import { CheckCircle2, Circle, XCircle } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Link } from "@/i18n/navigation";
import type { Order, OrderStatus } from "@/lib/api/types";
import { formatDate, formatLkr, localizedString } from "@/lib/localize";

import { StoreTrustLine } from "./ProductCardView";

const STATUS_TONE: Record<OrderStatus, BadgeTone> = {
  PLACED: "developing",
  CONFIRMED: "trusted",
  DISPATCHED: "trusted",
  DELIVERED: "verified",
  COMPLETED: "verified",
  CANCELLED: "neutral",
  DELIVERY_FAILED: "risk",
};

export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  const t = useTranslations("orderStatus");
  return <Badge tone={STATUS_TONE[status]}>{t(status)}</Badge>;
}

function dateTime(value: string, locale: string) {
  return new Intl.DateTimeFormat(locale === "si" ? "si-LK" : "en-LK", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

/** Delivery tracking as a timeline of what has actually happened (no invented steps). */
function Timeline({ order }: { order: Order }) {
  const t = useTranslations("orders");
  const locale = useLocale();
  const d = order.delivery;

  type Step = { label: string; at: string | null; failed?: boolean };
  const steps: Step[] = [
    { label: t("stepPlaced"), at: order.placed_at },
    { label: t("stepConfirmed"), at: order.confirmed_at },
    { label: t("stepDispatched"), at: d.dispatched_at },
    { label: t("stepInTransit"), at: d.in_transit_at },
    { label: t("stepDelivered"), at: d.delivered_at },
    { label: t("stepCompleted"), at: order.completed_at },
  ];
  let shown = steps;
  if (order.status === "CANCELLED") {
    shown = [
      ...steps.filter((s) => s.at),
      { label: t("stepCancelled", { by: t(`cancelledBy.${order.cancelled_by ?? "CUSTOMER"}`) }), at: order.cancelled_at, failed: true },
    ];
  } else if (order.status === "DELIVERY_FAILED") {
    shown = [...steps.filter((s) => s.at), { label: t("stepFailed"), at: d.failed_at, failed: true }];
  } else {
    // Skip the optional "in transit" step if the order went straight to delivered.
    shown = steps.filter((s) => s.label !== t("stepInTransit") || s.at || !d.delivered_at);
  }

  return (
    <ol className="space-y-3">
      {shown.map((step) => {
        const Icon = step.failed ? XCircle : step.at ? CheckCircle2 : Circle;
        return (
          <li key={step.label} className="flex items-start gap-3 text-sm">
            <Icon
              aria-hidden="true"
              className={`mt-0.5 h-4 w-4 shrink-0 ${step.failed ? "text-trust-risk" : step.at ? "text-trust-verified" : "text-ink-muted"}`}
            />
            <div>
              <p className={step.at ? "font-medium" : "text-ink-muted"}>{step.label}</p>
              {step.at ? <p className="text-xs text-ink-muted">{dateTime(step.at, locale)}</p> : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-3 text-sm">
      <dt className="text-ink-muted">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

/** Full order view shared by the customer and SME pages; `actions` are role-specific controls. */
export function OrderDetail({ order, actions, showCustomer = false }: { order: Order; actions?: ReactNode; showCustomer?: boolean }) {
  const t = useTranslations("orders");
  const tDelivery = useTranslations("deliveryStatus");
  const tPayment = useTranslations("paymentStatus");
  const tCheckout = useTranslations("checkout");
  const tCart = useTranslations("cart");
  const tDistricts = useTranslations("districts");
  const tProduct = useTranslations("product");
  const locale = useLocale();
  const d = order.delivery;
  const address = order.shipping_address;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
      <div className="space-y-6">
        <Card className="space-y-3">
          <h2 className="font-semibold">{t("itemsTitle")}</h2>
          <ul className="divide-y divide-line text-sm">
            {order.items.map((item) => (
              <li key={item.product_id} className="flex justify-between gap-3 py-2">
                <span>
                  {localizedString(item.product_name_i18n, locale)} × {item.quantity}
                </span>
                <span className="tabular-nums">{formatLkr(item.line_total_lkr, locale)}</span>
              </li>
            ))}
          </ul>
          <dl className="space-y-1 border-t border-line pt-2">
            <Row label={t("delivery")}>{formatLkr(order.delivery_fee_lkr, locale)}</Row>
            <div className="flex justify-between text-base font-semibold">
              <dt>{tCart("total")}</dt>
              <dd className="tabular-nums">{formatLkr(order.total_lkr, locale)}</dd>
            </div>
          </dl>
        </Card>

        <Card className="space-y-3">
          <h2 className="font-semibold">{t("timeline")}</h2>
          <Timeline order={order} />
          {order.cancellation_reason ? (
            <p className="rounded-lg bg-canvas p-2 text-sm">
              {t("reason")}: {order.cancellation_reason}
            </p>
          ) : null}
          {d.failure_reason ? (
            <p className="rounded-lg bg-canvas p-2 text-sm">
              {t("reason")}: {d.failure_reason}
            </p>
          ) : null}
        </Card>
      </div>

      <div className="space-y-6">
        {actions ? <Card className="space-y-3">{actions}</Card> : null}

        <Card className="space-y-3">
          <h2 className="font-semibold">{t("delivery")}</h2>
          <dl className="space-y-2">
            <Row label={t("provider")}>{d.provider_code === "SIMULATED" ? t("providerSIMULATED") : d.provider_code}</Row>
            <Row label={tCheckout("district")}>{tDistricts.has(d.district as "COLOMBO") ? tDistricts(d.district as "COLOMBO") : d.district}</Row>
            <Row label={t("delivery")}>{tDelivery(d.status)}</Row>
            {d.tracking_ref ? (
              <Row label={t("tracking")}>
                <span className="font-mono">{d.tracking_ref}</span>
              </Row>
            ) : null}
            <Row label={t("eta")}>
              {d.estimated_delivery_date ? formatDate(d.estimated_delivery_date, locale) : t("etaPending", { days: d.eta_days })}
            </Row>
          </dl>
        </Card>

        <Card className="space-y-3">
          <h2 className="font-semibold">{t("payment")}</h2>
          <dl className="space-y-2">
            <Row label={t("method")}>{order.payment.method === "COD" ? tCheckout("cod") : tCheckout("mockCard")}</Row>
            <Row label={t("payment")}>{tPayment(order.payment.status)}</Row>
            {order.payment.mock_reference ? (
              <Row label={t("reference")}>
                <span className="font-mono">{order.payment.mock_reference}</span>
              </Row>
            ) : null}
          </dl>
        </Card>

        <Card className="space-y-3">
          <h2 className="font-semibold">{showCustomer ? t("shipTo") : t("store")}</h2>
          {showCustomer ? (
            <address className="text-sm not-italic">
              {address.recipient_name}
              <br />
              {address.address_line1}
              {address.address_line2 ? (
                <>
                  <br />
                  {address.address_line2}
                </>
              ) : null}
              <br />
              {address.city}
              {address.postal_code ? ` ${address.postal_code}` : ""}
              <br />
              {address.phone}
            </address>
          ) : (
            <>
              <StoreTrustLine store={order.store} />
              <Link href={`/stores/${order.store.slug}/passport`} className="text-sm text-brand-700 hover:underline">
                {tProduct("viewPassport")}
              </Link>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
