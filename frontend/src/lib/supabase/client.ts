import { createBrowserClient } from "@supabase/ssr";

import { publicEnv } from "@/lib/env";

/** Supabase client for Client Components. Used for authentication only. */
export function createClient() {
  return createBrowserClient(publicEnv.supabaseUrl, publicEnv.supabaseAnonKey);
}
