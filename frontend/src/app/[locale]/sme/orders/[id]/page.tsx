import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { SmeOrderActions } from "@/components/commerce/OrderActions";
import { OrderDetail, OrderStatusBadge } from "@/components/commerce/OrderDetail";
import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import type { Locale } from "@/i18n/routing";
import { ApiError } from "@/lib/api/client";
import type { Order } from "@/lib/api/types";
import { serverApi } from "@/lib/auth";
import { formatDate } from "@/lib/localize";
import { requireSme } from "@/lib/sme";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function SmeOrderPage({ params }: PageProps<"/[locale]/sme/orders/[id]">) {
  const { locale, id } = await params;
  setRequestLocale(locale as Locale);
  if (!UUID.test(id)) notFound();
  const guard = await requireSme(locale as Locale, `/${locale}/sme/orders/${id}`);
  if (guard.kind !== "allowed") {
    return <AccessState kind={guard.kind === "forbidden" ? "forbidden" : "unavailable"} roles={["SME"]} />;
  }

  let order: Order;
  try {
    order = await serverApi<Order>(`/sme/orders/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const t = await getTranslations("orders");

  return (
    <div className="space-y-6">
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
        showCustomer
        actions={
          order.allowed_actions.length ? (
            <SmeOrderActions orderId={order.id} actions={order.allowed_actions} />
          ) : undefined
        }
      />
    </div>
  );
}
