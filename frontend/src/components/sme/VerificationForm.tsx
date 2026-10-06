"use client";

import { useTranslations } from "next-intl";
import { type FormEvent } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { DOCUMENT_ACCEPT } from "@/components/ui/FileUploadButton";
import { clientApi } from "@/lib/api/browser";
import type { Verification } from "@/lib/api/types";
import { useApiAction } from "@/lib/useApiAction";

export function VerificationForm() {
  const t = useTranslations("sme.verification");
  const { run, pending, error } = useApiAction();

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Files and text fields are sent as multipart; the API validates file contents.
    const body = new FormData(event.currentTarget);
    await run(() => clientApi<Verification>("/smes/me/verification", { method: "POST", body }));
  }

  return (
    <Card>
      <form onSubmit={onSubmit} className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label={t("regNumber")}
            name="business_reg_number"
            required
            pattern="[A-Za-z0-9/ \-]{3,40}"
            placeholder="PV 00123456"
          />
          <Field label={t("registeredName")} name="registered_name" required minLength={2} maxLength={160} />
        </div>
        <Field
          label={t("documents")}
          name="documents"
          type="file"
          accept={DOCUMENT_ACCEPT}
          multiple
          required
          hint={t("documentsHint")}
          className="[&_input]:file:mr-3 [&_input]:file:rounded-md [&_input]:file:border-0 [&_input]:file:bg-brand-50 [&_input]:file:px-3 [&_input]:file:py-1.5 [&_input]:file:text-brand-700"
        />
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Button type="submit" disabled={pending}>
          {t("submit")}
        </Button>
      </form>
    </Card>
  );
}
