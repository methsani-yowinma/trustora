"use client";

import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { TextAreaField } from "@/components/ui/Field";
import { clientApi } from "@/lib/api/browser";
import { useApiAction } from "@/lib/useApiAction";

export function ReviewResponseForm({ reviewId }: { reviewId: string }) {
  const t = useTranslations("smeReviews");
  const { run, pending, error } = useApiAction();
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <Button variant="secondary" onClick={() => setOpen(true)}>
        {t("respond")}
      </Button>
    );
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const response = String(new FormData(event.currentTarget).get("response") ?? "").trim();
    await run(() => clientApi(`/sme/reviews/${reviewId}/response`, { method: "POST", body: { response } }));
  }

  return (
    <form onSubmit={onSubmit} className="space-y-2">
      <TextAreaField label={t("response")} name="response" required maxLength={1000} rows={3} />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Button type="submit" disabled={pending}>
        {t("submit")}
      </Button>
    </form>
  );
}
