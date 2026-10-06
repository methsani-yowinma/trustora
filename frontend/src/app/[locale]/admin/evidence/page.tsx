import { getTranslations, setRequestLocale } from "next-intl/server";

import { EvidenceReviewForm } from "@/components/admin/EvidenceReviewForm";
import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import { EvidenceList } from "@/components/trust/EvidenceList";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Link } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";
import type { AdminEvidenceItem, EvidenceReviewStatus } from "@/lib/api/types";
import { requireRole, serverApi } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { localizedString } from "@/lib/localize";

const FILTERS: EvidenceReviewStatus[] = ["PENDING", "ACCEPTED", "REJECTED"];

export default async function AdminEvidencePage({ params, searchParams }: PageProps<"/[locale]/admin/evidence">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);
  const requested = (await searchParams).status;
  const status = FILTERS.find((f) => f === requested) ?? "PENDING";

  const guard = await requireRole(locale as Locale, ["ADMIN"], `/${locale}/admin/evidence`);
  if (guard.kind !== "allowed") return <AccessState kind={guard.kind} roles={["ADMIN"]} />;

  const t = await getTranslations("adminEvidence");
  const items = await serverApi<AdminEvidenceItem[]>(`/admin/evidence?status=${status}`);

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("body")} />

      <nav aria-label={t("title")} className="flex flex-wrap gap-2">
        {FILTERS.map((filter) => (
          <Link
            key={filter}
            aria-current={filter === status ? "page" : undefined}
            href={{ pathname: "/admin/evidence", query: { status: filter } }}
            className={cn(
              "rounded-full border px-3 py-1 text-sm",
              filter === status ? "border-brand-600 bg-brand-50 text-brand-700" : "border-line text-ink-muted",
            )}
          >
            {t(`filter${filter}`)}
          </Link>
        ))}
      </nav>

      {items.length === 0 ? (
        <Card className="text-sm text-ink-muted">{t("empty")}</Card>
      ) : (
        <ul className="space-y-4">
          {items.map((item) => (
            <li key={item.id}>
              <Card className="grid gap-5 lg:grid-cols-[1fr_22rem]">
                <div className="space-y-3">
                  <dl className="grid gap-3 text-sm sm:grid-cols-2">
                    <div>
                      <dt className="text-ink-muted">{t("store")}</dt>
                      <dd className="font-medium">{item.sme_name}</dd>
                    </div>
                    {item.product_name_i18n ? (
                      <div>
                        <dt className="text-ink-muted">{t("product")}</dt>
                        <dd className="font-medium">{localizedString(item.product_name_i18n, locale)}</dd>
                      </div>
                    ) : null}
                  </dl>
                  <EvidenceList items={[item]} emptyText="" adminAi />
                  {item.flagged_misleading ? <Badge tone="risk">{t("flaggedMisleading")}</Badge> : null}
                  {item.review_note ? <p className="text-sm text-ink-muted">{item.review_note}</p> : null}
                </div>
                {item.review_status === "PENDING" ? <EvidenceReviewForm evidenceId={item.id} /> : null}
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
