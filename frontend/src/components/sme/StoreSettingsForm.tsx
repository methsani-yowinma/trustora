"use client";

import { BadgeCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field } from "@/components/ui/Field";
import { LocalizedFields, readLocalized } from "@/components/ui/LocalizedFields";
import { clientApi } from "@/lib/api/browser";
import type { PolicyKey, Sme, StorePolicies } from "@/lib/api/types";
import { useApiAction } from "@/lib/useApiAction";

const POLICY_KEYS: PolicyKey[] = ["returns", "refunds", "delivery"];

export function StoreSettingsForm({ sme }: { sme: Sme }) {
  const t = useTranslations("sme.store");
  const tOnboarding = useTranslations("sme.onboarding");
  const tPolicies = useTranslations("policies");
  const tCommon = useTranslations("common");
  const { run, pending, error } = useApiAction();
  const [saved, setSaved] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaved(false);
    const form = new FormData(event.currentTarget);
    const policies: StorePolicies = {};
    for (const key of POLICY_KEYS) {
      const value = readLocalized(form, `policy_${key}`);
      if (value) policies[key] = value;
    }
    const optional = (key: string) => String(form.get(key) ?? "").trim() || null;
    const result = await run(() =>
      clientApi<Sme>("/smes/me", {
        method: "PATCH",
        body: {
          name: String(form.get("name") ?? "").trim(),
          description_i18n: readLocalized(form, "description"),
          policies_i18n: policies,
          contact_phone: optional("contact_phone"),
          contact_email: optional("contact_email"),
        },
      }),
    );
    if (result) setSaved(true);
  }

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      <Card className="space-y-5">
        <h2 className="font-semibold">{t("profile")}</h2>
        <Field label={tOnboarding("name")} name="name" required minLength={2} maxLength={120} defaultValue={sme.name} />
        <LocalizedFields
          name="description"
          label={tOnboarding("description")}
          multiline
          maxLength={2000}
          defaultValue={sme.description_i18n}
        />
      </Card>

      <Card className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">{t("contact")}</h2>
          {sme.contact_verified ? (
            <span className="inline-flex items-center gap-1 text-sm text-trust-verified">
              <BadgeCheck aria-hidden="true" className="h-4 w-4" />
              {t("contactConfirmed")}
            </span>
          ) : null}
        </div>
        <p className="text-sm text-ink-muted">{t("contactHint")}</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label={tOnboarding("contactPhone")}
            name="contact_phone"
            type="tel"
            defaultValue={sme.contact_phone ?? ""}
          />
          <Field
            label={tOnboarding("contactEmail")}
            name="contact_email"
            type="email"
            defaultValue={sme.contact_email ?? ""}
          />
        </div>
      </Card>

      <Card className="space-y-5">
        <div className="space-y-1">
          <h2 className="font-semibold">{t("policiesTitle")}</h2>
          <p className="text-sm text-ink-muted">{t("policiesHint")}</p>
        </div>
        {POLICY_KEYS.map((key) => (
          <LocalizedFields
            key={key}
            name={`policy_${key}`}
            label={tPolicies(key)}
            multiline
            maxLength={2000}
            defaultValue={sme.policies_i18n[key]}
          />
        ))}
      </Card>

      {error ? <Alert tone="error">{error}</Alert> : null}
      {saved ? <Alert tone="success">{tCommon("saved")}</Alert> : null}
      <Button type="submit" disabled={pending}>
        {pending ? tCommon("saving") : tCommon("save")}
      </Button>
    </form>
  );
}
