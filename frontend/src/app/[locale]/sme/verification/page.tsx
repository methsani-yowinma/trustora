import { getTranslations, setRequestLocale } from "next-intl/server";

import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import { VerificationForm } from "@/components/sme/VerificationForm";
import { EvidenceList } from "@/components/trust/EvidenceList";
import { VerificationBadge } from "@/components/trust/StatusBadges";
import { Alert } from "@/components/ui/Alert";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import type { Locale } from "@/i18n/routing";
import type { Verification } from "@/lib/api/types";
import { serverApi } from "@/lib/auth";
import { formatDate } from "@/lib/localize";
import { requireSme } from "@/lib/sme";

export default async function SmeVerificationPage({ params }: PageProps<"/[locale]/sme/verification">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);

  const guard = await requireSme(locale as Locale, `/${locale}/sme/verification`);
  if (guard.kind !== "allowed") {
    return <AccessState kind={guard.kind === "forbidden" ? "forbidden" : "unavailable"} roles={["SME"]} />;
  }
  const { sme } = guard;
  const t = await getTranslations("sme.verification");
  const history = await serverApi<Verification[]>("/smes/me/verification");
  const canSubmit = sme.verification_status === "UNVERIFIED" || sme.verification_status === "REJECTED";

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("title")}
        description={<VerificationBadge status={sme.verification_status} />}
      />

      {sme.verification_status === "PENDING" ? <Alert>{t("pendingNotice")}</Alert> : null}
      {sme.verification_status === "VERIFIED" ? <Alert tone="success">{t("verifiedNotice")}</Alert> : null}
      {sme.verification_status === "REJECTED" ? <Alert tone="error">{t("rejectedNotice")}</Alert> : null}

      {canSubmit ? (
        <section className="space-y-3">
          <p className="max-w-2xl text-sm text-ink-muted">{t("body")}</p>
          <VerificationForm />
        </section>
      ) : null}

      {history.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">{t("history")}</h2>
          {history.map((item) => (
            <Card key={item.id} className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="font-medium">{item.registered_name}</p>
                  <p className="text-sm text-ink-muted">
                    {item.business_reg_number} · {t("submittedOn", { date: formatDate(item.submitted_at, locale) })}
                  </p>
                </div>
                <Badge
                  tone={item.status === "APPROVED" ? "verified" : item.status === "REJECTED" ? "caution" : "developing"}
                >
                  {t(`decision.${item.status}`)}
                </Badge>
              </div>
              {item.decision_note ? (
                <p className="rounded-lg bg-canvas p-3 text-sm">
                  <span className="font-medium">{t("note")}: </span>
                  {item.decision_note}
                </p>
              ) : null}
              <EvidenceList items={item.documents} emptyText="" />
            </Card>
          ))}
        </section>
      ) : null}
    </div>
  );
}
