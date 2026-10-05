import { CircleAlert, CircleCheck, Info } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type Tone = "info" | "success" | "error";

const tones: Record<Tone, { box: string; Icon: typeof Info }> = {
  info: { box: "border-line bg-canvas text-ink", Icon: Info },
  success: { box: "border-brand-100 bg-brand-50 text-brand-900", Icon: CircleCheck },
  error: { box: "border-trust-risk/30 bg-trust-risk/5 text-trust-risk", Icon: CircleAlert },
};

export function Alert({ tone = "info", title, children }: { tone?: Tone; title?: string; children?: ReactNode }) {
  const { box, Icon } = tones[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cn("flex gap-3 rounded-lg border p-4 text-sm", box)}>
      <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="space-y-1">
        {title ? <p className="font-medium">{title}</p> : null}
        {children ? <div>{children}</div> : null}
      </div>
    </div>
  );
}
