import { getTranslations, setRequestLocale } from "next-intl/server";

import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import { ProfileSummary } from "@/components/layout/ProfileSummary";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Link } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";
import type { AdminSocialAccount, AdminVerificationItem } from "@/lib/api/types";
import { requireRole, serverApi } from "@/lib/auth";

export default async function AdminDashboardPage({ params }: PageProps<"/[locale]/admin">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);

  const guard = await requireRole(locale as Locale, ["ADMIN"], `/${locale}/admin`);
  if (guard.kind !== "allowed") return <AccessState kind={guard.kind} roles={["ADMIN"]} />;

  const [t, tDashboard] = await Promise.all([
    getTranslations("admin.dashboard"),
    getTranslations("dashboard"),
  ]);
  const [verifications, social] = await Promise.all([
    serverApi<AdminVerificationItem[]>("/admin/verifications?status=SUBMITTED"),
    serverApi<AdminSocialAccount[]>("/admin/social-accounts?pending=true"),
  ]);

  const queues = [
    { label: t("pendingVerifications"), count: verifications.length },
    { label: t("pendingSocial"), count: social.length },
  ];

  return (
    <div className="space-y-6">
      <PageHeader title={tDashboard("adminTitle")} description={tDashboard("adminBody")} />
      <div className="grid gap-4 sm:grid-cols-2">
        {queues.map((queue) => (
          <Card key={queue.label} className="flex items-center justify-between gap-4 p-5">
            <div>
              <p className="text-sm text-ink-muted">{queue.label}</p>
              <p className="mt-1 text-3xl font-semibold tabular-nums">{queue.count}</p>
            </div>
            <Link href="/admin/verifications" className={buttonClasses("secondary")}>
              {t("review")}
            </Link>
          </Card>
        ))}
      </div>
      <ProfileSummary profile={guard.profile} />
    </div>
  );
}
