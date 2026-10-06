import { getTranslations, setRequestLocale } from "next-intl/server";

import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import { ReviewResponseForm } from "@/components/reviews/ReviewResponseForm";
import { ReviewItem } from "@/components/reviews/Reviews";
import { Card } from "@/components/ui/Card";
import type { Locale } from "@/i18n/routing";
import type { SmeReview } from "@/lib/api/types";
import { serverApi } from "@/lib/auth";
import { requireSme } from "@/lib/sme";

export default async function SmeReviewsPage({ params }: PageProps<"/[locale]/sme/reviews">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);
  const guard = await requireSme(locale as Locale, `/${locale}/sme/reviews`);
  if (guard.kind !== "allowed") {
    return <AccessState kind={guard.kind === "forbidden" ? "forbidden" : "unavailable"} roles={["SME"]} />;
  }
  const t = await getTranslations("smeReviews");
  const reviews = await serverApi<SmeReview[]>("/sme/reviews");

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} />
      {reviews.length === 0 ? (
        <Card className="text-center text-ink-muted">{t("empty")}</Card>
      ) : (
        <ul className="space-y-3">
          {reviews.map((review) => (
            <li key={review.id}>
              <Card className="space-y-2 py-2">
                <p className="pt-2 text-xs text-ink-muted">{t("order", { number: review.order_number })}</p>
                <ul>
                  <ReviewItem review={review} />
                </ul>
                {review.sme_response ? null : (
                  <div className="pb-3">
                    <ReviewResponseForm reviewId={review.id} />
                  </div>
                )}
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
