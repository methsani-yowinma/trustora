import { getTranslations, setRequestLocale } from "next-intl/server";

import { OrderList } from "@/components/commerce/OrderList";
import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import type { Locale } from "@/i18n/routing";
import type { OrderSummary } from "@/lib/api/types";
import { requireRole, serverApi } from "@/lib/auth";

export default async function OrdersPage({ params }: PageProps<"/[locale]/orders">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);
  const guard = await requireRole(locale as Locale, ["CUSTOMER"], `/${locale}/orders`);
  if (guard.kind !== "allowed") return <AccessState kind={guard.kind} roles={["CUSTOMER"]} />;

  const t = await getTranslations("orders");
  const orders = await serverApi<OrderSummary[]>("/orders");
  return (
    <div className="space-y-6 py-8">
      <PageHeader title={t("title")} />
      <OrderList orders={orders} basePath="/orders" emptyText={t("empty")} />
    </div>
  );
}
