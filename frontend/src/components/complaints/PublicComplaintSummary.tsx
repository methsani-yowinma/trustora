import { useTranslations } from "next-intl";

import { ProvenanceBadge } from "@/components/trust/StatusBadges";
import { Card } from "@/components/ui/Card";
import type { ComplaintCategory, PublicComplaintSummary as Summary } from "@/lib/api/types";

/**
 * Public complaint record: categories and outcomes only. Open complaints are labelled as customer
 * allegations; only upheld complaints are shown as verified findings.
 */
export function PublicComplaintSummary({ summary }: { summary: Summary }) {
  const t = useTranslations("publicComplaints");
  const tCategory = useTranslations("complaintCategory");
  const open = Object.entries(summary.open_allegations) as [ComplaintCategory, number][];
  const upheld = Object.entries(summary.upheld) as [ComplaintCategory, number][];

  return (
    <Card className="space-y-3">
      <h2 className="font-semibold">{t("title")}</h2>
      {summary.total === 0 ? (
        <p className="text-sm text-ink-muted">{t("none")}</p>
      ) : (
        <ul className="space-y-2 text-sm">
          {upheld.map(([category, count]) => (
            <li key={`u-${category}`} className="flex flex-wrap items-center justify-between gap-2">
              <span>{t("upheld", { category: tCategory(category) })}</span>
              <span className="flex items-center gap-2">
                <ProvenanceBadge provenance="VERIFIED_FACT" />
                <span className="tabular-nums">{count}</span>
              </span>
            </li>
          ))}
          {open.map(([category, count]) => (
            <li key={`o-${category}`} className="flex flex-wrap items-center justify-between gap-2">
              <span>{t("open", { category: tCategory(category) })}</span>
              <span className="flex items-center gap-2">
                <ProvenanceBadge provenance="CUSTOMER_ALLEGATION" />
                <span className="tabular-nums">{t("openCount", { count })}</span>
              </span>
            </li>
          ))}
          {summary.resolved > 0 ? <li className="text-ink-muted">{t("resolved", { count: summary.resolved })}</li> : null}
          {summary.dismissed > 0 ? <li className="text-ink-muted">{t("dismissed", { count: summary.dismissed })}</li> : null}
        </ul>
      )}
      <p className="text-xs text-ink-muted">{t("explain")}</p>
    </Card>
  );
}
