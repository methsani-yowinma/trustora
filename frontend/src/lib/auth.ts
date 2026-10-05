import "server-only";

import { cache } from "react";

import { redirect } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";
import { ApiError, apiFetch } from "@/lib/api/client";
import type { Profile, UserRole } from "@/lib/api/types";
import { createClient } from "@/lib/supabase/server";

export type SessionState =
  | { status: "anonymous" }
  | { status: "authenticated"; profile: Profile }
  | { status: "unavailable"; code: string };

/**
 * Resolves the signed-in user's Trustora profile via the API (which verifies the JWT).
 * Cached per request.
 */
export const getSession = cache(async (): Promise<SessionState> => {
  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) return { status: "anonymous" };

  try {
    const profile = await apiFetch<Profile>("/me", { token });
    return { status: "authenticated", profile };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return { status: "anonymous" };
    return { status: "unavailable", code: error instanceof ApiError ? error.code : "unknown" };
  }
});

export type GuardResult =
  | { kind: "allowed"; profile: Profile }
  | { kind: "forbidden" }
  | { kind: "unavailable" };

/**
 * Server-side page guard. Redirects anonymous users to login; otherwise reports whether the
 * role is allowed. This only shapes the UI — the API enforces the same rules on every request.
 */
export async function requireRole(
  locale: Locale,
  allowed: UserRole[],
  returnTo: string,
): Promise<GuardResult> {
  const session = await getSession();
  if (session.status === "anonymous") {
    redirect({ href: { pathname: "/login", query: { next: returnTo } }, locale });
  }
  if (session.status !== "authenticated") return { kind: "unavailable" };
  return allowed.includes(session.profile.role)
    ? { kind: "allowed", profile: session.profile }
    : { kind: "forbidden" };
}
