"use client";

import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { TextAreaField } from "@/components/ui/Field";
import { clientApi } from "@/lib/api/browser";
import type { AdminVerificationDetail } from "@/lib/api/types";
import { useApiAction } from "@/lib/useApiAction";

export function VerificationDecisionForm({ verificationId }: { verificationId: string }) {
  const t = useTranslations("admin.verifications");
  const { run, pending, error } = useApiAction();
  const [noteError, setNoteError] = useState<string | undefined>();

  async function decide(event: FormEvent<HTMLFormElement>, decision: "APPROVED" | "REJECTED") {
    const form = new FormData(event.currentTarget);
    const note = String(form.get("note") ?? "").trim();
    if (decision === "REJECTED" && !note) {
      setNoteError(t("noteRequired"));
      return;
    }
    setNoteError(undefined);
    await run(() =>
      clientApi<AdminVerificationDetail>(`/admin/verifications/${verificationId}/decision`, {
        method: "POST",
        body: {
          decision,
          note: note || undefined,
          contact_verified: decision === "APPROVED" && form.get("contact_verified") === "on",
        },
      }),
    );
  }

  return (
    <Card className="space-y-4">
      <div className="space-y-1">
        <h2 className="font-semibold">{t("decisionTitle")}</h2>
        <p className="text-sm text-ink-muted">{t("decisionHint")}</p>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
          void decide(event, submitter?.value === "REJECTED" ? "REJECTED" : "APPROVED");
        }}
        className="space-y-4"
      >
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" name="contact_verified" className="h-4 w-4 accent-brand-600" />
          {t("contactVerified")}
        </label>
        <TextAreaField label={t("note")} name="note" rows={3} maxLength={1000} hint={t("noteRequired")} error={noteError} />
        {error ? <Alert tone="error">{error}</Alert> : null}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" name="decision" value="APPROVED" disabled={pending}>
            {t("approve")}
          </Button>
          <Button type="submit" name="decision" value="REJECTED" variant="secondary" disabled={pending}>
            {t("reject")}
          </Button>
        </div>
      </form>
    </Card>
  );
}
