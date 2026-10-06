import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { CustomerOrderActions } from "@/components/commerce/OrderActions";
import { ComplaintForm, CustomerComplaintActions } from "@/components/complaints/ComplaintForms";
import { ComplaintThread } from "@/components/complaints/ComplaintThread";
import { ReviewForm } from "@/components/reviews/ReviewForm";
import { ReviewItem } from "@/components/reviews/Reviews";
import { Card } from "@/components/ui/Card";
import { OrderDetail, OrderStatusBadge } from "@/components/commerce/OrderDetail";
import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import type { Locale } from "@/i18n/routing";
import { ApiError } from "@/lib/api/client";
import type { Complaint, Order } from "@/lib/api/types";
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
  const [t, tReviews, tComplaints] = await Promise.all([
    getTranslations("orders"),
    getTranslations("reviews"),
    getTranslations("complaints"),
  ]);
  const complaint = order.complaint ? await serverApi<Complaint>(`/complaints/${order.complaint.id}`) : null;
  const canReview = order.allowed_actions.includes("review");
  const canComplain = order.allowed_actions.includes("complain");
  // Only order-state actions belong in the order panel; review/complaint have their own sections.
  const orderActions = order.allowed_actions.filter((a) => a === "cancel" || a === "confirm_receipt");

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
          orderActions.length ? <CustomerOrderActions orderId={order.id} actions={orderActions} /> : undefined
        }
      />

      {order.review || canReview ? (
        <Card className="space-y-3">
          {order.review ? (
            <>
              <h2 className="font-semibold">{tReviews("yours")}</h2>
              <ul>
                <ReviewItem review={order.review} />
              </ul>
            </>
          ) : (
            <ReviewForm orderId={order.id} />
          )}
        </Card>
      ) : null}

      {complaint ? (
        <Card className="space-y-4">
          <h2 className="font-semibold">{tComplaints("yourComplaint")}</h2>
          <ComplaintThread complaint={complaint} />
          <CustomerComplaintActions complaintId={complaint.id} actions={complaint.allowed_actions} />
        </Card>
      ) : null}
      {canComplain ? (
        <Card>
          <ComplaintForm orderId={order.id} />
        </Card>
      ) : null}
    </div>
  );
}
