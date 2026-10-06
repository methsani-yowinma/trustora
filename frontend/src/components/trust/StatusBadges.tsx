import { BadgeCheck, CircleAlert, CircleDashed, Clock, ShieldAlert, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";

import { Badge, type BadgeTone } from "@/components/ui/Badge";
import type {
  AuthenticityStatus,
  EvidenceProvenance,
  EvidenceReviewStatus,
  VerificationStatus,
} from "@/lib/api/types";

const icon = "h-3.5 w-3.5";

const VERIFICATION: Record<VerificationStatus, { tone: BadgeTone; Icon: typeof BadgeCheck }> = {
  VERIFIED: { tone: "verified", Icon: BadgeCheck },
  PENDING: { tone: "developing", Icon: Clock },
  UNVERIFIED: { tone: "neutral", Icon: CircleDashed },
  REJECTED: { tone: "caution", Icon: CircleAlert },
};

export function VerificationBadge({ status }: { status: VerificationStatus }) {
  const t = useTranslations("verificationStatus");
  const { tone, Icon } = VERIFICATION[status];
  return (
    <Badge tone={tone} icon={<Icon aria-hidden="true" className={icon} />}>
      {t(status)}
    </Badge>
  );
}

const AUTHENTICITY: Record<AuthenticityStatus, { tone: BadgeTone; Icon: typeof BadgeCheck }> = {
  VERIFIED: { tone: "verified", Icon: ShieldCheck },
  PARTIALLY_VERIFIED: { tone: "trusted", Icon: ShieldCheck },
  UNVERIFIED: { tone: "neutral", Icon: CircleDashed },
  CONCERN: { tone: "risk", Icon: ShieldAlert },
};

export function AuthenticityBadge({ status }: { status: AuthenticityStatus }) {
  const t = useTranslations("authenticity");
  const { tone, Icon } = AUTHENTICITY[status];
  return (
    <Badge tone={tone} icon={<Icon aria-hidden="true" className={icon} />}>
      {t(status)}
    </Badge>
  );
}

const PROVENANCE_TONE: Record<EvidenceProvenance, BadgeTone> = {
  VERIFIED_FACT: "verified",
  SELLER_CLAIM: "neutral",
  CUSTOMER_ALLEGATION: "caution",
  PUBLIC_EVIDENCE: "trusted",
  AI_ANALYSIS: "developing",
  PLATFORM_STATISTIC: "trusted",
};

/** Distinguishes verified facts from claims, allegations and AI analysis everywhere evidence appears. */
export function ProvenanceBadge({ provenance }: { provenance: EvidenceProvenance }) {
  const t = useTranslations("provenance");
  return <Badge tone={PROVENANCE_TONE[provenance]}>{t(provenance)}</Badge>;
}

const REVIEW_TONE: Record<EvidenceReviewStatus, BadgeTone> = {
  PENDING: "developing",
  ACCEPTED: "verified",
  REJECTED: "caution",
};

export function ReviewStatusBadge({ status }: { status: EvidenceReviewStatus }) {
  const t = useTranslations("reviewStatus");
  return <Badge tone={REVIEW_TONE[status]}>{t(status)}</Badge>;
}
