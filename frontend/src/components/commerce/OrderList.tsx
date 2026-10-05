import { useLocale, useTranslations } from "next-intl";

import { Card } from "@/components/ui/Card";
import { Link } from "@/i18n/navigation";
import type { OrderSummary } from "@/lib/api/types";
import { formatDate, formatLkr } from "@/lib/localize";

import { OrderStatusBadge } from "./OrderDetail";

export function OrderList({
  orders,
  basePath,
  emptyText,
}: {
  orders: OrderSummary[];
  basePath: "/orders" | "/sme/orders";
  emptyText: string;
}) {
  const t = useTranslations("orders");
  const tDelivery = useTranslations("deliveryStatus");
  const locale = useLocale();

  if (orders.length === 0) return <Card className="text-center text-ink-muted">{emptyText}</Card>;

  return (
    <ul className="space-y-3">
      {orders.map((order) => (
        <li key={order.id}>
          <Link href={`${basePath}/${order.id}`} className="block">
            <Card className="flex flex-wrap items-center justify-between gap-3 p-4 transition-shadow hover:shadow-md">
              <div className="space-y-1">
                <p className="font-medium">
                  {t("order", { number: order.order_number })} · {order.store_name}
                </p>
                <p className="text-sm text-ink-muted">
                  {t("placedOn", { date: formatDate(order.placed_at, locale) })} · {t("items", { count: order.item_count })} ·{" "}
                  {tDelivery(order.delivery_status)}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <OrderStatusBadge status={order.status} />
                <span className="font-semibold tabular-nums">{formatLkr(order.total_lkr, locale)}</span>
              </div>
            </Card>
          </Link>
        </li>
      ))}
    </ul>
  );
}
