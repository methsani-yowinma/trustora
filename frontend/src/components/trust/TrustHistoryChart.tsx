"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";

import type { TrustHistory, TrustLevel } from "@/lib/api/types";
import { formatDate } from "@/lib/localize";

const HEIGHT = 180;
const MARGIN = { top: 12, right: 12, bottom: 26, left: 32 };
// Level thresholds from the trust methodology, drawn as recessive reference lines.
const THRESHOLDS = [40, 55, 70];
const Y_TICKS = [0, 40, 55, 70, 100];

type Point = { at: number; score: number; level: TrustLevel };

/**
 * Single-series step line of the overall trust score (scores change at discrete events).
 * One hue, no legend (the title names the series), crosshair + tooltip on hover/focus,
 * and a table view so no value depends on hovering.
 */
export function TrustHistoryChart({ history, current }: { history: TrustHistory; current: { score: number; level: TrustLevel } }) {
  const t = useTranslations("passport");
  const tLevel = useTranslations("trustLevel");
  const locale = useLocale();
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [active, setActive] = useState<number | null>(null);
  // Fixed once per mount so rendering stays pure; the series ends at "now".
  const [now] = useState(() => Date.now());

  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const { points, start, end } = useMemo(() => {
    const windowStart = now - history.days * 86_400_000;
    const series: Point[] = history.points.map((p) => ({
      at: new Date(p.at).getTime(),
      score: p.overall_score,
      level: p.level,
    }));
    // The score in effect when the window opened is drawn from the window's left edge.
    if (history.baseline) {
      series.unshift({ at: windowStart, score: history.baseline.overall_score, level: history.baseline.level });
    }
    // Stores younger than the window start at their first score rather than an empty stretch.
    return { points: series, start: series.length ? series[0].at : windowStart, end: now };
  }, [history, now]);

  const change = history.change;
  const summary = !change
    ? t("historyEmpty")
    : change.to_score > change.from_score
      ? t("historyIncreased", { from: change.from_score, to: change.to_score, days: history.days })
      : change.to_score < change.from_score
        ? t("historyDecreased", { from: change.from_score, to: change.to_score, days: history.days })
        : t("historyUnchanged", { to: change.to_score, days: history.days });

  const plotWidth = Math.max(0, width - MARGIN.left - MARGIN.right);
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const x = (at: number) => MARGIN.left + ((at - start) / Math.max(1, end - start)) * plotWidth;
  const y = (score: number) => MARGIN.top + (1 - score / 100) * plotHeight;

  let path = "";
  points.forEach((p, i) => {
    path += i === 0 ? `M${x(p.at)},${y(p.score)}` : `H${x(p.at)}V${y(p.score)}`;
  });
  if (points.length) path += `H${x(end)}`;

  function onPointerMove(event: React.PointerEvent<SVGSVGElement>) {
    if (!points.length) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const px = event.clientX - rect.left;
    let nearest = 0;
    points.forEach((p, i) => {
      if (Math.abs(x(p.at) - px) < Math.abs(x(points[nearest].at) - px)) nearest = i;
    });
    setActive(nearest);
  }

  const activePoint = active !== null ? points[active] : null;

  return (
    <div className="space-y-3">
      <p className="text-sm">{summary}</p>
      {points.length > 0 ? (
        <div ref={container} className="relative">
          {width > 0 ? (
            <svg
              width={width}
              height={HEIGHT}
              role="img"
              aria-label={`${t("chartLabel")}. ${summary}`}
              onPointerMove={onPointerMove}
              onPointerLeave={() => setActive(null)}
              className="touch-pan-y"
            >
              {Y_TICKS.map((tick) => (
                <g key={tick}>
                  <line
                    x1={MARGIN.left}
                    x2={MARGIN.left + plotWidth}
                    y1={y(tick)}
                    y2={y(tick)}
                    stroke="var(--color-line)"
                    strokeDasharray={THRESHOLDS.includes(tick) ? "3 4" : undefined}
                  />
                  <text x={MARGIN.left - 6} y={y(tick)} dy="0.32em" textAnchor="end" className="fill-ink-muted text-[10px] tabular-nums">
                    {tick}
                  </text>
                </g>
              ))}
              <text x={MARGIN.left} y={HEIGHT - 6} className="fill-ink-muted text-[10px]">
                {formatDate(new Date(start).toISOString(), locale)}
              </text>
              <text x={MARGIN.left + plotWidth} y={HEIGHT - 6} textAnchor="end" className="fill-ink-muted text-[10px]">
                {formatDate(new Date(end).toISOString(), locale)}
              </text>

              <path d={path} fill="none" stroke="var(--color-brand-600)" strokeWidth={2} strokeLinejoin="round" />

              {activePoint ? (
                <line
                  x1={x(activePoint.at)}
                  x2={x(activePoint.at)}
                  y1={MARGIN.top}
                  y2={MARGIN.top + plotHeight}
                  stroke="var(--color-ink-muted)"
                  strokeWidth={1}
                />
              ) : null}

              {points.map((p, i) => (
                <g
                  key={p.at}
                  tabIndex={0}
                  role="button"
                  aria-label={`${formatDate(new Date(p.at).toISOString(), locale)}: ${p.score} — ${tLevel(`${p.level}.label`)}`}
                  onFocus={() => setActive(i)}
                  onBlur={() => setActive(null)}
                  className="outline-none"
                >
                  {/* Transparent hit area larger than the mark. */}
                  <circle cx={x(p.at)} cy={y(p.score)} r={12} fill="transparent" />
                  <circle
                    cx={x(p.at)}
                    cy={y(p.score)}
                    r={active === i ? 6 : 4}
                    fill="var(--color-brand-600)"
                    stroke="var(--color-surface)"
                    strokeWidth={2}
                  />
                </g>
              ))}
            </svg>
          ) : (
            <div style={{ height: HEIGHT }} />
          )}

          {activePoint ? (
            <div
              role="status"
              className="pointer-events-none absolute top-0 rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-[var(--shadow-card)]"
              style={{
                left: Math.min(Math.max(0, x(activePoint.at) - 70), Math.max(0, width - 150)),
              }}
            >
              <p className="text-base font-semibold text-ink">{activePoint.score}</p>
              <p className="text-ink">{tLevel(`${activePoint.level}.label`)}</p>
              <p className="text-ink-muted">{formatDate(new Date(activePoint.at).toISOString(), locale)}</p>
            </div>
          ) : null}
        </div>
      ) : null}

      {history.points.length > 0 ? (
        <details className="text-sm">
          <summary className="cursor-pointer text-brand-700">{t("showTable")}</summary>
          <table className="mt-2 w-full text-left">
            <thead className="text-ink-muted">
              <tr>
                <th className="py-1 font-medium">{t("tableDate")}</th>
                <th className="py-1 font-medium">{t("tableScore")}</th>
                <th className="py-1 font-medium">{t("tableLevel")}</th>
              </tr>
            </thead>
            <tbody>
              {history.points.map((p) => (
                <tr key={p.at} className="border-t border-line">
                  <td className="py-1">{formatDate(p.at, locale)}</td>
                  <td className="py-1 tabular-nums">{p.overall_score}</td>
                  <td className="py-1">{tLevel(`${p.level}.label`)}</td>
                </tr>
              ))}
              <tr className="border-t border-line">
                <td className="py-1">{formatDate(new Date(now).toISOString(), locale)}</td>
                <td className="py-1 tabular-nums">{current.score}</td>
                <td className="py-1">{tLevel(`${current.level}.label`)}</td>
              </tr>
            </tbody>
          </table>
        </details>
      ) : null}
    </div>
  );
}
