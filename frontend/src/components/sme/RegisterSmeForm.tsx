"use client";

import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import { LocalizedFields, readLocalized } from "@/components/ui/LocalizedFields";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { clientApi } from "@/lib/api/browser";
import type { Sme } from "@/lib/api/types";
import { useApiAction } from "@/lib/useApiAction";

function suggestSlug(name: string): string {
  return name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
}

export function RegisterSmeForm() {
  const t = useTranslations("sme.onboarding");
  const { run, pending, error } = useApiAction();
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const optional = (key: string) => String(form.get(key) ?? "").trim() || undefined;
    await run(() =>
      clientApi<Sme>("/smes", {
        method: "POST",
        body: {
          name: String(form.get("name") ?? "").trim(),
          slug: slug.trim(),
          description_i18n: readLocalized(form, "description") ?? undefined,
          contact_phone: optional("contact_phone"),
          contact_email: optional("contact_email"),
        },
      }),
    );
  }

  return (
    <Card className="mx-auto max-w-2xl space-y-6 p-6 sm:p-8">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-ink-muted">{t("body")}</p>
      </div>
      <form onSubmit={onSubmit} className="space-y-5">
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Field
          label={t("name")}
          name="name"
          required
          minLength={2}
          maxLength={120}
          onChange={(event) => {
            if (!slugEdited) setSlug(suggestSlug(event.target.value));
          }}
        />
        <Field
          label={t("slug")}
          name="slug"
          required
          value={slug}
          pattern="[a-z0-9][a-z0-9\-]{1,38}[a-z0-9]"
          hint={t("slugHint", { slug: slug || "your-store" })}
          onChange={(event) => {
            setSlugEdited(true);
            setSlug(event.target.value.toLowerCase());
          }}
          autoCapitalize="none"
          spellCheck={false}
        />
        <LocalizedFields name="description" label={t("description")} multiline maxLength={2000} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("contactPhone")} name="contact_phone" type="tel" autoComplete="tel" placeholder="+94 77 123 4567" />
          <Field label={t("contactEmail")} name="contact_email" type="email" autoComplete="email" />
        </div>
        <Button type="submit" disabled={pending}>
          {t("submit")}
        </Button>
      </form>
    </Card>
  );
}
