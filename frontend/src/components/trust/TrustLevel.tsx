import { BadgeCheck, CircleAlert, ShieldAlert, ShieldCheck, Sprout } from "lucide-react";
import { useTranslations } from "next-intl";

import { Badge, type BadgeTone } from "@/components/ui/Badge";
import type { TrustLevel } from "@/lib/api/types";

export const LEVEL_STYLE: Record<TrustLevel, { tone: BadgeTone; Icon: typeof BadgeCheck; color: string }> = {
  VERIFIED: { tone: "verified", Icon: BadgeCheck, color: "var(--color-trust-verified)" },
  TRUSTED: { tone: "trusted", Icon: ShieldCheck, color: "var(--color-trust-trusted)" },
  DEVELOPING: { tone: "developing", Icon: Sprout, color: "var(--color-trust-developing)" },
  CAUTION: { tone: "caution", Icon: CircleAlert, color: "var(--color-trust-caution)" },
  HIGH_RISK: { tone: "risk", Icon: ShieldAlert, color: "var(--color-trust-risk)" },
};

/** Trust level: always icon + text, never colour alone. */
export function TrustLevelBadge({ level }: { level: TrustLevel }) {
  const t = useTranslations("trustLevel");
  const { tone, Icon } = LEVEL_STYLE[level];
  return (
    <Badge tone={tone} icon={<Icon aria-hidden="true" className="h-3.5 w-3.5" />}>
      {t(`${level}.label`)}
    </Badge>
  );
}
