// Mirrors backend Pydantic schemas (app/users/schemas.py).
export type UserRole = "CUSTOMER" | "SME" | "ADMIN";
export type AccountStatus = "ACTIVE" | "SUSPENDED";

export type Profile = {
  id: string;
  email: string | null;
  role: UserRole;
  status: AccountStatus;
  full_name: string | null;
  phone: string | null;
  preferred_locale: "en" | "si";
  created_at: string;
};
