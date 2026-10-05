from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.i18n import LocalizedDescription, LocalizedName
from app.evidence.schemas import EvidenceFileOut

Price = Annotated[Decimal, Field(gt=0, le=10_000_000, max_digits=12, decimal_places=2)]
Stock = Annotated[int, Field(ge=0, le=1_000_000)]


class AuthenticityStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    CONCERN = "CONCERN"


class CategoryOut(BaseModel):
    id: int
    slug: str
    name_i18n: dict[str, str]


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: int = Field(ge=1)
    name_i18n: LocalizedName
    description_i18n: LocalizedDescription | None = None
    price_lkr: Price
    stock: Stock = 0
    status: Literal["ACTIVE", "HIDDEN"] = "ACTIVE"


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: int | None = Field(default=None, ge=1)
    name_i18n: LocalizedName | None = None
    description_i18n: LocalizedDescription | None = None
    price_lkr: Price | None = None
    stock: Stock | None = None
    # REMOVED is only reachable through DELETE.
    status: Literal["ACTIVE", "HIDDEN"] | None = None

    @model_validator(mode="after")
    def _required_fields_not_null(self) -> "ProductUpdate":
        for name in ("category_id", "name_i18n", "price_lkr", "stock", "status"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class ProductEvidenceType(StrEnum):
    PRODUCT_DOCUMENT = "PRODUCT_DOCUMENT"
    PRODUCT_IMAGE = "PRODUCT_IMAGE"


EvidenceDescription = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)
]


class ProductImageOut(BaseModel):
    id: str
    url: str
    sort_order: int


class ProductOut(BaseModel):
    """Owner view."""

    id: str
    category_id: int
    name_i18n: dict[str, str]
    description_i18n: dict[str, str] | None
    price_lkr: Decimal
    stock: int
    status: Literal["ACTIVE", "HIDDEN", "REMOVED"]
    authenticity_status: AuthenticityStatus
    images: list[ProductImageOut]
    created_at: datetime
    updated_at: datetime


class ProductDetailOut(ProductOut):
    evidence: list[EvidenceFileOut]


class PublicProductOut(BaseModel):
    id: str
    category_id: int
    name_i18n: dict[str, str]
    description_i18n: dict[str, str] | None
    price_lkr: Decimal
    in_stock: bool
    authenticity_status: AuthenticityStatus
    images: list[ProductImageOut]


# --- Public browsing (Phase 5) ----------------------------------------------------------
class StoreBadge(BaseModel):
    id: str
    slug: str
    name: str
    verification_status: str
    trust_level: str | None
    trust_score: int | None


class ProductCard(BaseModel):
    id: str
    category_id: int
    name_i18n: dict[str, str]
    price_lkr: Decimal
    in_stock: bool
    authenticity_status: AuthenticityStatus
    image_url: str | None
    store: StoreBadge


class ProductPage(BaseModel):
    items: list[ProductCard]
    total: int
    page: int
    page_size: int


class PublicProductDetail(PublicProductOut):
    store: StoreBadge
    max_quantity: int


class StoreCard(BaseModel):
    id: str
    slug: str
    name: str
    logo_url: str | None
    description_i18n: dict[str, str] | None
    verification_status: str
    trust_level: str | None
    trust_score: int | None
    product_count: int


class StorePage(BaseModel):
    items: list[StoreCard]
    total: int
    page: int
    page_size: int
