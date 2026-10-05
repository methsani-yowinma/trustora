import { getTranslations, setRequestLocale } from "next-intl/server";

import { AccessState } from "@/components/layout/AccessState";
import { ProfileSummary } from "@/components/layout/ProfileSummary";
import { Alert } from "@/components/ui/Alert";
import type { Locale } from "@/i18n/routing";
import { requireRole } from "@/lib/auth";

export default async function SmeDashboardPage({ params }: PageProps<"/[locale]/sme">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);

  const guard = await requireRole(locale as Locale, ["SME"], `/${locale}/sme`);
  if (guard.kind !== "allowed") return <AccessState kind={guard.kind} roles={["SME"]} />;

  const t = await getTranslations("dashboard");
  return (
    <div className="space-y-6 py-10">
      <div className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight">{t("smeTitle")}</h1>
        <p className="text-ink-muted">{t("smeBody")}</p>
      </div>
      <ProfileSummary profile={guard.profile} />
      <Alert>{t("comingSoon")}</Alert>
    </div>
  );
}
