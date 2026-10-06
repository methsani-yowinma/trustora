import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type BadgeTone = "verified" | "trusted" | "developing" | "caution" | "risk" | "neutral";

const tones: Record<BadgeTone, string> = {
  verified: "border-trust-verified/25 bg-trust-verified/10 text-trust-verified",
  trusted: "border-trust-trusted/25 bg-trust-trusted/10 text-trust-trusted",
  developing: "border-trust-developing/25 bg-trust-developing/10 text-trust-developing",
  caution: "border-trust-caution/25 bg-trust-caution/10 text-trust-caution",
  risk: "border-trust-risk/25 bg-trust-risk/10 text-trust-risk",
  neutral: "border-line bg-canvas text-ink-muted",
};

/** Status pill. Always carries text (never colour alone) and an optional icon. */
export function Badge({
  tone = "neutral",
  icon,
  children,
  className,
}: {
  tone?: BadgeTone;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        tones[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}
