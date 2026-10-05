import { useLocale, useTranslations } from "next-intl";

import { Card } from "@/components/ui/Card";
import type { EvidenceProvenance, Passport } from "@/lib/api/types";
import { formatDate } from "@/lib/localize";

import { SignalList } from "./SignalList";
import { ProvenanceBadge } from "./StatusBadges";
import { TrustHistoryChart } from "./TrustHistoryChart";
import { TrustScoreCard } from "./TrustScoreCard";

/** The body of a Digital Trust Passport, shared by the public page and the SME's own view. */
export function PassportView({ passport }: { passport: Passport }) {
  const t = useTranslations("passport");
  const locale = useLocale();
  const { trust, evidence_summary: evidence } = passport;
  const provenance = Object.entries(evidence.by_provenance) as [EvidenceProvenance, number][];

  return (
    <div className="space-y-6">
      <TrustScoreCard trust={trust} />

      <Card className="space-y-5">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold">{t("whyTitle")}</h2>
          <p className="text-sm text-ink-muted">{t("whyBody")}</p>
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <SignalList title={t("positive")} signals={passport.positive_signals} emptyText={t("noPositive")} />
          <div className="space-y-6">
            <SignalList title={t("risks")} signals={passport.risk_signals} emptyText={t("noRisks")} />
            {passport.info_signals.length > 0 ? (
              <SignalList title={t("info")} signals={passport.info_signals} emptyText="" />
            ) : null}
          </div>
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <Card className="space-y-3">
          <h2 className="font-semibold">{t("historyTitle", { days: passport.history.days })}</h2>
          <TrustHistoryChart history={passport.history} current={{ score: trust.overall_score, level: trust.level }} />
        </Card>

        <Card className="space-y-4">
          <h2 className="font-semibold">{t("evidenceTitle")}</h2>
          <dl className="grid grid-cols-3 gap-2 text-center">
            {[
              { label: t("evidenceTotal"), value: evidence.total },
              { label: t("evidenceAccepted"), value: evidence.accepted },
              { label: t("evidencePending"), value: evidence.pending },
            ].map((item) => (
              <div key={item.label} className="rounded-lg bg-canvas p-2">
                <dd className="text-xl font-semibold">{item.value}</dd>
                <dt className="text-xs text-ink-muted">{item.label}</dt>
              </div>
            ))}
          </dl>
          {provenance.length > 0 ? (
            <div className="space-y-2">
              <h3 className="text-sm font-medium">{t("evidenceBy")}</h3>
              <ul className="space-y-1.5">
                {provenance.map(([key, count]) => (
                  <li key={key} className="flex items-center justify-between gap-2 text-sm">
                    <ProvenanceBadge provenance={key} />
                    <span className="tabular-nums">{count}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </Card>
      </div>

      <div className="space-y-1 text-xs text-ink-muted">
        <p>{t("lastUpdate", { date: formatDate(trust.computed_at, locale) })}</p>
        <p>{t("methodology", { version: trust.rules_version })}</p>
        <p>{t("disclaimer")}</p>
      </div>
    </div>
  );
}
