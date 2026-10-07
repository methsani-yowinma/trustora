import { getTranslations, setRequestLocale } from "next-intl/server";

import { OrderList } from "@/components/commerce/OrderList";
import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import { Link } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";
import type { OrderStatus, OrderSummary } from "@/lib/api/types";
import { serverApi } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { requireSme } from "@/lib/sme";

const FILTERS: OrderStatus[] = [
  "PLACED",
  "CONFIRMED",
  "DISPATCHED",
  "DELIVERED",
  "COMPLETED",
  "CANCELLED",
  "DELIVERY_FAILED",
];

export default async function SmeOrdersPage({ params, searchParams }: PageProps<"/[locale]/sme/orders">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);
  const guard = await requireSme(locale as Locale, `/${locale}/sme/orders`);
  if (guard.kind !== "allowed") {
    return <AccessState kind={guard.kind === "forbidden" ? "forbidden" : "unavailable"} roles={["SME"]} />;
  }
  const requested = (await searchParams).status;
  const status = FILTERS.find((f) => f === requested);
  const [t, tStatus] = await Promise.all([getTranslations("smeOrders"), getTranslations("orderStatus")]);
  const orders = await serverApi<OrderSummary[]>(`/sme/orders${status ? `?status=${status}` : ""}`);

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={t("trustNote")} />
      <nav aria-label={t("title")} className="flex flex-wrap gap-2">
        {[undefined, ...FILTERS].map((filter) => (
          <Link
            key={filter ?? "all"}
            href={filter ? { pathname: "/sme/orders", query: { status: filter } } : "/sme/orders"}
            aria-current={filter === status ? "page" : undefined}
            className={cn(
              "rounded-full border px-3 py-1 text-sm",
              filter === status ? "border-brand-600 bg-brand-50 text-brand-700" : "border-line text-ink-muted",
            )}
          >
            {filter ? tStatus(filter) : t("all")}
          </Link>
        ))}
      </nav>
      <OrderList orders={orders} basePath="/sme/orders" emptyText={t("empty")} />
    </div>
  );
}
