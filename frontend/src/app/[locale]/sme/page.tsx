import { CheckCircle2, Circle, ExternalLink } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import { RegisterSmeForm } from "@/components/sme/RegisterSmeForm";
import { VerificationBadge } from "@/components/trust/StatusBadges";
import { Alert } from "@/components/ui/Alert";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Link } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";
import { requireSme } from "@/lib/sme";

export default async function SmeDashboardPage({ params }: PageProps<"/[locale]/sme">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);

  const guard = await requireSme(locale as Locale, `/${locale}/sme`, { allowOnboarding: true });
  if (guard.kind === "forbidden" || guard.kind === "unavailable") {
    return <AccessState kind={guard.kind} roles={["SME"]} />;
  }
  if (guard.kind === "onboarding") return <RegisterSmeForm />;

  const { sme } = guard;
  const t = await getTranslations("sme.dashboard");
  const confirmedSocial = sme.social_accounts.filter((a) => a.ownership_verified).length;
  const activeProducts = sme.product_counts.ACTIVE ?? 0;

  const steps = [
    { key: "logo", done: Boolean(sme.logo_url), href: "/sme/store" },
    { key: "policies", done: Object.keys(sme.policies_i18n).length > 0, href: "/sme/store" },
    { key: "social", done: confirmedSocial > 0, href: "/sme/store" },
    { key: "verification", done: sme.verification_status === "VERIFIED", href: "/sme/verification" },
    { key: "products", done: activeProducts > 0, href: "/sme/products/new" },
    { key: "publish", done: sme.is_published, href: "/sme/store" },
  ] as const;

  const stats = [
    { label: t("activeProducts"), value: activeProducts },
    { label: t("hiddenProducts"), value: sme.product_counts.HIDDEN ?? 0 },
    { label: t("linkedAccounts"), value: confirmedSocial },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={sme.name}
        description={<VerificationBadge status={sme.verification_status} />}
        actions={
          sme.is_published ? (
            <Link href={`/stores/${sme.slug}`} className={buttonClasses("secondary")}>
              <ExternalLink aria-hidden="true" className="h-4 w-4" />
              {t("viewStore")}
            </Link>
          ) : null
        }
      />
      {!sme.is_published ? <Alert>{t("notPublished")}</Alert> : null}

      <div className="grid gap-4 sm:grid-cols-3">
        {stats.map((stat) => (
          <Card key={stat.label} className="p-5">
            <p className="text-sm text-ink-muted">{stat.label}</p>
            <p className="mt-1 text-3xl font-semibold tabular-nums">{stat.value}</p>
          </Card>
        ))}
      </div>

      <Card className="space-y-4">
        <div className="space-y-1">
          <h2 className="font-semibold">{t("checklistTitle")}</h2>
          <p className="text-sm text-ink-muted">{t("checklistBody")}</p>
        </div>
        <ol className="space-y-2">
          {steps.map((step) => (
            <li key={step.key}>
              <Link
                href={step.href}
                className="flex items-center gap-3 rounded-lg px-2 py-2 text-sm hover:bg-canvas"
              >
                {step.done ? (
                  <CheckCircle2 aria-hidden="true" className="h-5 w-5 shrink-0 text-trust-verified" />
                ) : (
                  <Circle aria-hidden="true" className="h-5 w-5 shrink-0 text-ink-muted" />
                )}
                <span className={step.done ? "text-ink-muted line-through" : "font-medium"}>
                  {t(`steps.${step.key}`)}
                </span>
              </Link>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
