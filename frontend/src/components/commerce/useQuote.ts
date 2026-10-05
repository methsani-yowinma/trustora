"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { ApiError, apiFetch } from "@/lib/api/client";
import type { Quote } from "@/lib/api/types";
import type { Cart } from "@/lib/cart";

/** Server-priced quote for the cart. The API is the only source of prices and availability. */
export function useQuote(cart: Cart, district: string) {
  const tErrors = useTranslations("apiErrors");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [version, setVersion] = useState(0);

  const key = cart ? JSON.stringify(cart.lines.map((l) => [l.productId, l.quantity])) : "";

  useEffect(() => {
    if (!cart || cart.lines.length === 0) return;
    const controller = new AbortController();
    // Loading flags are set from the request lifecycle, not synchronously in the effect body.
    queueMicrotask(() => setLoading(true));
    apiFetch<Quote>("/checkout/quote", {
      method: "POST",
      body: { items: cart.lines.map((l) => ({ product_id: l.productId, quantity: l.quantity })), district },
      signal: controller.signal,
    })
      .then((result) => {
        setQuote(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        const code = (err instanceof ApiError ? err.code : "generic") as Parameters<typeof tErrors>[0];
        setError(tErrors.has(code) ? tErrors(code) : tErrors("generic"));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // `key` captures the cart contents; `version` forces a refresh after a failed checkout.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, district, version]);

  const refresh = useCallback(() => setVersion((v) => v + 1), []);
  return { quote: cart && cart.lines.length ? quote : null, error, loading, refresh };
}
