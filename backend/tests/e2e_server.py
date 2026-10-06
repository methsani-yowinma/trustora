"""TEST-ONLY API server for frontend end-to-end tests.

Starts an embedded PostgreSQL, applies the Supabase shim + real migrations, seeds demo data and
serves the real FastAPI app, plus a stand-in for Supabase Auth under /auth/v1 so browser tests can
sign in (tests/fake_supabase_auth.py). No Supabase project is needed.
Usage: python -m tests.e2e_server --port 8100
"""

import argparse
import asyncio
import json
import re
import tempfile
from pathlib import Path

import pgserver
import uvicorn
from sqlalchemy import text

import app.core.rate_limit as rate_limit_module
import app.main as main_module
from app.ai.gemini_client import ChatMessage, DisabledAiClient, ModelTurn, ToolCall, ToolResults
from app.core.config import Settings
from app.core.db import Database, create_engine
from app.core.security import TokenVerifier
from app.main import create_app
from tests.fake_supabase_auth import FakeAuth, FakeUser

ROOT = Path(__file__).resolve().parents[2]
SHIM = Path(__file__).parent / "sql" / "supabase_shim.sql"
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))

SME_USER = "00000000-0000-4000-8000-000000000001"
DRAFT_USER = "00000000-0000-4000-8000-000000000002"
NIMAL_USER = "00000000-0000-4000-8000-000000000005"
ADMIN_USER = "00000000-0000-4000-8000-000000000006"
DRAFT_SME = "10000000-0000-4000-8000-000000000002"

# Sign-in accounts for browser tests (all share one password; test-only).
E2E_PASSWORD = "trustora-e2e-pass"
ACCOUNTS = {
    "shop@example.test": SME_USER,
    "draft@example.test": DRAFT_USER,
    "spice@example.test": "00000000-0000-4000-8000-000000000003",
    "buyer@example.test": "00000000-0000-4000-8000-000000000004",
    "nimal@example.test": NIMAL_USER,
    "admin@example.test": ADMIN_USER,
    "complain-desktop@example.test": "00000000-0000-4000-8000-000000000007",
    "complain-mobile@example.test": "00000000-0000-4000-8000-000000000008",
    "kitchen@example.test": "00000000-0000-4000-8000-000000000009",
}


class _NoLimit:
    def hit(self, *args: object) -> bool:
        return True


class ScriptedChatAi(DisabledAiClient):
    """Deterministic stand-in for Gemini in browser tests, for the chat only.

    It asks for the real `get_seller_trust` tool when the user is on a store page and answers from
    the tool result, so the UI is tested against real, authorized data. Other AI features stay
    unavailable (they inherit the disabled behaviour), as without a key.
    """

    model = "e2e-scripted"
    enabled = True

    async def chat(
        self, *, system: str, history: list, tools: list, max_tokens: int = 800
    ) -> ModelTurn:  # type: ignore[override]
        last = history[-1]
        question = next(
            m.text.lower()
            for m in reversed(history)
            if isinstance(m, ChatMessage) and m.role == "user"
        )
        if isinstance(last, ToolResults):
            call, result = last.results[0]
            if call.name == "get_my_orders":
                orders = result.get("orders", [])
                if "complain" in question and orders:
                    return ModelTurn(text=None, calls=[ToolCall("draft_complaint", {
                        "order_number": orders[0]["order_number"], "category": "DELIVERY",
                        "description": "My order has not arrived yet.",
                    })])  # fmt: skip
                listed = ", ".join(f"{o['order_number']} ({o['status']})" for o in orders)
                return ModelTurn(
                    text=f"Your orders: {listed}." if orders else "You have no orders yet."
                )
            if call.name == "draft_complaint":
                return ModelTurn(text=(
                    "I've prepared a complaint draft. Please review and confirm it below."
                    if result.get("drafted") else "A complaint can't be opened for this order now."
                ))  # fmt: skip
            if "trust_level" in result:
                return ModelTurn(text=(
                    f"{result['store_name']} has the trust level {result['trust_level']} "
                    f"({result['overall_score']}/100), calculated by Trustora's rules."
                ))  # fmt: skip
        elif "signed in as a" in system and ("order" in question or "complain" in question):
            return ModelTurn(text=None, calls=[ToolCall("get_my_orders", {})])
        elif slug := re.search(r'store_slug "([^"]+)"', system):
            return ModelTurn(
                text=None, calls=[ToolCall("get_seller_trust", {"store_slug": slug[1]})]
            )
        return ModelTurn(text="There isn't enough verified evidence to determine this.")


