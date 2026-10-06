"use client";

import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";

import { useRouter } from "@/i18n/navigation";
import { ApiError } from "@/lib/api/client";

/**
 * Runs an API mutation with pending/error state. On success the current route's Server
 * Components are refreshed so they re-read data from the API.
 */
export function useApiAction() {
  const t = useTranslations("apiErrors");
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async <T>(action: () => Promise<T>, options: { refresh?: boolean } = {}): Promise<T | undefined> => {
      setPending(true);
      setError(null);
      try {
        const result = await action();
        if (options.refresh !== false) router.refresh();
        return result;
      } catch (err) {
        // API error codes are runtime strings; unknown codes fall back to a generic message.
        const code = (err instanceof ApiError ? err.code : "generic") as Parameters<typeof t>[0];
        setError(t.has(code) ? t(code) : t("generic"));
        return undefined;
      } finally {
        setPending(false);
      }
    },
    [router, t],
  );

  return { run, pending, error, setError };
}
