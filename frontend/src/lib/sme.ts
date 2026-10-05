import "server-only";

import { redirect } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";
import type { Profile, Sme } from "@/lib/api/types";
import { getOwnSme, requireRole } from "@/lib/auth";

export type SmeGuard =
  | { kind: "allowed"; profile: Profile; sme: Sme }
  | { kind: "onboarding"; profile: Profile }
  | { kind: "forbidden" }
  | { kind: "unavailable" };

/**
 * Guard for SME pages: requires the SME role and loads the SME's store. Pages other than the
 * dashboard send unregistered SMEs to onboarding at /sme.
 */
export async function requireSme(
  locale: Locale,
  returnTo: string,
  { allowOnboarding = false }: { allowOnboarding?: boolean } = {},
): Promise<SmeGuard> {
  const guard = await requireRole(locale, ["SME"], returnTo);
  if (guard.kind !== "allowed") return guard;

  let sme: Sme | null;
  try {
    sme = await getOwnSme();
  } catch {
    return { kind: "unavailable" };
  }

  if (sme) return { kind: "allowed", profile: guard.profile, sme };
  if (!allowOnboarding) redirect({ href: "/sme", locale });
  return { kind: "onboarding", profile: guard.profile };
}
