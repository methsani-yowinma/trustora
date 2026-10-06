"use client";

import { BadgeCheck, Clock, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { type FormEvent, useRef } from "react";

import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, SelectField } from "@/components/ui/Field";
import { clientApi } from "@/lib/api/browser";
import type { OwnSocialAccount, SocialPlatform } from "@/lib/api/types";
import { useApiAction } from "@/lib/useApiAction";

const PLATFORMS: SocialPlatform[] = ["INSTAGRAM", "FACEBOOK", "TIKTOK", "WHATSAPP"];

export function SocialAccountsManager({ accounts }: { accounts: OwnSocialAccount[] }) {
  const t = useTranslations("sme.social");
  const tPlatform = useTranslations("platforms");
  const tCommon = useTranslations("common");
  const { run, pending, error } = useApiAction();
  const formRef = useRef<HTMLFormElement>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const url = String(form.get("url") ?? "").trim();
    const created = await run(() =>
      clientApi<OwnSocialAccount>("/smes/me/social-accounts", {
        method: "POST",
        body: { platform: form.get("platform"), handle: String(form.get("handle") ?? "").trim(), url: url || undefined },
      }),
    );
    if (created) formRef.current?.reset();
  }

  return (
    <Card className="space-y-5">
      <div className="space-y-1">
        <h2 className="font-semibold">{t("title")}</h2>
        <p className="text-sm text-ink-muted">{t("body")}</p>
      </div>

      {accounts.length === 0 ? (
        <p className="text-sm text-ink-muted">{t("empty")}</p>
      ) : (
        <ul className="divide-y divide-line rounded-lg border border-line">
          {accounts.map((account) => (
            <li key={account.id} className="flex flex-wrap items-center justify-between gap-3 p-3">
              <div className="space-y-1">
                <p className="text-sm font-medium">
                  {tPlatform(account.platform)} · @{account.handle}
                </p>
                {account.ownership_verified ? (
                  <Badge tone="verified" icon={<BadgeCheck aria-hidden="true" className="h-3.5 w-3.5" />}>
                    {t("confirmed")}
                  </Badge>
                ) : (
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <Badge tone="developing" icon={<Clock aria-hidden="true" className="h-3.5 w-3.5" />}>
                      {t("pending")}
                    </Badge>
                    <span className="text-ink-muted">{t("code")}:</span>
                    <code className="rounded bg-canvas px-1.5 py-0.5 font-mono text-xs select-all">
                      {account.verification_code}
                    </code>
                  </div>
                )}
              </div>
              <Button
                variant="ghost"
                disabled={pending}
                aria-label={`${tCommon("remove")} ${tPlatform(account.platform)} @${account.handle}`}
                onClick={() =>
                  run(() => clientApi(`/smes/me/social-accounts/${account.id}`, { method: "DELETE" }))
                }
              >
                <Trash2 aria-hidden="true" className="h-4 w-4" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <form ref={formRef} onSubmit={onSubmit} className="grid gap-3 sm:grid-cols-[10rem_1fr_1fr_auto] sm:items-end">
        <SelectField label={t("platform")} name="platform" defaultValue="INSTAGRAM">
          {PLATFORMS.map((platform) => (
            <option key={platform} value={platform}>
              {tPlatform(platform)}
            </option>
          ))}
        </SelectField>
        <Field label={t("handle")} name="handle" required minLength={2} maxLength={60} />
        <Field label={`${t("url")} (${tCommon("optional")})`} name="url" type="url" placeholder="https://" />
        <Button type="submit" disabled={pending}>
          {t("add")}
        </Button>
      </form>
      {error ? <Alert tone="error">{error}</Alert> : null}
    </Card>
  );
}
