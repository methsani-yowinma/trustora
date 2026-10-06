import { BadgeCheck, MessageSquareReply, Star } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import type { Review, ReviewPage } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatDate } from "@/lib/localize";

/** Read-only star rating; the accessible name carries the value (never colour/shape alone). */
export function Stars({ rating, className }: { rating: number; className?: string }) {
  const t = useTranslations("reviews");
  return (
    <span role="img" aria-label={t("stars", { rating })} className={cn("inline-flex gap-0.5", className)}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          aria-hidden="true"
          className={cn("h-4 w-4", i <= rating ? "fill-trust-caution text-trust-caution" : "text-line")}
        />
      ))}
    </span>
  );
}

export function ReviewItem({ review }: { review: Review }) {
  const t = useTranslations("reviews");
  const locale = useLocale();
  return (
    <li className="space-y-2 py-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Stars rating={review.rating} />
        <span className="inline-flex items-center gap-1 text-xs text-trust-verified">
          <BadgeCheck aria-hidden="true" className="h-3.5 w-3.5" />
          {t("verifiedBuyer")}
        </span>
        <span className="text-xs text-ink-muted">{formatDate(review.created_at, locale)}</span>
      </div>
      {review.comment ? <p className="text-sm whitespace-pre-line">{review.comment}</p> : null}
      {review.sme_response ? (
        <div className="ml-4 rounded-lg bg-canvas p-3 text-sm">
          <p className="mb-1 inline-flex items-center gap-1 text-xs font-medium text-ink-muted">
            <MessageSquareReply aria-hidden="true" className="h-3.5 w-3.5" />
            {t("sellerResponse")}
          </p>
          <p className="whitespace-pre-line">{review.sme_response}</p>
        </div>
      ) : null}
    </li>
  );
}

export function ReviewSummary({ page }: { page: ReviewPage }) {
  const t = useTranslations("reviews");
  return (
    <section aria-labelledby="reviews-title" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="reviews-title" className="text-xl font-semibold">
          {t("title")}
        </h2>
        <p className="flex items-center gap-2 text-sm">
          {page.average !== null ? (
            <>
              <Stars rating={Math.round(page.average)} />
              <span className="font-medium">{t("average", { average: page.average })}</span>
            </>
          ) : null}
          <span className="text-ink-muted">{t("count", { count: page.count })}</span>
        </p>
      </div>
      {page.items.length === 0 ? (
        <p className="text-sm text-ink-muted">{t("empty")}</p>
      ) : (
        <ul className="divide-y divide-line rounded-[var(--radius-card)] border border-line bg-surface px-4">
          {page.items.map((review) => (
            <ReviewItem key={review.id} review={review} />
          ))}
        </ul>
      )}
    </section>
  );
}
