import { getTranslations, setRequestLocale } from "next-intl/server";

import { ComplaintList, StatusFilter } from "@/components/complaints/ComplaintList";
import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import type { Locale } from "@/i18n/routing";
import type { ComplaintStatus, ComplaintSummary } from "@/lib/api/types";
import { serverApi } from "@/lib/auth";
import { requireSme } from "@/lib/sme";

const STATUSES: ComplaintStatus[] = ["SUBMITTED", "SME_RESPONDED", "UNDER_REVIEW", "RESOLVED", "UPHELD", "DISMISSED"];

export default async function SmeComplaintsPage({ params, searchParams }: PageProps<"/[locale]/sme/complaints">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);
  const guard = await requireSme(locale as Locale, `/${locale}/sme/complaints`);
  if (guard.kind !== "allowed") {
    return <AccessState kind={guard.kind === "forbidden" ? "forbidden" : "unavailable"} roles={["SME"]} />;
  }
  const requested = (await searchParams).status;
  const status = STATUSES.find((s) => s === requested);
  const [t, tStatus] = await Promise.all([getTranslations("smeComplaints"), getTranslations("complaintStatus")]);
  const items = await serverApi<ComplaintSummary[]>(`/sme/complaints${status ? `?status=${status}` : ""}`);

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("body")} />
      <StatusFilter
        basePath="/sme/complaints"
        statuses={STATUSES}
        current={status}
        allLabel={t("all")}
        label={t("title")}
        labelFor={(s) => tStatus(s)}
      />
      <ComplaintList items={items} basePath="/sme/complaints" emptyText={t("empty")} />
    </div>
  );
}
