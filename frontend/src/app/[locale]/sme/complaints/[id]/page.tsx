import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { EvidenceUpload, SmeComplaintResponse } from "@/components/complaints/ComplaintForms";
import { ComplaintThread } from "@/components/complaints/ComplaintThread";
import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/Card";
import type { Locale } from "@/i18n/routing";
import { ApiError } from "@/lib/api/client";
import type { Complaint } from "@/lib/api/types";
import { serverApi } from "@/lib/auth";
import { requireSme } from "@/lib/sme";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function SmeComplaintPage({ params }: PageProps<"/[locale]/sme/complaints/[id]">) {
  const { locale, id } = await params;
  setRequestLocale(locale as Locale);
  if (!UUID.test(id)) notFound();
  const guard = await requireSme(locale as Locale, `/${locale}/sme/complaints/${id}`);
  if (guard.kind !== "allowed") {
    return <AccessState kind={guard.kind === "forbidden" ? "forbidden" : "unavailable"} roles={["SME"]} />;
  }

  let complaint: Complaint;
  try {
    complaint = await serverApi<Complaint>(`/sme/complaints/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const [t, tOrders] = await Promise.all([getTranslations("smeComplaints"), getTranslations("orders")]);

  return (
    <div className="space-y-6">
      <PageHeader title={tOrders("order", { number: complaint.order_number })} />
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <Card>
          <ComplaintThread complaint={complaint} />
        </Card>
        <div className="space-y-6">
          {complaint.allowed_actions.includes("respond") ? (
            <Card>
              <SmeComplaintResponse complaintId={complaint.id} />
            </Card>
          ) : null}
          {complaint.allowed_actions.includes("add_evidence") ? (
            <Card>
              <EvidenceUpload path={`/sme/complaints/${complaint.id}/evidence`} hint={t("evidenceHint")} />
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}
