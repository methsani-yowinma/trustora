from enum import StrEnum

from pydantic import BaseModel


class UserRole(StrEnum):
    CUSTOMER = "CUSTOMER"
    SME = "SME"
    ADMIN = "ADMIN"


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class CurrentUser(BaseModel):
    id: str
    email: str | None
    role: UserRole
