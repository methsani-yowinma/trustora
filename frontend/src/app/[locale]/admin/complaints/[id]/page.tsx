import { ExternalLink } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { ComplaintDecisionForm } from "@/components/complaints/ComplaintForms";
import { ComplaintThread } from "@/components/complaints/ComplaintThread";
import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Card } from "@/components/ui/Card";
import { Link } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";
import { ApiError } from "@/lib/api/client";
import type { Complaint } from "@/lib/api/types";
import { requireRole, serverApi } from "@/lib/auth";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function AdminComplaintPage({ params }: PageProps<"/[locale]/admin/complaints/[id]">) {
  const { locale, id } = await params;
  setRequestLocale(locale as Locale);
  if (!UUID.test(id)) notFound();
  const guard = await requireRole(locale as Locale, ["ADMIN"], `/${locale}/admin/complaints/${id}`);
  if (guard.kind !== "allowed") return <AccessState kind={guard.kind} roles={["ADMIN"]} />;

  let complaint: Complaint;
  try {
    complaint = await serverApi<Complaint>(`/admin/complaints/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const [t, tOrders] = await Promise.all([getTranslations("adminComplaints"), getTranslations("orders")]);

  return (
    <div className="space-y-6">
      <PageHeader
        title={tOrders("order", { number: complaint.order_number })}
        description={
          <Link href={`/stores/${complaint.store_slug}/passport`} className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline">
            {t("store")}: {complaint.store_name}
            <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
          </Link>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <Card>
          <ComplaintThread complaint={complaint} />
        </Card>
        {complaint.allowed_actions.includes("decide") ? (
          <Card>
            <ComplaintDecisionForm complaintId={complaint.id} />
          </Card>
        ) : null}
      </div>
    </div>
  );
}
