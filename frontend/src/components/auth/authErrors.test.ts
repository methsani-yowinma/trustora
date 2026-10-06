import type { AuthError } from "@supabase/supabase-js";
import { describe, expect, it } from "vitest";

import { authErrorKey } from "./authErrors";

const error = (code: string) => ({ code, message: "provider text" }) as unknown as AuthError;

describe("authErrorKey", () => {
  it.each([
    ["invalid_credentials", "invalidCredentials"],
    ["email_not_confirmed", "emailNotConfirmed"],
    ["user_already_exists", "userExists"],
    ["email_exists", "userExists"],
    ["weak_password", "weakPassword"],
    ["over_request_rate_limit", "rateLimited"],
    ["something_new", "generic"],
  ])("maps %s to a translated message key", (code, key) => {
    expect(authErrorKey(error(code))).toBe(key);
  });
});
