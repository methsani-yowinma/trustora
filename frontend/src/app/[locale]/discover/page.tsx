import { Search } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { PageHeader } from "@/components/layout/PageHeader";
import { ProductCardView } from "@/components/commerce/ProductCardView";
import { VerificationBadge } from "@/components/trust/StatusBadges";
import { TrustLevelBadge } from "@/components/trust/TrustLevel";
import { Alert } from "@/components/ui/Alert";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { RemoteImage } from "@/components/ui/RemoteImage";
import { Link } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";
import { serverFetch } from "@/lib/api/server";
import type { Category, Paged, ProductCard, StoreCard } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { localize, localizedString } from "@/lib/localize";

const SORTS = ["newest", "price_asc", "price_desc", "trust"] as const;
const SORT_LABEL = { newest: "sortNewest", price_asc: "sortPriceAsc", price_desc: "sortPriceDesc", trust: "sortTrust" } as const;

function one(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function DiscoverPage({ params, searchParams }: PageProps<"/[locale]/discover">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);
  const t = await getTranslations("discover");
  const query = await searchParams;

  const tab = one(query.tab) === "stores" ? "stores" : "products";
  const q = (one(query.q) ?? "").slice(0, 80);
  const category = Number(one(query.category)) || undefined;
  const verified = one(query.verified) === "true";
  const sort = SORTS.find((s) => s === one(query.sort)) ?? "newest";
  const page = Math.max(1, Math.min(500, Number(one(query.page)) || 1));

  const search = new URLSearchParams({ page: String(page), page_size: "24" });
  if (q) search.set("q", q);
  if (verified) search.set("verified", "true");

  let products: Paged<ProductCard> | null = null;
  let stores: Paged<StoreCard> | null = null;
  let categories: Category[] = [];
  let failed = false;
  try {
    categories = await serverFetch<Category[]>("/categories");
    if (tab === "products") {
      if (category) search.set("category", String(category));
      search.set("sort", sort);
      products = await serverFetch<Paged<ProductCard>>(`/products?${search}`);
    } else {
      stores = await serverFetch<Paged<StoreCard>>(`/stores?${search}`);
    }
  } catch {
    failed = true;
  }

  const result = products ?? stores;
  const pages = result ? Math.max(1, Math.ceil(result.total / result.page_size)) : 1;
  const link = (overrides: Record<string, string | number | undefined>) => ({
    pathname: "/discover" as const,
    query: Object.fromEntries(
      Object.entries({ tab, q: q || undefined, category, verified: verified ? "true" : undefined, sort, page, ...overrides })
        .filter(([, v]) => v !== undefined && v !== "")
        .map(([k, v]) => [k, String(v)]),
    ),
  });

  return (
    <div className="space-y-6 py-8">
      <PageHeader title={t("title")} description={t("subtitle")} />

      <nav aria-label={t("title")} className="flex gap-2">
        {(["products", "stores"] as const).map((value) => (
          <Link
            key={value}
            href={link({ tab: value, page: 1 })}
            aria-current={tab === value ? "page" : undefined}
            className={cn(
              "rounded-full border px-4 py-1.5 text-sm",
              tab === value ? "border-brand-600 bg-brand-50 text-brand-700" : "border-line text-ink-muted",
            )}
          >
            {t(value)}
          </Link>
        ))}
      </nav>

      <form role="search" className="grid gap-3 rounded-[var(--radius-card)] border border-line bg-surface p-4 sm:grid-cols-[1fr_auto] lg:grid-cols-[1fr_12rem_12rem_auto_auto]">
        <input type="hidden" name="tab" value={tab} />
        <label className="relative block">
          <span className="sr-only">{t("search")}</span>
          <Search aria-hidden="true" className="pointer-events-none absolute top-3 left-3 h-4 w-4 text-ink-muted" />
          <input
            type="search"
            name="q"
            defaultValue={q}
            maxLength={80}
            placeholder={t("searchPlaceholder")}
            className="w-full rounded-lg border border-line py-2.5 pr-3 pl-9 text-sm"
          />
        </label>
        {tab === "products" ? (
          <>
            <label className="block">
              <span className="sr-only">{t("allCategories")}</span>
              <select name="category" defaultValue={category ?? ""} className="w-full rounded-lg border border-line px-3 py-2.5 text-sm">
                <option value="">{t("allCategories")}</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {localizedString(c.name_i18n, locale)}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="sr-only">{t("sort")}</span>
              <select name="sort" defaultValue={sort} className="w-full rounded-lg border border-line px-3 py-2.5 text-sm">
                {SORTS.map((s) => (
                  <option key={s} value={s}>
                    {t(SORT_LABEL[s])}
                  </option>
                ))}
              </select>
            </label>
          </>
        ) : null}
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" name="verified" value="true" defaultChecked={verified} className="h-4 w-4 accent-brand-600" />
          {tab === "products" ? t("verifiedOnly") : t("verifiedStoresOnly")}
        </label>
        <button type="submit" className={buttonClasses("primary")}>
          {t("search")}
        </button>
      </form>

      {failed ? <Alert tone="error">{(await getTranslations("common"))("loadFailed")}</Alert> : null}

      {result ? (
        <p className="text-sm text-ink-muted" aria-live="polite">
          {t("results", { count: result.total })}
        </p>
      ) : null}

      {products && products.items.length > 0 ? (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {products.items.map((product) => (
            <li key={product.id}>
              <ProductCardView product={product} />
            </li>
          ))}
        </ul>
      ) : null}

      {stores && stores.items.length > 0 ? (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {stores.items.map((store) => {
            const description = localize(store.description_i18n, locale);
            return (
              <li key={store.id}>
                <Link href={`/stores/${store.slug}`} className="block h-full">
                  <Card className="flex h-full gap-4 p-4 transition-shadow hover:shadow-md">
                    <RemoteImage src={store.logo_url} alt={store.name} className="h-14 w-14 shrink-0 rounded-xl border border-line" />
                    <div className="min-w-0 space-y-1.5">
                      <p className="font-semibold">{store.name}</p>
                      <div className="flex flex-wrap gap-1.5">
                        {store.trust_level ? <TrustLevelBadge level={store.trust_level} /> : null}
                        <VerificationBadge status={store.verification_status} />
                      </div>
                      {description ? (
                        <p lang={description.lang} className="line-clamp-2 text-sm text-ink-muted">
                          {description.text}
                        </p>
                      ) : null}
                      <p className="text-xs text-ink-muted">
                        {t("productCount", { count: store.product_count })}
                        {store.trust_score !== null ? ` · ${t("trustScore", { score: store.trust_score })}` : ""}
                      </p>
                    </div>
                  </Card>
                </Link>
              </li>
            );
          })}
        </ul>
      ) : null}

      {result && result.items.length === 0 ? <Card className="text-center text-ink-muted">{t("noResults")}</Card> : null}

      {result && pages > 1 ? (
        <nav className="flex items-center justify-between gap-3 text-sm" aria-label={t("page", { page, pages })}>
          {page > 1 ? (
            <Link href={link({ page: page - 1 })} className={buttonClasses("secondary")}>
              {t("previous")}
            </Link>
          ) : (
            <span />
          )}
          <span className="text-ink-muted">{t("page", { page, pages })}</span>
          {page < pages ? (
            <Link href={link({ page: page + 1 })} className={buttonClasses("secondary")}>
              {t("next")}
            </Link>
          ) : (
            <span />
          )}
        </nav>
      ) : null}
    </div>
  );
}
