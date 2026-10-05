import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { CustomerOrderActions } from "@/components/commerce/OrderActions";
import { OrderDetail, OrderStatusBadge } from "@/components/commerce/OrderDetail";
import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import type { Locale } from "@/i18n/routing";
import { ApiError } from "@/lib/api/client";
import type { Order } from "@/lib/api/types";
import { requireRole, serverApi } from "@/lib/auth";
import { formatDate } from "@/lib/localize";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function OrderPage({ params }: PageProps<"/[locale]/orders/[id]">) {
  const { locale, id } = await params;
  setRequestLocale(locale as Locale);
  if (!UUID.test(id)) notFound();
  const guard = await requireRole(locale as Locale, ["CUSTOMER"], `/${locale}/orders/${id}`);
  if (guard.kind !== "allowed") return <AccessState kind={guard.kind} roles={["CUSTOMER"]} />;

  let order: Order;
  try {
    order = await serverApi<Order>(`/orders/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const t = await getTranslations("orders");

  return (
    <div className="space-y-6 py-8">
      <PageHeader
        title={t("order", { number: order.order_number })}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <OrderStatusBadge status={order.status} />
            <span>{t("placedOn", { date: formatDate(order.placed_at, locale) })}</span>
          </span>
        }
      />
      <OrderDetail
        order={order}
        actions={
          order.allowed_actions.length ? (
            <CustomerOrderActions orderId={order.id} actions={order.allowed_actions} />
          ) : undefined
        }
      />
    </div>
  );
}
