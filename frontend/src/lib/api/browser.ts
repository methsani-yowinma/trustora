"use client";

import { apiFetch } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/client";

type Options = Omit<Parameters<typeof apiFetch>[1], "token">;

/** Authenticated API call from Client Components (uses the current Supabase session). */
export async function clientApi<T>(path: string, options: Options = {}): Promise<T> {
  const { data } = await createClient().auth.getSession();
  return apiFetch<T>(path, { ...options, token: data.session?.access_token });
}
