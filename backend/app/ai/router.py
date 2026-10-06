from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncConnection

from app.ai import document_analyzer, trust_explainer
from app.ai.gemini_client import AiClient
from app.ai.output import AiAnalysisOut
from app.ai.schemas import TrustExplanationOut
from app.auth.dependencies import get_anon_db, get_storage, get_user_db, require_role
from app.auth.models import CurrentUser, UserRole
from app.core.rate_limit import rate_limit
from app.core.storage import StorageClient


def get_ai(request: Request) -> AiClient:
    return request.app.state.ai


Ai = Annotated[AiClient, Depends(get_ai)]
Storage = Annotated[StorageClient, Depends(get_storage)]

public_router = APIRouter(tags=["trust"])


@public_router.get(
    "/stores/{slug}/trust/explanation",
    response_model=TrustExplanationOut,
    dependencies=[Depends(rate_limit("30/minute", scope="ai"))],
)
async def trust_explanation(
    slug: Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{3,40}$")],
    conn: Annotated[AsyncConnection, Depends(get_anon_db, scope="function")],
    storage: Storage,
    ai: Ai,
    locale: Literal["en", "si"] = "en",
) -> TrustExplanationOut:
    """AI summary of the store's trust signals (or a deterministic template). Never the score itself."""
    return await trust_explainer.explain(conn, storage, ai, slug, locale)


admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.post(
    "/evidence/{evidence_id}/analyze",
    response_model=AiAnalysisOut,
    dependencies=[Depends(rate_limit("20/minute", scope="ai"))],
)
async def analyze_evidence(
    evidence_id: UUID,
    admin: Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN))],
    conn: Annotated[AsyncConnection, Depends(get_user_db, scope="function")],
    storage: Storage,
    ai: Ai,
) -> AiAnalysisOut:
    return await document_analyzer.analyze_evidence(conn, storage, ai, admin, str(evidence_id))
