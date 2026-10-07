"use client";

import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { TextAreaField } from "@/components/ui/Field";
import { clientApi } from "@/lib/api/browser";
import { useApiAction } from "@/lib/useApiAction";

export function EvidenceReviewForm({ evidenceId }: { evidenceId: string }) {
  const t = useTranslations("adminEvidence");
  const { run, pending, error } = useApiAction();
  const [noteError, setNoteError] = useState<string>();

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const decision = submitter?.value === "REJECTED" ? "REJECTED" : "ACCEPTED";
    const form = new FormData(event.currentTarget);
    const note = String(form.get("note") ?? "").trim();
    if (decision === "REJECTED" && !note) {
      setNoteError(t("noteRequired"));
      return;
    }
    setNoteError(undefined);
    await run(() =>
      clientApi(`/admin/evidence/${evidenceId}/review`, {
        method: "POST",
        body: {
          decision,
          misleading: decision === "REJECTED" && form.get("misleading") === "on",
          note: note || undefined,
        },
      }),
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <TextAreaField label={t("note")} name="note" rows={2} maxLength={1000} hint={t("noteRequired")} error={noteError} />
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" name="misleading" className="mt-0.5 h-4 w-4 accent-brand-600" />
        {t("misleading")}
      </label>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" value="ACCEPTED" disabled={pending}>
          {t("accept")}
        </Button>
        <Button type="submit" value="REJECTED" variant="secondary" disabled={pending}>
          {t("reject")}
        </Button>
      </div>
    </form>
  );
}
