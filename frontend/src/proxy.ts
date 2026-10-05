import createIntlMiddleware from "next-intl/middleware";
import type { NextRequest } from "next/server";

import { routing } from "@/i18n/routing";
import { refreshSession } from "@/lib/supabase/proxy";

const handleI18nRouting = createIntlMiddleware(routing);

// Locale routing + session refresh only. Authorization is enforced by the API and by
// server-side checks in protected pages — never here alone.
export async function proxy(request: NextRequest) {
  const response = handleI18nRouting(request);
  return refreshSession(request, response);
}

export const config = {
  matcher: "/((?!api|_next|_vercel|.*\..*).*)",
};
