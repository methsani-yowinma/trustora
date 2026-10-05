import { getTranslations, setRequestLocale } from "next-intl/server";

import { SocialReviewList } from "@/components/admin/SocialReviewList";
import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/Card";
import { Link } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";
import type { AdminSocialAccount, AdminVerificationItem, VerificationDecision } from "@/lib/api/types";
import { requireRole, serverApi } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/localize";

const FILTERS: VerificationDecision[] = ["SUBMITTED", "APPROVED", "REJECTED"];

export default async function AdminVerificationsPage({
  params,
  searchParams,
}: PageProps<"/[locale]/admin/verifications">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);
  const requested = (await searchParams).status;
  const status = FILTERS.find((f) => f === requested) ?? "SUBMITTED";

  const guard = await requireRole(locale as Locale, ["ADMIN"], `/${locale}/admin/verifications`);
  if (guard.kind !== "allowed") return <AccessState kind={guard.kind} roles={["ADMIN"]} />;

  const t = await getTranslations("admin.verifications");
  const [items, social] = await Promise.all([
    serverApi<AdminVerificationItem[]>(`/admin/verifications?status=${status}`),
    serverApi<AdminSocialAccount[]>("/admin/social-accounts?pending=true"),
  ]);

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} />

      <nav aria-label={t("title")} className="flex flex-wrap gap-2">
        {FILTERS.map((filter) => (
          <Link
            key={filter}
            aria-current={filter === status ? "page" : undefined}
            href={{ pathname: "/admin/verifications", query: { status: filter } }}
            className={cn(
              "rounded-full border px-3 py-1 text-sm",
              filter === status ? "border-brand-600 bg-brand-50 text-brand-700" : "border-line text-ink-muted",
            )}
          >
            {t(`filter${filter}`)}
          </Link>
        ))}
      </nav>

      <Card className="p-0">
        {items.length === 0 ? (
          <p className="p-6 text-sm text-ink-muted">{t("queueEmpty")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-line text-ink-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">{t("storeName")}</th>
                  <th className="px-4 py-3 font-medium">{t("registeredName")}</th>
                  <th className="px-4 py-3 font-medium">{t("regNumber")}</th>
                  <th className="px-4 py-3 font-medium">{t("submitted")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {items.map((item) => (
                  <tr key={item.id}>
                    <td className="px-4 py-3">
                      <Link href={`/admin/verifications/${item.id}`} className="font-medium text-brand-700 hover:underline">
                        {item.sme_name}
                      </Link>
                    </td>
                    <td className="px-4 py-3">{item.registered_name}</td>
                    <td className="px-4 py-3 font-mono">{item.business_reg_number}</td>
                    <td className="px-4 py-3 whitespace-nowrap">{formatDate(item.submitted_at, locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <SocialReviewList accounts={social} />
    </div>
  );
}
