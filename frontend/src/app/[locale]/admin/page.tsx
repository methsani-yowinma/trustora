import { getTranslations, setRequestLocale } from "next-intl/server";

import { AccessState } from "@/components/layout/AccessState";
import { ProfileSummary } from "@/components/layout/ProfileSummary";
import { Alert } from "@/components/ui/Alert";
import type { Locale } from "@/i18n/routing";
import { requireRole } from "@/lib/auth";

export default async function AdminDashboardPage({ params }: PageProps<"/[locale]/admin">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);

  const guard = await requireRole(locale as Locale, ["ADMIN"], `/${locale}/admin`);
  if (guard.kind !== "allowed") return <AccessState kind={guard.kind} roles={["ADMIN"]} />;

  const t = await getTranslations("dashboard");
  return (
    <div className="space-y-6 py-10">
      <div className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight">{t("adminTitle")}</h1>
        <p className="text-ink-muted">{t("adminBody")}</p>
      </div>
      <ProfileSummary profile={guard.profile} />
      <Alert>{t("comingSoon")}</Alert>
    </div>
  );
}
