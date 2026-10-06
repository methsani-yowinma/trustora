import { cn } from "@/lib/cn";

/**
 * Trustora AI identity: the Trustora shield and tick, plus a four-point "AI" spark in place of
 * the logo's signal node. The spark twinkles occasionally when `animated` (respects reduced motion).
 */
export function TrustoraAiMark({ className, animated = false }: { className?: string; animated?: boolean }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn("h-7 w-7", className)}>
      <path
        d="M15 4 4.5 8.2v7.4c0 6.6 4.5 11.4 10.5 13.3 6-1.9 10.5-6.7 10.5-13.3V8.2L15 4Z"
        fill="var(--color-brand-500)"
      />
      <path
        d="m10 16.1 3.4 3.4 6.6-6.8"
        fill="none"
        stroke="#fff"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M25.5 1.5c.4 2.6 1.4 3.6 4 4-2.6.4-3.6 1.4-4 4-.4-2.6-1.4-3.6-4-4 2.6-.4 3.6-1.4 4-4Z"
        fill="var(--color-brand-100)"
        className={cn(animated && "animate-ai-twinkle")}
        style={{ transformBox: "fill-box", transformOrigin: "center" }}
      />
    </svg>
  );
}
