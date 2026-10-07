"use client";

import { Star } from "lucide-react";
import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { TextAreaField } from "@/components/ui/Field";
import { clientApi } from "@/lib/api/browser";
import { cn } from "@/lib/cn";
import { useApiAction } from "@/lib/useApiAction";

export function ReviewForm({ orderId }: { orderId: string }) {
  const t = useTranslations("reviews");
  const { run, pending, error } = useApiAction();
  const [rating, setRating] = useState(5);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const comment = String(new FormData(event.currentTarget).get("comment") ?? "").trim();
    await run(() => clientApi(`/orders/${orderId}/review`, { method: "POST", body: { rating, comment: comment || undefined } }));
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div className="space-y-1">
        <h2 className="font-semibold">{t("writeTitle")}</h2>
        <p className="text-xs text-ink-muted">{t("writeBody")}</p>
      </div>
      <fieldset>
        <legend className="mb-1 text-sm font-medium">{t("rating")}</legend>
        <div className="flex gap-1">
          {[1, 2, 3, 4, 5].map((value) => (
            <label key={value} className="cursor-pointer rounded p-0.5 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand-600">
              <input
                type="radio"
                name="rating"
                value={value}
                checked={rating === value}
                onChange={() => setRating(value)}
                className="sr-only"
                aria-label={t("stars", { rating: value })}
              />
              <Star
                aria-hidden="true"
                className={cn("h-7 w-7", value <= rating ? "fill-trust-caution text-trust-caution" : "text-line")}
              />
            </label>
          ))}
        </div>
      </fieldset>
      <TextAreaField label={t("comment")} name="comment" rows={3} maxLength={1000} />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Button type="submit" disabled={pending} className="w-full">
        {t("submit")}
      </Button>
    </form>
  );
}
