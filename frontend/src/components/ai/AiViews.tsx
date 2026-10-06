import { Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";

import { ProvenanceBadge } from "@/components/trust/StatusBadges";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import type { AiAnalysis, TrustExplanation } from "@/lib/api/types";

/** Shopper-facing summary. AI text is always labelled, with a reminder that AI did not score. */
export function AiSummaryCard({ explanation }: { explanation: TrustExplanation }) {
  const t = useTranslations("ai");
  const isAi = explanation.source === "AI";
  return (
    <Card className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-semibold">{t("summaryTitle")}</h2>
        {isAi ? (
          <Badge tone="developing" icon={<Sparkles aria-hidden="true" className="h-3.5 w-3.5" />}>
            {t("aiSummary")}
          </Badge>
        ) : null}
      </div>
      <p lang={explanation.locale} className="text-ink">
        {explanation.text}
      </p>
      <p className="text-xs text-ink-muted">{isAi ? t("aiNote") : t("templateNote")}</p>
    </Card>
  );
}

const CHECK_TONE: Record<string, BadgeTone> = {
  MATCH: "verified",
  PARTIAL: "caution",
  MISMATCH: "risk",
  NOT_FOUND: "neutral",
};

const DOCUMENT_FIELDS = [
  "document_type",
  "business_name",
  "registration_number",
  "issue_date",
  "issuer",
  "product_names",
  "legibility",
  "notes",
] as const;

/** Admin view of a stored analysis (documents and complaint triage). */
export function AiAnalysisView({ analysis }: { analysis: AiAnalysis }) {
  const t = useTranslations("ai");
  const tCategory = useTranslations("complaintCategory");

  const header = (
    <div className="flex flex-wrap items-center gap-2">
      <Sparkles aria-hidden="true" className="h-4 w-4 text-trust-developing" />
      <span className="text-sm font-medium">{analysis.kind === "COMPLAINT" ? t("triage") : t("analysis")}</span>
      <ProvenanceBadge provenance="AI_ANALYSIS" />
      <span className="text-xs text-ink-muted">{analysis.model}</span>
    </div>
  );

  if (analysis.status !== "DONE" || !analysis.output) {
    return (
      <div className="space-y-1 rounded-lg border border-dashed border-line p-3">
        {header}
        <p className="text-sm text-ink-muted">{analysis.status === "SKIPPED" ? t("skipped") : t("failed")}</p>
      </div>
    );
  }
  const out = analysis.output as Record<string, unknown>;

  if (analysis.kind === "COMPLAINT") {
    const rows = [
      { label: t("suggestedCategory"), value: tCategory(out.category as "OTHER") },
      { label: t("severity"), value: t(`severityValue.${out.severity as "LOW"}`) },
      { label: t("sentiment"), value: t(`sentimentValue.${out.sentiment as "NEUTRAL"}`) },
    ];
    return (
      <div className="space-y-2 rounded-lg border border-dashed border-trust-developing/40 p-3">
        {header}
        <dl className="grid gap-2 text-sm sm:grid-cols-3">
          {rows.map((row) => (
            <div key={row.label}>
              <dt className="text-xs text-ink-muted">{row.label}</dt>
              <dd className="font-medium">{row.value}</dd>
            </div>
          ))}
        </dl>
        {out.summary ? <p className="text-sm">{String(out.summary)}</p> : null}
        <p className="text-xs text-ink-muted">{t("triageNote")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-lg border border-dashed border-trust-developing/40 p-3">
      {header}
      {analysis.checks && Object.keys(analysis.checks).length > 0 ? (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-ink-muted">{t("checks")}</p>
          <ul className="flex flex-wrap gap-2">
            {Object.entries(analysis.checks).map(([key, result]) => (
              <li key={key}>
                <Badge tone={CHECK_TONE[result] ?? "neutral"}>
                  {t(`check.${key as "registered_name"}`)}: {t(`checkResult.${result}`)}
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="space-y-1.5">
        <p className="text-xs font-medium text-ink-muted">{t("extracted")}</p>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          {DOCUMENT_FIELDS.filter((f) => out[f] !== null && out[f] !== undefined && out[f] !== "" && !(Array.isArray(out[f]) && !(out[f] as unknown[]).length)).map((field) => (
            <div key={field}>
              <dt className="text-xs text-ink-muted">{t(`field.${field}`)}</dt>
              <dd className="break-words">{Array.isArray(out[field]) ? (out[field] as string[]).join(", ") : String(out[field])}</dd>
            </div>
          ))}
        </dl>
      </div>
      <p className="text-xs text-ink-muted">{t("analysisNote")}</p>
    </div>
  );
}
