from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.auth.models import AccountStatus, UserRole

# Mirrors the profiles.preferred_locale check constraint.
Locale = Literal["en", "si"]


class ProfileOut(BaseModel):
    id: str
    email: str | None
    role: UserRole
    status: AccountStatus
    full_name: str | None
    phone: str | None
    preferred_locale: Locale
    created_at: datetime


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, pattern=r"^\+?[0-9 ]{7,20}$")
    preferred_locale: Locale | None = None
