import { getTranslations, setRequestLocale } from "next-intl/server";

import { ComplaintList, StatusFilter } from "@/components/complaints/ComplaintList";
import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import type { Locale } from "@/i18n/routing";
import type { ComplaintStatus, ComplaintSummary } from "@/lib/api/types";
import { requireRole, serverApi } from "@/lib/auth";

const STATUSES: ComplaintStatus[] = ["UNDER_REVIEW", "SUBMITTED", "SME_RESPONDED", "UPHELD", "DISMISSED", "RESOLVED"];

export default async function AdminComplaintsPage({ params, searchParams }: PageProps<"/[locale]/admin/complaints">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);
  const guard = await requireRole(locale as Locale, ["ADMIN"], `/${locale}/admin/complaints`);
  if (guard.kind !== "allowed") return <AccessState kind={guard.kind} roles={["ADMIN"]} />;

  const requested = (await searchParams).status;
  const status = STATUSES.find((s) => s === requested) ?? "UNDER_REVIEW";
  const t = await getTranslations("adminComplaints");
  const items = await serverApi<ComplaintSummary[]>(`/admin/complaints?status=${status}`);

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} />
      <StatusFilter
        basePath="/admin/complaints"
        statuses={STATUSES}
        current={status}
        label={t("title")}
        labelFor={(s) => t(`filter${s}`)}
      />
      <ComplaintList items={items} basePath="/admin/complaints" emptyText={t("empty")} />
    </div>
  );
}
