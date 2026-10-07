import { Info } from "lucide-react";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { cache } from "react";

import { AddToCart } from "@/components/commerce/AddToCart";
import { AuthenticityBadge, VerificationBadge } from "@/components/trust/StatusBadges";
import { TrustLevelBadge } from "@/components/trust/TrustLevel";
import { Alert } from "@/components/ui/Alert";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { RemoteImage } from "@/components/ui/RemoteImage";
import { Link } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";
import { ApiError } from "@/lib/api/client";
import { serverFetch } from "@/lib/api/server";
import type { PublicProductDetail } from "@/lib/api/types";
import { formatLkr, localize } from "@/lib/localize";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const loadProduct = cache(async (id: string) => {
  if (!UUID.test(id)) return null;
  try {
    return await serverFetch<PublicProductDetail>(`/products/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
});

export async function generateMetadata({ params }: PageProps<"/[locale]/products/[id]">): Promise<Metadata> {
  const { id, locale } = await params;
  const product = await loadProduct(id).catch(() => null);
  if (!product) return {};
  return { title: `${localize(product.name_i18n, locale)?.text ?? ""} · ${product.store.name}` };
}

export default async function ProductPage({ params }: PageProps<"/[locale]/products/[id]">) {
  const { locale, id } = await params;
  setRequestLocale(locale as Locale);
  const t = await getTranslations("product");

  let product: PublicProductDetail | null;
  try {
    product = await loadProduct(id);
  } catch {
    return (
      <div className="py-16">
        <Alert tone="error">{(await getTranslations("common"))("loadFailed")}</Alert>
      </div>
    );
  }
  if (!product) notFound();

  const name = localize(product.name_i18n, locale);
  const description = localize(product.description_i18n, locale);
  const [main, ...rest] = product.images;

  return (
    <div className="grid gap-8 py-8 lg:grid-cols-2">
      <div className="space-y-3">
        <RemoteImage src={main?.url} alt={name?.text ?? ""} className="aspect-square w-full rounded-[var(--radius-card)] border border-line" />
        {rest.length > 0 ? (
          <ul className="grid grid-cols-4 gap-2">
            {rest.map((image, index) => (
              <li key={image.id}>
                <RemoteImage src={image.url} alt={t("image", { index: index + 2 })} className="aspect-square w-full rounded-lg border border-line" />
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      <div className="space-y-6">
        <div className="space-y-3">
          <h1 lang={name?.lang} className="text-3xl font-semibold tracking-tight">
            {name?.text}
          </h1>
          <p className="text-2xl font-semibold">{formatLkr(product.price_lkr, locale)}</p>
          <div className="space-y-1">
            <AuthenticityBadge status={product.authenticity_status} />
            <p className="flex items-start gap-1.5 text-xs text-ink-muted">
              <Info aria-hidden="true" className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {t("authenticityHelp")}
            </p>
          </div>
        </div>

        <AddToCart product={product} />

        <Card className="space-y-3">
          <h2 className="text-sm font-semibold">{t("storeTrust")}</h2>
          <p className="text-sm">
            {t("soldBy")}{" "}
            <Link href={`/stores/${product.store.slug}`} className="font-medium text-brand-700 hover:underline">
              {product.store.name}
            </Link>
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {product.store.trust_level ? <TrustLevelBadge level={product.store.trust_level} /> : null}
            <VerificationBadge status={product.store.verification_status} />
            {product.store.trust_score !== null ? (
              <span className="text-sm text-ink-muted tabular-nums">{product.store.trust_score}/100</span>
            ) : null}
          </div>
          <Link href={`/stores/${product.store.slug}/passport`} className={buttonClasses("secondary")}>
            {t("viewPassport")}
          </Link>
        </Card>

        {description ? (
          <section className="space-y-2">
            <h2 className="font-semibold">{t("description")}</h2>
            <p lang={description.lang} className="whitespace-pre-line text-ink">
              {description.text}
            </p>
            <p className="text-xs text-ink-muted">{t("sellerProvided")}</p>
          </section>
        ) : null}
      </div>
    </div>
  );
}
