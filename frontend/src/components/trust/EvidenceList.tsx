import { FileText } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import { AnalyzeButton } from "@/components/ai/AnalyzeButton";
import { AiAnalysisView } from "@/components/ai/AiViews";
import type { EvidenceFile } from "@/lib/api/types";
import { formatDate } from "@/lib/localize";

import { ProvenanceBadge, ReviewStatusBadge } from "./StatusBadges";

const ANALYZABLE = new Set(["BUSINESS_DOCUMENT", "PRODUCT_DOCUMENT", "PRODUCT_IMAGE"]);

/** Evidence with its provenance and review state, plus the integrity hash for auditability. */
export function EvidenceList({
  items,
  emptyText,
  adminAi = false,
}: {
  items: EvidenceFile[];
  emptyText: string;
  /** Admin views: show stored AI analyses and offer "Analyze with AI". */
  adminAi?: boolean;
}) {
  const t = useTranslations("admin.verifications");
  const locale = useLocale();

  if (items.length === 0) return <p className="text-sm text-ink-muted">{emptyText}</p>;

  return (
    <ul className="divide-y divide-line rounded-lg border border-line">
      {items.map((item) => (
        <li key={item.id} className="flex flex-wrap items-start justify-between gap-3 p-3 text-sm">
          <div className="flex min-w-0 gap-3">
            <FileText aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" />
            <div className="min-w-0 space-y-1">
              <p className="font-medium">{item.description ?? item.type}</p>
              <div className="flex flex-wrap gap-1.5">
                <ProvenanceBadge provenance={item.provenance} />
                <ReviewStatusBadge status={item.review_status} />
              </div>
              <p className="text-xs text-ink-muted">
                {formatDate(item.created_at, locale)}
                {item.sha256 ? (
                  <>
                    {" · "}
                    <span className="font-mono" title={item.sha256}>
                      SHA-256 {item.sha256.slice(0, 12)}…
                    </span>
                  </>
                ) : null}
              </p>
            </div>
          </div>
          {item.download_url ? (
            <a
              href={item.download_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-medium text-brand-700 hover:underline"
            >
              {t("openDocument")}
            </a>
          ) : null}
          {adminAi && ANALYZABLE.has(item.type) ? (
            <div className="w-full space-y-2">
              {item.ai_analysis ? <AiAnalysisView analysis={item.ai_analysis} /> : null}
              <AnalyzeButton evidenceId={item.id} again={Boolean(item.ai_analysis)} />
            </div>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
