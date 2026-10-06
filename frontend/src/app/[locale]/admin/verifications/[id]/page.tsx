import { ExternalLink } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { VerificationDecisionForm } from "@/components/admin/VerificationDecisionForm";
import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import { EvidenceList } from "@/components/trust/EvidenceList";
import { VerificationBadge } from "@/components/trust/StatusBadges";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Link } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";
import { ApiError } from "@/lib/api/client";
import type { AdminVerificationDetail } from "@/lib/api/types";
import { requireRole, serverApi } from "@/lib/auth";
import { formatDate } from "@/lib/localize";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function AdminVerificationDetailPage({
  params,
}: PageProps<"/[locale]/admin/verifications/[id]">) {
  const { locale, id } = await params;
  setRequestLocale(locale as Locale);
  if (!UUID.test(id)) notFound();

  const guard = await requireRole(locale as Locale, ["ADMIN"], `/${locale}/admin/verifications/${id}`);
  if (guard.kind !== "allowed") return <AccessState kind={guard.kind} roles={["ADMIN"]} />;

  let detail: AdminVerificationDetail;
  try {
    detail = await serverApi<AdminVerificationDetail>(`/admin/verifications/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const t = await getTranslations("admin.verifications");
  const tSme = await getTranslations("sme.verification");
  const tOnboarding = await getTranslations("sme.onboarding");

  const facts = [
    { label: t("registeredName"), value: detail.registered_name },
    { label: t("regNumber"), value: detail.business_reg_number, mono: true },
    { label: t("storeName"), value: detail.sme.name },
    { label: tOnboarding("contactPhone"), value: detail.sme.contact_phone ?? "—" },
    { label: tOnboarding("contactEmail"), value: detail.sme.contact_email ?? "—" },
    { label: t("submitted"), value: formatDate(detail.submitted_at, locale) },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={detail.sme.name}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <VerificationBadge status={detail.sme.verification_status} />
            <Link href={`/stores/${detail.sme.slug}`} className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline">
              /stores/{detail.sme.slug}
              <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
            </Link>
          </span>
        }
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-6">
          <Card>
            <dl className="grid gap-4 sm:grid-cols-2">
              {facts.map((fact) => (
                <div key={fact.label}>
                  <dt className="text-sm text-ink-muted">{fact.label}</dt>
                  <dd className={fact.mono ? "font-mono" : "font-medium"}>{fact.value}</dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold">{t("documents")}</h2>
              <p className="text-xs text-ink-muted">{t("linkExpires")}</p>
            </div>
            <EvidenceList items={detail.documents} emptyText="—" adminAi />
          </Card>

          {detail.history.length > 0 ? (
            <Card className="space-y-3">
              <h2 className="font-semibold">{t("history")}</h2>
              <ul className="space-y-2 text-sm">
                {detail.history.map((item) => (
                  <li key={item.id} className="flex flex-wrap items-center gap-2">
                    <Badge tone={item.status === "APPROVED" ? "verified" : item.status === "REJECTED" ? "caution" : "developing"}>
                      {tSme(`decision.${item.status}`)}
                    </Badge>
                    <span>{formatDate(item.submitted_at, locale)}</span>
                    {item.decision_note ? <span className="text-ink-muted">— {item.decision_note}</span> : null}
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
        </div>

        {detail.status === "SUBMITTED" ? (
          <VerificationDecisionForm verificationId={detail.id} />
        ) : (
          <Card className="space-y-2">
            <h2 className="font-semibold">{t("decisionTitle")}</h2>
            <Badge tone={detail.status === "APPROVED" ? "verified" : "caution"}>{tSme(`decision.${detail.status}`)}</Badge>
            {detail.reviewed_at ? (
              <p className="text-sm text-ink-muted">{t("decided", { date: formatDate(detail.reviewed_at, locale) })}</p>
            ) : null}
            {detail.decision_note ? <p className="text-sm">{detail.decision_note}</p> : null}
          </Card>
        )}
      </div>
    </div>
  );
}