class PublicOnlyStorage:
    async def upload(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("uploads are not available in the e2e server")

    async def delete(self, *args: object, **kwargs: object) -> None:
        return None

    async def signed_url(self, bucket: str, path: str, expires_in: int = 300) -> str:
        # Seeded documents have no file; admins still see a (dead) link, as in production.
        return f"http://localhost:8100/e2e-no-file/{path}"

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


# Accounts used by signed-in browser tests, and a business verification waiting for an admin.
SEED += [
    # A store only signed-in tests buy from and change, so public-page assertions on the other
    # stores stay stable while both Playwright projects run in parallel.
    (
        "insert into auth.users (id, email, raw_user_meta_data) values "
        "('00000000-0000-4000-8000-000000000009', 'kitchen@example.test', '{\"role\": \"SME\"}')",
        {},
    ),
    (
        "insert into public.smes (id, owner_id, slug, name, is_published) values "
        "('10000000-0000-4000-8000-000000000009', '00000000-0000-4000-8000-000000000009', "
        "'kegalle-kitchen', 'Kegalle Kitchen', true)",
        {},
    ),
    (
        "insert into public.products (sme_id, category_id, name_i18n, price_lkr, stock) values "
        "('10000000-0000-4000-8000-000000000009', 5, cast(:name as jsonb), 650, 10000)",
        {"name": json.dumps({"en": "Kithul treacle", "si": "කිතුල් පැණි"})},
    ),
    (
        "insert into auth.users (id, email, raw_user_meta_data) values "
        "(:nimal, 'nimal@example.test', '{}'), (:admin, 'admin@example.test', '{}'), "
        "('00000000-0000-4000-8000-000000000007', 'complain-desktop@example.test', '{}'), "
        "('00000000-0000-4000-8000-000000000008', 'complain-mobile@example.test', '{}')",
        {"nimal": NIMAL_USER, "admin": ADMIN_USER},
    ),
    # Admins are never created by sign-up; promote by SQL, as in production.
    ("update public.profiles set role = 'ADMIN' where id = :admin", {"admin": ADMIN_USER}),
    (
        "update public.smes set verification_status = 'PENDING' where id = :sme",
        {"sme": DRAFT_SME},
    ),
    (
        "insert into public.business_verifications (id, sme_id, business_reg_number, "
        "registered_name, submitted_by) values ('30000000-0000-4000-8000-000000000001', :sme, "
        "'PV 00123', 'Draft Store (Pvt) Ltd', :owner)",
        {"sme": DRAFT_SME, "owner": DRAFT_USER},
    ),
    (
        "insert into public.evidence (type, provenance, sme_id, verification_id, description, "
        "source, storage_path, mime_type, size_bytes, sha256, created_by) values "
        "('BUSINESS_DOCUMENT', 'SELLER_CLAIM', :sme, '30000000-0000-4000-8000-000000000001', "
        "'Business registration certificate', 'SME_UPLOAD', 'verification/e2e-certificate.pdf', "
        "'application/pdf', 2048, repeat('a', 64), :owner)",
        {"sme": DRAFT_SME, "owner": DRAFT_USER},
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
        supabase_url=f"http://localhost:{args.port}",
        database_url=uri,
        cors_origins="http://localhost:3100",
    )
    auth = FakeAuth(
        issuer=settings.jwt_issuer,
        users=[FakeUser(user_id, email, E2E_PASSWORD) for email, user_id in ACCOUNTS.items()],
        cors_origin="http://localhost:3100",
    )
    database = Database(create_engine(settings.async_database_url))
    # Every e2e request comes from 127.0.0.1 (one client, many parallel tests), so rate limits
    # are switched off here; they are covered by the backend tests.
    main_module.DEFAULT_LIMIT = "100000/minute"
    rate_limit_module._limiter = _NoLimit()
    app = create_app(
        settings,
        db=database,
        token_verifier=TokenVerifier(issuer=settings.jwt_issuer, jwks_client=auth),
        storage=PublicOnlyStorage(),
        ai=ScriptedChatAi(),
    )

    async def server(scope: dict, receive: object, send: object) -> None:
        # /auth/v1/* → Supabase Auth stand-in (own CORS rules); everything else → the real API.
        if scope["type"] == "http" and scope["path"].startswith("/auth/v1/"):
            scope = {**scope, "path": scope["path"][len("/auth/v1") :],
                     "root_path": scope.get("root_path", "") + "/auth/v1"}  # fmt: skip
            await auth.app(scope, receive, send)
        else:
            await app(scope, receive, send)

    # As in production: trust X-Forwarded-For only from the frontend server's address.
    uvicorn.run(
        server,
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )


if __name__ == "__main__":
    main()
