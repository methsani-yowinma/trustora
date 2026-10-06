"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { SelectField, TextAreaField } from "@/components/ui/Field";
import { Link } from "@/i18n/navigation";
import { clientApi } from "@/lib/api/browser";
import type { ComplaintDraft } from "@/lib/api/types";
import { useApiAction } from "@/lib/useApiAction";

const CATEGORIES = [
  "DELIVERY",
  "WRONG_PRODUCT",
  "PRODUCT_AUTHENTICITY",
  "REFUND",
  "PAYMENT",
  "CUSTOMER_SERVICE",
  "PRODUCT_QUALITY",
  "OTHER",
] as const;

/**
 * A complaint prepared by Trustora AI. Nothing is sent until the customer reviews, optionally
 * edits, and submits it here, through the same endpoint as the order page.
 */
export function ComplaintDraftCard({ draft }: { draft: ComplaintDraft }) {
  const t = useTranslations("chat");
  const tCategory = useTranslations("complaintCategory");
  const { run, pending, error } = useApiAction();
  const [category, setCategory] = useState(draft.category);
  const [description, setDescription] = useState(draft.description);
  const [state, setState] = useState<"draft" | "submitted" | "discarded">("draft");
  const tooShort = description.trim().length < 10;

  if (state === "discarded") return <p className="text-xs text-ink-muted">{t("discarded")}</p>;
  if (state === "submitted") {
    return (
      <Alert tone="success">
        {t("submitted")}{" "}
        <Link href={`/orders/${draft.order_id}`} className="font-medium underline">
          {t("viewOrder")}
        </Link>
      </Alert>
    );
  }

  async function submit() {
    const form = new FormData();
    form.set("category", category);
    form.set("description", description.trim());
    const result = await run(
      () => clientApi(`/orders/${draft.order_id}/complaints`, { method: "POST", body: form }),
      { refresh: false },
    );
    if (result !== undefined) setState("submitted");
  }

  return (
    <div className="space-y-3 rounded-xl border border-trust-caution/40 bg-surface p-3">
      <div>
        <p className="text-sm font-semibold">{t("draftTitle")}</p>
        <p className="text-xs text-ink-muted">
          {t("draftOrder", { number: draft.order_number })} · {t("draftNote")}
        </p>
      </div>
      <SelectField
        label={t("category")}
        id={`draft-category-${draft.order_id}`}
        value={category}
        onChange={(e) => setCategory(e.target.value)}
      >
        {CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {tCategory(c)}
          </option>
        ))}
      </SelectField>
      <TextAreaField
        label={t("description")}
        id={`draft-description-${draft.order_id}`}
        rows={3}
        maxLength={2000}
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        error={tooShort ? t("descriptionTooShort") : undefined}
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="flex flex-wrap gap-2">
        <Button onClick={submit} disabled={pending || tooShort}>
          {pending ? t("submitting") : t("submit")}
        </Button>
        <Button variant="ghost" onClick={() => setState("discarded")} disabled={pending}>
          {t("discard")}
        </Button>
      </div>
    </div>
  );
}
