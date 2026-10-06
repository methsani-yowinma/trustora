import { getTranslations, setRequestLocale } from "next-intl/server";

import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import { ReviewResponseForm } from "@/components/reviews/ReviewResponseForm";
import { ReviewItem } from "@/components/reviews/Reviews";
import { Badge } from "@/components/ui/Badge";
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
  const [t, tAi] = await Promise.all([getTranslations("smeReviews"), getTranslations("ai")]);
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
                <div className="flex flex-wrap items-center gap-2 pt-2">
                  <p className="text-xs text-ink-muted">{t("order", { number: review.order_number })}</p>
                  {review.ai_sentiment ? (
                    <Badge tone="developing">
                      {tAi("reviewSentiment", { sentiment: tAi(`sentimentValue.${review.ai_sentiment as "NEUTRAL"}`) })}
                    </Badge>
                  ) : null}
                </div>
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
