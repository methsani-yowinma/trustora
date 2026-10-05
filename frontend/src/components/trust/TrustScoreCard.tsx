import { useTranslations } from "next-intl";

import { Card } from "@/components/ui/Card";
import type { TrustDimension, TrustScore } from "@/lib/api/types";
import { cn } from "@/lib/cn";

import { TrustLevelBadge } from "./TrustLevel";

const DIMENSIONS: { key: TrustDimension; field: keyof TrustScore }[] = [
  { key: "BUSINESS", field: "business_score" },
  { key: "PRODUCT", field: "product_score" },
  { key: "TRANSACTION", field: "transaction_score" },
];

/**
 * Meter fill carries severity; the track is a lighter step of the same ramp. The neutral middle
 * (e.g. 50 = "no evidence yet") uses the developing tone, not a warning colour.
 */
function meterColor(score: number) {
  if (score < 40) return { fill: "bg-trust-risk", track: "bg-trust-risk/15" };
  if (score < 70) return { fill: "bg-trust-developing", track: "bg-trust-developing/15" };
  return { fill: "bg-brand-600", track: "bg-brand-100" };
}

export function DimensionMeter({ label, question, score }: { label: string; question?: string; score: number }) {
  const { fill, track } = meterColor(score);
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="font-medium">{label}</span>
        <span className="font-semibold tabular-nums">{score}</span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={score}
        className={cn("h-2 overflow-hidden rounded-full", track)}
      >
        <div className={cn("h-full rounded-full", fill)} style={{ width: `${score}%` }} />
      </div>
      {question ? <p className="text-xs text-ink-muted">{question}</p> : null}
    </div>
  );
}

/** Hero score + level + the three dimensions. */
export function TrustScoreCard({ trust, compact = false }: { trust: TrustScore; compact?: boolean }) {
  const t = useTranslations("passport");
  const tLevel = useTranslations("trustLevel");
  const tDim = useTranslations("trustDimension");

  return (
    <Card className={cn("grid gap-6", compact ? "md:grid-cols-[auto_1fr]" : "lg:grid-cols-[16rem_1fr]")}>
      <div className="space-y-2">
        <p className="text-sm text-ink-muted">{t("overall")}</p>
        <p className="flex items-baseline gap-2">
          <span className="text-5xl font-semibold tracking-tight">{trust.overall_score}</span>
          <span className="text-sm text-ink-muted">{t("outOf")}</span>
        </p>
        <TrustLevelBadge level={trust.level} />
        {!compact ? <p className="text-sm text-ink-muted">{tLevel(`${trust.level}.description`)}</p> : null}
      </div>
      <div className="space-y-4">
        {!compact ? <h2 className="text-sm font-semibold">{t("dimensions")}</h2> : null}
        {DIMENSIONS.map(({ key, field }) => (
          <DimensionMeter
            key={key}
            label={tDim(key)}
            question={compact ? undefined : tDim(`${key}_question`)}
            score={trust[field] as number}
          />
        ))}
      </div>
    </Card>
  );
}
