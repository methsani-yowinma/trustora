import "server-only";

import { headers } from "next/headers";

import { apiFetch } from "@/lib/api/client";

type Options = Parameters<typeof apiFetch>[1];

/**
 * API calls made while server-rendering. The visitor's IP is forwarded so the API's per-client
 * rate limits apply per visitor, not to the frontend server as a whole. The API trusts this
 * header only from the frontend server (uvicorn --proxy-headers --forwarded-allow-ips).
 */
export async function serverFetch<T>(path: string, options: Options = {}): Promise<T> {
  const incoming = await headers();
  const clientIp = incoming.get("x-forwarded-for") ?? incoming.get("x-real-ip");
  return apiFetch<T>(path, {
    ...options,
    headers: { ...options?.headers, ...(clientIp ? { "X-Forwarded-For": clientIp } : {}) },
  });
}
