"use client";

import { useTranslations } from "next-intl";
import { type FormEvent, useRef, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Field, SelectField, TextAreaField } from "@/components/ui/Field";
import { DOCUMENT_ACCEPT } from "@/components/ui/FileUploadButton";
import { clientApi } from "@/lib/api/browser";
import type { ComplaintCategory } from "@/lib/api/types";
import { useApiAction } from "@/lib/useApiAction";

const CATEGORIES: ComplaintCategory[] = [
  "DELIVERY",
  "WRONG_PRODUCT",
  "PRODUCT_AUTHENTICITY",
  "REFUND",
  "PAYMENT",
  "CUSTOMER_SERVICE",
  "PRODUCT_QUALITY",
  "OTHER",
];

const fileInputClasses =
  "[&_input]:file:mr-3 [&_input]:file:rounded-md [&_input]:file:border-0 [&_input]:file:bg-brand-50 [&_input]:file:px-3 [&_input]:file:py-1.5 [&_input]:file:text-brand-700";

/** Customer: raise a complaint about an order (multipart: fields + up to 3 files). */
export function ComplaintForm({ orderId }: { orderId: string }) {
  const t = useTranslations("complaints");
  const tCategory = useTranslations("complaintCategory");
  const { run, pending, error } = useApiAction();
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <Button variant="secondary" className="w-full" onClick={() => setOpen(true)}>
        {t("reportTitle")}
      </Button>
    );
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = new FormData(event.currentTarget);
    // Drop the empty file entry browsers send when no file is chosen.
    if (body.getAll("files").every((f) => f instanceof File && f.size === 0)) body.delete("files");
    await run(() => clientApi(`/orders/${orderId}/complaints`, { method: "POST", body }));
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div className="space-y-1">
        <h2 className="font-semibold">{t("reportTitle")}</h2>
        <p className="text-xs text-ink-muted">{t("reportBody")}</p>
      </div>
      <Alert>{t("allegationNotice")}</Alert>
      <SelectField label={t("category")} name="category" required defaultValue="">
        <option value="" disabled>
          {t("chooseCategory")}
        </option>
        {CATEGORIES.map((c) => (
          <option key={c} value={c}>
            {tCategory(c)}
          </option>
        ))}
      </SelectField>
      <TextAreaField label={t("description")} name="description" required minLength={10} maxLength={2000} hint={t("descriptionHint")} />
      <Field
        label={t("attachments")}
        name="files"
        type="file"
        multiple
        accept={DOCUMENT_ACCEPT}
        hint={t("attachmentsHint")}
        className={fileInputClasses}
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Button type="submit" disabled={pending} className="w-full">
        {t("submit")}
      </Button>
    </form>
  );
}

/** Customer controls on an existing complaint: resolve, escalate, add evidence. */
export function CustomerComplaintActions({ complaintId, actions }: { complaintId: string; actions: string[] }) {
  const t = useTranslations("complaints");
  const { run, pending, error } = useApiAction();
  if (actions.length === 0) return null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {actions.includes("resolve") ? (
          <Button disabled={pending} onClick={() => run(() => clientApi(`/complaints/${complaintId}/resolve`, { method: "POST" }))}>
            {t("resolve")}
          </Button>
        ) : null}
        {actions.includes("escalate") ? (
          <Button
            variant="secondary"
            disabled={pending}
            onClick={() => {
              if (window.confirm(t("escalateConfirm"))) {
                void run(() => clientApi(`/complaints/${complaintId}/escalate`, { method: "POST" }));
              }
            }}
          >
            {t("escalate")}
          </Button>
        ) : null}
      </div>
      {actions.includes("add_evidence") ? <EvidenceUpload path={`/complaints/${complaintId}/evidence`} /> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
    </div>
  );
}

/** Shared evidence upload for either party (customer or SME endpoint). */
export function EvidenceUpload({ path, hint }: { path: string; hint?: string }) {
  const t = useTranslations("complaints");
  const { run, pending, error } = useApiAction();
  const formRef = useRef<HTMLFormElement>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = new FormData(event.currentTarget);
    const done = await run(() => clientApi(path, { method: "POST", body }));
    if (done) formRef.current?.reset();
  }

  return (
    <form ref={formRef} onSubmit={onSubmit} className="space-y-2 rounded-lg border border-line p-3">
      <Field label={t("addEvidence")} name="files" type="file" multiple required accept={DOCUMENT_ACCEPT} hint={hint} className={fileInputClasses} />
      <Field label={t("evidenceNote")} name="description" maxLength={500} />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Button type="submit" variant="secondary" disabled={pending}>
        {t("addEvidence")}
      </Button>
    </form>
  );
}

/** SME: respond to a complaint. */
export function SmeComplaintResponse({ complaintId }: { complaintId: string }) {
  const t = useTranslations("smeComplaints");
  const { run, pending, error } = useApiAction();

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const response = String(new FormData(event.currentTarget).get("response") ?? "").trim();
    await run(() => clientApi(`/sme/complaints/${complaintId}/response`, { method: "POST", body: { response } }));
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <h2 className="font-semibold">{t("respondTitle")}</h2>
      <TextAreaField label={t("response")} name="response" required maxLength={2000} rows={4} />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Button type="submit" disabled={pending}>
        {t("submit")}
      </Button>
    </form>
  );
}

/** Admin: decide an open complaint. */
export function ComplaintDecisionForm({ complaintId }: { complaintId: string }) {
  const t = useTranslations("adminComplaints");
  const { run, pending, error } = useApiAction();
  const [noteError, setNoteError] = useState<string>();

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
    const note = String(new FormData(event.currentTarget).get("note") ?? "").trim();
    if (!note) {
      setNoteError(t("noteRequired"));
      return;
    }
    setNoteError(undefined);
    await run(() =>
      clientApi(`/admin/complaints/${complaintId}/decision`, {
        method: "POST",
        body: { decision: submitter?.value ?? "RESOLVED", note },
      }),
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div className="space-y-1">
        <h2 className="font-semibold">{t("decisionTitle")}</h2>
        <p className="text-xs text-ink-muted">{t("decisionHint")}</p>
      </div>
      <TextAreaField label={t("note")} name="note" rows={3} maxLength={1000} error={noteError} />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="flex flex-wrap gap-2">
        {(["UPHELD", "DISMISSED", "RESOLVED"] as const).map((decision) => (
          <Button
            key={decision}
            type="submit"
            value={decision}
            variant={decision === "UPHELD" ? "primary" : "secondary"}
            disabled={pending}
          >
            {t(decision)}
          </Button>
        ))}
      </div>
    </form>
  );
}
