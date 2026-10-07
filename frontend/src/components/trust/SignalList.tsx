import { CircleAlert, CircleCheck, Info } from "lucide-react";
import { useTranslations } from "next-intl";

import type { TrustSignal } from "@/lib/api/types";
import { cn } from "@/lib/cn";

import { ProvenanceBadge } from "./StatusBadges";

const KIND_ICON = {
  POSITIVE: { Icon: CircleCheck, className: "text-trust-verified" },
  RISK: { Icon: CircleAlert, className: "text-trust-caution" },
  INFO: { Icon: Info, className: "text-ink-muted" },
} as const;

type SignalValues = Record<string, string | number>;

/** Turns a signal's params into ICU message values (lists become localized, joined text). */
function useSignalText() {
  const t = useTranslations("trustSignals");
  const tPolicies = useTranslations("policies");

  return (signal: TrustSignal) => {
    const values: SignalValues = {};
    for (const [key, value] of Object.entries(signal.params)) {
      if (Array.isArray(value)) {
        values[key] = value
          .map((item) => (tPolicies.has(item as "returns") ? tPolicies(item as "returns") : String(item)))
          .join(", ");
      } else if (typeof value === "number" || typeof value === "string") {
        values[key] = value;
      }
    }
    const key = signal.code as Parameters<typeof t>[0];
    return t.has(key) ? t(key, values as never) : t("unknown");
  };
}

/** One group of trust signals ("why"), each with its source so facts and claims are never mixed up. */
export function SignalList({
  title,
  signals,
  emptyText,
}: {
  title: string;
  signals: TrustSignal[];
  emptyText: string;
}) {
  const text = useSignalText();
  const tPassport = useTranslations("passport");

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-semibold">{title}</h3>
      {signals.length === 0 ? (
        <p className="text-sm text-ink-muted">{emptyText}</p>
      ) : (
        <ul className="space-y-2">
          {signals.map((signal) => {
            const { Icon, className } = KIND_ICON[signal.kind];
            return (
              <li key={`${signal.dimension}-${signal.code}`} className="flex gap-3 rounded-lg border border-line p-3">
                <Icon aria-hidden="true" className={cn("mt-0.5 h-4 w-4 shrink-0", className)} />
                <div className="min-w-0 flex-1 space-y-1.5">
                  <p className="text-sm">{text(signal)}</p>
                  <div className="flex flex-wrap items-center gap-2">
                    <ProvenanceBadge provenance={signal.provenance} />
                    {signal.points !== 0 ? (
                      <span className="text-xs text-ink-muted tabular-nums">
                        {tPassport(signal.points > 0 ? "pointsGained" : "pointsLost", {
                          points: Math.abs(signal.points),
                        })}
                      </span>
                    ) : null}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
