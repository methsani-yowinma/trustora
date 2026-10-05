"use client";

import { ExternalLink } from "lucide-react";
import { useTranslations } from "next-intl";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { clientApi } from "@/lib/api/browser";
import type { AdminSocialAccount } from "@/lib/api/types";
import { useApiAction } from "@/lib/useApiAction";

export function SocialReviewList({ accounts }: { accounts: AdminSocialAccount[] }) {
  const t = useTranslations("admin.social");
  const tPlatform = useTranslations("platforms");
  const tSocial = useTranslations("sme.social");
  const { run, pending, error } = useApiAction();

  return (
    <Card className="space-y-4">
      <div className="space-y-1">
        <h2 className="font-semibold">{t("title")}</h2>
        <p className="text-sm text-ink-muted">{t("body")}</p>
      </div>
      {accounts.length === 0 ? (
        <p className="text-sm text-ink-muted">{t("empty")}</p>
      ) : (
        <ul className="divide-y divide-line rounded-lg border border-line">
          {accounts.map((account) => (
            <li key={account.id} className="flex flex-wrap items-center justify-between gap-3 p-3 text-sm">
              <div className="space-y-1">
                <p className="font-medium">
                  {account.sme_name} — {tPlatform(account.platform)} · @{account.handle}
                </p>
                <p className="text-ink-muted">
                  {tSocial("code")}: <code className="font-mono">{account.verification_code}</code>
                </p>
                {account.url ? (
                  <a
                    href={account.url}
                    target="_blank"
                    rel="noopener noreferrer nofollow"
                    className="inline-flex items-center gap-1 text-brand-700 hover:underline"
                  >
                    {account.url}
                    <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
                  </a>
                ) : null}
              </div>
              <Button
                disabled={pending}
                onClick={() =>
                  run(() =>
                    clientApi(`/admin/social-accounts/${account.id}/decision`, {
                      method: "POST",
                      body: { verified: true },
                    }),
                  )
                }
              >
                {t("confirm")}
              </Button>
            </li>
          ))}
        </ul>
      )}
      {error ? <Alert tone="error">{error}</Alert> : null}
    </Card>
  );
}
