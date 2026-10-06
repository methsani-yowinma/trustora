import { useLocale, useTranslations } from "next-intl";

import { AuthenticityBadge } from "@/components/trust/StatusBadges";
import { TrustLevelBadge } from "@/components/trust/TrustLevel";
import { Card } from "@/components/ui/Card";
import { RemoteImage } from "@/components/ui/RemoteImage";
import { Link } from "@/i18n/navigation";
import type { ProductCard, StoreBadge } from "@/lib/api/types";
import { formatLkr, localize } from "@/lib/localize";

/** Compact store identity + trust, shown wherever a product appears. */
export function StoreTrustLine({ store }: { store: StoreBadge }) {
  const t = useTranslations("discover");
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs text-ink-muted">
      <span className="font-medium text-ink">{store.name}</span>
      {store.trust_level ? <TrustLevelBadge level={store.trust_level} /> : null}
      {store.trust_score !== null ? <span className="tabular-nums">{t("trustScore", { score: store.trust_score })}</span> : null}
    </div>
  );
}

export function ProductCardView({ product }: { product: ProductCard }) {
  const t = useTranslations("product");
  const locale = useLocale();
  const name = localize(product.name_i18n, locale);

  return (
    <Link href={`/products/${product.id}`} className="block h-full">
      <Card className="flex h-full flex-col gap-3 p-4 transition-shadow hover:shadow-md">
        <RemoteImage src={product.image_url} alt={name?.text ?? ""} className="aspect-[4/3] w-full rounded-lg" />
        <p lang={name?.lang} className="font-medium">
          {name?.text}
        </p>
        <p className="flex items-center justify-between text-sm">
          <span className="font-semibold tabular-nums">{formatLkr(product.price_lkr, locale)}</span>
          <span className={product.in_stock ? "text-ink-muted" : "text-trust-caution"}>
            {product.in_stock ? t("inStock") : t("outOfStock")}
          </span>
        </p>
        <AuthenticityBadge status={product.authenticity_status} />
        <div className="mt-auto border-t border-line pt-2">
          <StoreTrustLine store={product.store} />
        </div>
      </Card>
    </Link>
  );
}
