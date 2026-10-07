import { publicEnv } from "@/lib/env";

/** Error returned by the Trustora API envelope: {"error": {"code", "message"}}. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type ApiOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  token?: string | null;
  /** JSON-serialisable body, or FormData for file uploads. */
  body?: unknown;
  signal?: AbortSignal;
  /** Extra request headers (server-side: the forwarded client IP). */
  headers?: Record<string, string>;
};

/** Typed fetch against the FastAPI backend. Works in both server and client code. */
export async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
  if (options.token) headers.Authorization = `Bearer ${options.token}`;

  let body: BodyInit | undefined;
  if (options.body instanceof FormData) {
    body = options.body; // the browser sets the multipart boundary
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(`${publicEnv.apiUrl}/api/v1${path}`, {
      method: options.method ?? "GET",
      headers,
      body,
      signal: options.signal,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "network_error", "Could not reach the Trustora API");
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const error = payload?.error;
    throw new ApiError(
      response.status,
      typeof error?.code === "string" ? error.code : "http_error",
      typeof error?.message === "string" ? error.message : response.statusText,
    );
  }

  return (response.status === 204 ? undefined : await response.json()) as T;
}
