import { createServerClient } from "@supabase/ssr";
import type { NextRequest, NextResponse } from "next/server";

import { publicEnv } from "@/lib/env";

/** Refreshes the Supabase session cookie on the outgoing response (if it is about to expire). */
export async function refreshSession(request: NextRequest, response: NextResponse) {
  const supabase = createServerClient(publicEnv.supabaseUrl, publicEnv.supabaseAnonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options),
        );
      },
    },
  });

  // Do not remove: validates the token and triggers a refresh when needed.
  await supabase.auth.getClaims();
  return response;
}
