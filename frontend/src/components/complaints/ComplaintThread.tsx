import { useLocale, useTranslations } from "next-intl";

import { EvidenceList } from "@/components/trust/EvidenceList";
import { ProvenanceBadge } from "@/components/trust/StatusBadges";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import type { Complaint, ComplaintStatus } from "@/lib/api/types";
import { formatDate } from "@/lib/localize";

const STATUS_TONE: Record<ComplaintStatus, BadgeTone> = {
  SUBMITTED: "caution",
  SME_RESPONDED: "developing",
  UNDER_REVIEW: "trusted",
  RESOLVED: "verified",
  UPHELD: "risk",
  DISMISSED: "neutral",
};

export function ComplaintStatusBadge({ status }: { status: ComplaintStatus }) {
  const t = useTranslations("complaintStatus");
  return <Badge tone={STATUS_TONE[status]}>{t(status)}</Badge>;
}

/** The complaint as seen by its parties and admins. The customer's account is labelled as an allegation. */
export function ComplaintThread({ complaint }: { complaint: Complaint }) {
  const t = useTranslations("complaints");
  const tCategory = useTranslations("complaintCategory");
  const locale = useLocale();

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{tCategory(complaint.category)}</span>
        <ComplaintStatusBadge status={complaint.status} />
        <span className="text-xs text-ink-muted">{t("submittedOn", { date: formatDate(complaint.created_at, locale) })}</span>
      </div>

      <section className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-medium">{t("fromCustomer")}</h3>
          <ProvenanceBadge provenance="CUSTOMER_ALLEGATION" />
        </div>
        <p className="rounded-lg bg-canvas p-3 text-sm whitespace-pre-line">{complaint.description}</p>
      </section>

      <section className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-medium">{t("sellerResponse")}</h3>
          {complaint.sme_response ? <ProvenanceBadge provenance="SELLER_CLAIM" /> : null}
        </div>
        {complaint.sme_response ? (
          <p className="rounded-lg bg-canvas p-3 text-sm whitespace-pre-line">{complaint.sme_response}</p>
        ) : (
          <p className="text-sm text-ink-muted">{t("noResponse")}</p>
        )}
      </section>

      {complaint.resolution_note ? (
        <section className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-medium">{t("decision")}</h3>
            {complaint.status === "UPHELD" ? <ProvenanceBadge provenance="VERIFIED_FACT" /> : null}
          </div>
          <p className="rounded-lg border border-line p-3 text-sm">{complaint.resolution_note}</p>
        </section>
      ) : complaint.status === "UNDER_REVIEW" ? (
        <p className="text-sm text-ink-muted">{t("underReview")}</p>
      ) : null}

      <section className="space-y-1.5">
        <h3 className="text-sm font-medium">{t("evidenceTitle")}</h3>
        <EvidenceList items={complaint.evidence} emptyText={t("noEvidence")} />
      </section>
    </div>
  );
}
