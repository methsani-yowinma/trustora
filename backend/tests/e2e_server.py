"""TEST-ONLY API server for frontend end-to-end tests.

Starts an embedded PostgreSQL, applies the Supabase shim + real migrations, seeds demo data and
serves the real FastAPI app. Public (signed-out) pages can then be tested end to end without a
Supabase project. Usage: python -m tests.e2e_server --port 8100
"""

import argparse
import asyncio
import json
import tempfile
from pathlib import Path

import pgserver
import uvicorn
from sqlalchemy import text

import app.main as main_module
from app.core.config import Settings
from app.core.db import Database, create_engine
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
SHIM = Path(__file__).parent / "sql" / "supabase_shim.sql"
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))

SME_USER = "00000000-0000-4000-8000-000000000001"
DRAFT_USER = "00000000-0000-4000-8000-000000000002"


class PublicOnlyStorage:
    async def upload(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("uploads are not available in the e2e server")

    async def delete(self, *args: object, **kwargs: object) -> None:
        return None

    async def signed_url(self, *args: object, **kwargs: object) -> str:
        raise RuntimeError("signed URLs are not available in the e2e server")

    async def download(self, *args: object, **kwargs: object) -> bytes:
        raise RuntimeError("downloads are not available in the e2e server")

    def public_url(self, bucket: str, path: str) -> str:
        return f"http://localhost/storage/{bucket}/{path}"


SEED = [
    (
        "insert into auth.users (id, email, raw_user_meta_data) values "
        "(:sme, 'shop@example.test', '{\"role\": \"SME\"}'), "
        "(:draft, 'draft@example.test', '{\"role\": \"SME\"}')",
        {"sme": SME_USER, "draft": DRAFT_USER},
    ),
    (
        "insert into public.smes (id, owner_id, slug, name, description_i18n, policies_i18n, "
        "contact_phone, contact_verified, verification_status, verified_at, is_published) values "
        "('10000000-0000-4000-8000-000000000001', :sme, 'ceylon-crafts', 'Ceylon Crafts', "
        "cast(:description as jsonb), cast(:policies as jsonb), '+94 77 123 4567', true, "
        "'VERIFIED', now(), true), "
        "('10000000-0000-4000-8000-000000000002', :draft, 'draft-store', 'Draft Store', null, "
        "'{}', null, false, 'UNVERIFIED', null, false)",
        {
            "sme": SME_USER,
            "draft": DRAFT_USER,
            "description": json.dumps(
                {"en": "Handloom textiles from Dumbara.", "si": "දුම්බර අත්යන්ත්‍ර රෙදිපිළි."}
            ),
            "policies": json.dumps(
                {
                    "returns": {
                        "en": "Returns accepted within 7 days.",
                        "si": "දින 7ක් ඇතුළත ආපසු භාර ගනී.",
                    }
                }
            ),
        },
    ),
    (
        "insert into public.sme_social_accounts (sme_id, platform, handle, url, verification_code, "
        "ownership_verified, verified_at) values "
        "('10000000-0000-4000-8000-000000000001', 'INSTAGRAM', 'ceylon.crafts', "
        "'https://instagram.com/ceylon.crafts', 'TRUSTORA-ABC123', true, now()), "
        "('10000000-0000-4000-8000-000000000001', 'TIKTOK', 'unconfirmed.handle', null, "
        "'TRUSTORA-XYZ789', false, null)",
        {},
    ),
    (
        "insert into public.products (sme_id, category_id, name_i18n, price_lkr, stock, status) values "
        "('10000000-0000-4000-8000-000000000001', 1, cast(:p1 as jsonb), 12500, 4, 'ACTIVE'), "
        "('10000000-0000-4000-8000-000000000001', 6, cast(:p2 as jsonb), 3200, 0, 'ACTIVE'), "
        "('10000000-0000-4000-8000-000000000001', 6, cast(:p3 as jsonb), 999, 1, 'HIDDEN')",
        {
            "p1": json.dumps({"en": "Dumbara handloom saree", "si": "දුම්බර අත්යන්ත්‍ර සාරිය"}),
            "p2": json.dumps({"en": "Lacquer jewellery box"}),
            "p3": json.dumps({"en": "Hidden test product"}),
        },
    ),
    # A second published store, for "one store per cart" behaviour.
    (
        "insert into auth.users (id, email, raw_user_meta_data) values "
        "('00000000-0000-4000-8000-000000000003', 'spice@example.test', '{\"role\": \"SME\"}')",
        {},
    ),
    (
        "insert into public.smes (id, owner_id, slug, name, is_published) values "
        "('10000000-0000-4000-8000-000000000003', '00000000-0000-4000-8000-000000000003', "
        "'matale-spice', 'Matale Spice Garden', true)",
        {},
    ),
    (
        "insert into public.products (sme_id, category_id, name_i18n, price_lkr, stock) values "
        "('10000000-0000-4000-8000-000000000003', 5, cast(:name as jsonb), 850, 30)",
        {"name": json.dumps({"en": "Ceylon cinnamon sticks"})},
    ),
    # Matale Spice: one delivered order with a verified review, one order with an open complaint.
    (
        "insert into auth.users (id, email, raw_user_meta_data) values "
        "('00000000-0000-4000-8000-000000000004', 'buyer@example.test', '{}')",
        {},
    ),
    (
        "insert into public.orders (id, order_number, customer_id, sme_id, status, subtotal_lkr, "
        "delivery_fee_lkr, total_lkr, shipping_address, payment_method, idempotency_key, delivered_at) "
        "values "
        "('20000000-0000-4000-8000-000000000001', 'TR-SEEDREV1', '00000000-0000-4000-8000-000000000004', "
        "'10000000-0000-4000-8000-000000000003', 'DELIVERED', 850, 500, 1350, '{}', 'COD', "
        "gen_random_uuid(), now() - interval '3 days'), "
        "('20000000-0000-4000-8000-000000000002', 'TR-SEEDCMP1', '00000000-0000-4000-8000-000000000004', "
        "'10000000-0000-4000-8000-000000000003', 'PLACED', 850, 500, 1350, '{}', 'COD', "
        "gen_random_uuid(), null)",
        {},
    ),
    (
        "insert into public.reviews (order_id, sme_id, customer_id, rating, comment, sme_response, "
        "sme_responded_at) values ('20000000-0000-4000-8000-000000000001', "
        "'10000000-0000-4000-8000-000000000003', '00000000-0000-4000-8000-000000000004', 5, "
        "'Fresh cinnamon, well packed.', 'Thank you for shopping with us!', now())",
        {},
    ),
    (
        "insert into public.complaints (order_id, sme_id, customer_id, category, description) values "
        "('20000000-0000-4000-8000-000000000002', '10000000-0000-4000-8000-000000000003', "
        "'00000000-0000-4000-8000-000000000004', 'DELIVERY', "
        "'Private complaint text: order placed two weeks ago and still not received.')",
        {},
    ),
    (
        # Earlier trust history, so the passport can show a 30-day change and a chart.
        # The current score is computed by the real trust engine on first view.
        "insert into public.trust_score_history (sme_id, overall_score, level, business_score, "
        "product_score, transaction_score, rules_version, trigger, created_at) values "
        "('10000000-0000-4000-8000-000000000001', 72, 'TRUSTED', 85, 70, 60, 'seed', 'seed', "
        "now() - interval '45 days'), "
        "('10000000-0000-4000-8000-000000000001', 66, 'DEVELOPING', 80, 55, 55, 'seed', 'seed', "
        "now() - interval '20 days')",
        {},
    ),
]


async def prepare(uri: str) -> None:
    engine = create_engine(uri.replace("postgresql://", "postgresql+asyncpg://", 1))
    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        for path in [SHIM, *MIGRATIONS]:
            await raw.driver_connection.execute(path.read_text(encoding="utf-8"))
        for statement, params in SEED:
            await conn.execute(text(statement), params)
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()

    server = pgserver.get_server(tempfile.mkdtemp(prefix="trustora-e2e-"), cleanup_mode="delete")
    uri = server.get_uri()
    asyncio.run(prepare(uri))

    settings = Settings(
        app_env="test",
        supabase_url="https://e2e.supabase.test",
        database_url=uri,
        cors_origins="http://localhost:3100",
    )
    database = Database(create_engine(settings.async_database_url))
    # Every e2e request comes from 127.0.0.1 (one client), so the per-client limit is raised here;
    # the real limit is covered by backend tests.
    main_module.DEFAULT_LIMIT = "100000/minute"
    app = create_app(settings, db=database, storage=PublicOnlyStorage())
    # As in production: trust X-Forwarded-For only from the frontend server's address.
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )


if __name__ == "__main__":
    main()
