import { BadgeCheck, Info, Mail, Phone } from "lucide-react";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { cache } from "react";

import { AuthenticityBadge, VerificationBadge } from "@/components/trust/StatusBadges";
import { TrustScoreCard } from "@/components/trust/TrustScoreCard";
import { buttonClasses } from "@/components/ui/Button";
import { Link } from "@/i18n/navigation";
import { Alert } from "@/components/ui/Alert";
import { Card } from "@/components/ui/Card";
import { RemoteImage } from "@/components/ui/RemoteImage";
import type { Locale } from "@/i18n/routing";
import { ApiError, apiFetch } from "@/lib/api/client";
import type { Passport, PolicyKey, PublicProduct, PublicStore } from "@/lib/api/types";
import { formatDate, formatLkr, localize } from "@/lib/localize";

const SLUG = /^[A-Za-z0-9-]{3,40}$/;
const POLICY_KEYS: PolicyKey[] = ["returns", "refunds", "delivery"];

/** Public, signed-out view of a published store (read through the API as Postgres role anon). */
const loadStore = cache(async (slug: string) => {
  if (!SLUG.test(slug)) return null;
  try {
    const [store, products, passport] = await Promise.all([
      apiFetch<PublicStore>(`/stores/${slug}`),
      apiFetch<PublicProduct[]>(`/stores/${slug}/products`),
      apiFetch<Passport>(`/stores/${slug}/passport`),
    ]);
    return { store, products, passport };
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
});

export async function generateMetadata({ params }: PageProps<"/[locale]/stores/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const data = await loadStore(slug).catch(() => null);
  return data ? { title: `${data.store.name} · Trustora` } : {};
}

/** SME-authored text, tagged with the language it is actually written in. */
function SellerText({ text, className }: { text: ReturnType<typeof localize>; className?: string }) {
  if (!text) return null;
  return (
    <p lang={text.lang} className={className}>
      {text.text}
    </p>
  );
}

export default async function StorePage({ params }: PageProps<"/[locale]/stores/[slug]">) {
  const { locale, slug } = await params;
  setRequestLocale(locale as Locale);

  const t = await getTranslations("store");
  const tPolicies = await getTranslations("policies");
  const tPlatforms = await getTranslations("platforms");

  let data: Awaited<ReturnType<typeof loadStore>>;
  try {
    data = await loadStore(slug);
  } catch {
    const tErrors = await getTranslations("common");
    return (
      <div className="py-16">
        <Alert tone="error">{tErrors("loadFailed")}</Alert>
      </div>
    );
  }
  if (!data) notFound();
  const { store, products, passport } = data;
  const tPassport = await getTranslations("passport");

  const description = localize(store.description_i18n, locale);
  const policies = POLICY_KEYS.flatMap((key) => {
    const text = localize(store.policies_i18n[key], locale);
    return text ? [{ key, text }] : [];
  });
  const usesFallback =
    description?.isFallback || policies.some((p) => p.text.isFallback) || products.some((p) => localize(p.name_i18n, locale)?.isFallback);

  return (
    <div className="space-y-8 py-8">
      <section className="flex flex-col gap-5 sm:flex-row sm:items-start">
        <RemoteImage src={store.logo_url} alt={store.name} className="h-24 w-24 shrink-0 rounded-2xl border border-line" />
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-3xl font-semibold tracking-tight">{store.name}</h1>
            <VerificationBadge status={store.verification_status} />
          </div>
          <p className="text-sm text-ink-muted">
            {store.verification_status === "VERIFIED" && store.verified_at
              ? `${t("verifiedOn", { date: formatDate(store.verified_at, locale) })} · `
              : null}
            {t("memberSince", { date: formatDate(store.member_since, locale) })}
          </p>
          <SellerText text={description} className="max-w-3xl text-ink" />
        </div>
      </section>

      {store.verification_status !== "VERIFIED" ? (
        <Alert title={store.verification_status === "PENDING" ? t("pending") : t("notVerified")}>
          {t("notVerifiedHint")}
        </Alert>
      ) : null}

      <section aria-label={tPassport("title")} className="space-y-3">
        <TrustScoreCard trust={passport.trust} compact />
        <Link href={`/stores/${store.slug}/passport`} className={buttonClasses("secondary")}>
          {tPassport("openPassport")}
        </Link>
      </section>

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <section aria-labelledby="products-title" className="space-y-4">
          <h2 id="products-title" className="text-xl font-semibold">
            {t("productsTitle")}
          </h2>
          {products.length === 0 ? (
            <Card className="text-ink-muted">{t("noProducts")}</Card>
          ) : (
            <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {products.map((product) => {
                const name = localize(product.name_i18n, locale);
                return (
                  <li key={product.id}>
                    <Card className="h-full space-y-3 p-4">
                      <RemoteImage
                        src={product.images[0]?.url}
                        alt={name?.text ?? ""}
                        className="aspect-[4/3] w-full rounded-lg"
                      />
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
                    </Card>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <aside className="space-y-4">
          <Card className="space-y-3">
            <h2 className="font-semibold">{t("contact")}</h2>
            {store.contact_phone ? (
              <p className="flex items-center gap-2 text-sm">
                <Phone aria-hidden="true" className="h-4 w-4 text-ink-muted" />
                <a href={`tel:${store.contact_phone.replace(/\s/g, "")}`} className="hover:underline">
                  {store.contact_phone}
                </a>
              </p>
            ) : null}
            {store.contact_email ? (
              <p className="flex items-center gap-2 text-sm">
                <Mail aria-hidden="true" className="h-4 w-4 text-ink-muted" />
                <a href={`mailto:${store.contact_email}`} className="break-all hover:underline">
                  {store.contact_email}
                </a>
              </p>
            ) : null}
            <p className="text-xs text-ink-muted">
              {store.contact_verified ? (
                <span className="inline-flex items-center gap-1 text-trust-verified">
                  <BadgeCheck aria-hidden="true" className="h-3.5 w-3.5" />
                  {t("contactConfirmed")}
                </span>
              ) : (
                t("sellerProvided")
              )}
            </p>
          </Card>

          {store.social_accounts.length > 0 ? (
            <Card className="space-y-3">
              <h2 className="font-semibold">{t("socialTitle")}</h2>
              <ul className="space-y-2 text-sm">
                {store.social_accounts.map((account) => (
                  <li key={account.id} className="flex items-center gap-2">
                    <BadgeCheck aria-hidden="true" className="h-4 w-4 text-trust-verified" />
                    {account.url ? (
                      <a href={account.url} target="_blank" rel="noopener noreferrer nofollow" className="hover:underline">
                        {tPlatforms(account.platform)} · @{account.handle}
                      </a>
                    ) : (
                      <span>
                        {tPlatforms(account.platform)} · @{account.handle}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}

          <Card className="space-y-3">
            <h2 className="font-semibold">{t("policiesTitle")}</h2>
            {policies.length === 0 ? (
              <p className="text-sm text-ink-muted">{t("noPolicies")}</p>
            ) : (
              <dl className="space-y-3 text-sm">
                {policies.map(({ key, text }) => (
                  <div key={key}>
                    <dt className="font-medium">{tPolicies(key)}</dt>
                    <dd lang={text.lang} className="whitespace-pre-line text-ink-muted">
                      {text.text}
                    </dd>
                  </div>
                ))}
              </dl>
            )}
            <p className="text-xs text-ink-muted">{t("sellerProvided")}</p>
          </Card>
        </aside>
      </div>

      <div className="space-y-2 text-sm text-ink-muted">
        {usesFallback ? (
          <p className="flex items-center gap-2">
            <Info aria-hidden="true" className="h-4 w-4" />
            {t("fallbackLanguage")}
          </p>
        ) : null}
      </div>
    </div>
  );
}

