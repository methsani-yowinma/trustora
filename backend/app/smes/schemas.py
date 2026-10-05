import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.i18n import LocalizedPolicy, LocalizedStoreDescription
from app.evidence.schemas import EvidenceFileOut

RESERVED_SLUGS = frozenset(
    {
        "admin",
        "api",
        "sme",
        "smes",
        "store",
        "stores",
        "login",
        "signup",
        "auth",
        "trustora",
        "support",
        "help",
        "about",
        "en",
        "si",
        "ta",
        "new",
        "settings",
        "account",
        "orders",
    }
)

Slug = Annotated[
    str,
    BeforeValidator(lambda v: v.strip().lower() if isinstance(v, str) else v),
    StringConstraints(pattern=r"^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$"),
]
StoreName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+?[0-9 ]{7,20}$")]


class VerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class SocialPlatform(StrEnum):
    INSTAGRAM = "INSTAGRAM"
    FACEBOOK = "FACEBOOK"
    TIKTOK = "TIKTOK"
    WHATSAPP = "WHATSAPP"


class StorePolicies(BaseModel):
    model_config = ConfigDict(extra="forbid")

    returns: LocalizedPolicy | None = None
    refunds: LocalizedPolicy | None = None
    delivery: LocalizedPolicy | None = None


# --- Requests -----------------------------------------------------------------
class SmeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: Slug
    name: StoreName
    description_i18n: LocalizedStoreDescription | None = None
    contact_email: EmailStr | None = None
    contact_phone: Phone | None = None

    @field_validator("slug")
    @classmethod
    def _not_reserved(cls, value: str) -> str:
        if value in RESERVED_SLUGS or "--" in value:
            raise ValueError("This store address is not available")
        return value


class SmeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: StoreName | None = None
    description_i18n: LocalizedStoreDescription | None = None
    policies_i18n: StorePolicies | None = None
    contact_email: EmailStr | None = None
    contact_phone: Phone | None = None
    is_published: bool | None = None

    @model_validator(mode="after")
    def _name_not_null(self) -> "SmeUpdate":
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be empty")
        if "is_published" in self.model_fields_set and self.is_published is None:
            raise ValueError("is_published must be true or false")
        return self


_PLATFORM_HOSTS = {
    SocialPlatform.INSTAGRAM: ("instagram.com",),
    SocialPlatform.FACEBOOK: ("facebook.com", "fb.com", "fb.me"),
    SocialPlatform.TIKTOK: ("tiktok.com",),
    SocialPlatform.WHATSAPP: ("wa.me", "whatsapp.com"),
}


class SocialAccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    platform: SocialPlatform
    handle: Annotated[
        str,
        BeforeValidator(lambda v: v.strip().removeprefix("@") if isinstance(v, str) else v),
        StringConstraints(pattern=r"^[A-Za-z0-9_.+ -]{2,60}$"),
    ]
    url: Annotated[str, StringConstraints(max_length=300)] | None = None

    @model_validator(mode="after")
    def _url_matches_platform(self) -> "SocialAccountCreate":
        # Only links to the declared platform: prevents phishing links on public store pages.
        if self.url:
            parsed = urlparse(self.url)
            host = (parsed.hostname or "").lower()
            allowed = _PLATFORM_HOSTS[self.platform]
            if parsed.scheme != "https" or not any(
                host == h or host.endswith("." + h) for h in allowed
            ):
                raise ValueError(f"URL must be an https link to {allowed[0]}")
            if re.search(r"\s", self.url):
                raise ValueError("URL must not contain spaces")
        return self


class VerificationDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: Literal["APPROVED", "REJECTED"]
    note: Annotated[str, StringConstraints(max_length=1000)] | None = None
    contact_verified: bool = False
    # Rejected documents that appear forged or do not belong to the business.
    documents_misleading: bool = False

    @model_validator(mode="after")
    def _note_required_on_reject(self) -> "VerificationDecisionIn":
        if self.decision == "REJECTED" and not self.note:
            raise ValueError("A note explaining the rejection is required")
        if self.decision == "REJECTED" and self.contact_verified:
            raise ValueError("Contact details cannot be confirmed on a rejected application")
        if self.decision == "APPROVED" and self.documents_misleading:
            raise ValueError("Approved documents cannot be flagged as misleading")
        return self


class SocialDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verified: bool


# --- Responses ----------------------------------------------------------------
class SocialAccountOut(BaseModel):
    id: str
    platform: SocialPlatform
    handle: str
    url: str | None
    ownership_verified: bool
    verified_at: datetime | None


class OwnSocialAccountOut(SocialAccountOut):
    verification_code: str


class VerificationSummary(BaseModel):
    id: str
    status: Literal["SUBMITTED", "APPROVED", "REJECTED"]
    business_reg_number: str
    registered_name: str
    submitted_at: datetime
    reviewed_at: datetime | None
    decision_note: str | None


class SmeOut(BaseModel):
    """The owner's (or an admin's) full view of an SME."""

    id: str
    slug: str
    name: str
    logo_url: str | None
    description_i18n: dict[str, str] | None
    policies_i18n: dict[str, dict[str, str]]
    contact_email: str | None
    contact_phone: str | None
    contact_verified: bool
    verification_status: VerificationStatus
    verified_at: datetime | None
    is_published: bool
    status: Literal["ACTIVE", "SUSPENDED"]
    created_at: datetime
    product_counts: dict[str, int] = Field(default_factory=dict)
    social_accounts: list[OwnSocialAccountOut] = Field(default_factory=list)
    latest_verification: VerificationSummary | None = None


class PublicStoreOut(BaseModel):
    id: str
    slug: str
    name: str
    logo_url: str | None
    description_i18n: dict[str, str] | None
    policies_i18n: dict[str, dict[str, str]]
    contact_email: str | None
    contact_phone: str | None
    contact_verified: bool
    verification_status: VerificationStatus
    verified_at: datetime | None
    member_since: datetime
    social_accounts: list[SocialAccountOut]


class VerificationOut(VerificationSummary):
    documents: list[EvidenceFileOut] = Field(default_factory=list)


class AdminVerificationListItem(VerificationSummary):
    sme_id: str
    sme_name: str
    sme_slug: str


class AdminVerificationDetail(AdminVerificationListItem):
    sme: SmeOut
    documents: list[EvidenceFileOut]
    history: list[VerificationSummary]


class AdminSocialAccountItem(OwnSocialAccountOut):
    sme_id: str
    sme_name: str
    sme_slug: str
    created_at: datetime
