import { Plus } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import { AuthenticityBadge } from "@/components/trust/StatusBadges";
import { Badge } from "@/components/ui/Badge";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { RemoteImage } from "@/components/ui/RemoteImage";
import { Link } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";
import type { Product } from "@/lib/api/types";
import { serverApi } from "@/lib/auth";
import { formatLkr, localizedString } from "@/lib/localize";
import { requireSme } from "@/lib/sme";

export default async function SmeProductsPage({ params }: PageProps<"/[locale]/sme/products">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);

  const guard = await requireSme(locale as Locale, `/${locale}/sme/products`);
  if (guard.kind !== "allowed") {
    return <AccessState kind={guard.kind === "forbidden" ? "forbidden" : "unavailable"} roles={["SME"]} />;
  }
  const t = await getTranslations("sme.products");
  const products = await serverApi<Product[]>("/sme/products");

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("title")}
        actions={
          <Link href="/sme/products/new" className={buttonClasses("primary")}>
            <Plus aria-hidden="true" className="h-4 w-4" />
            {t("new")}
          </Link>
        }
      />
      {products.length === 0 ? (
        <Card className="text-center text-ink-muted">{t("empty")}</Card>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {products.map((product) => {
            const name = localizedString(product.name_i18n, locale);
            return (
              <li key={product.id}>
                <Link href={`/sme/products/${product.id}`} className="block h-full">
                  <Card className="h-full space-y-3 p-4 transition-shadow hover:shadow-md">
                    <RemoteImage
                      src={product.images[0]?.url}
                      alt={name}
                      className="aspect-[4/3] w-full rounded-lg"
                    />
                    <div className="space-y-1">
                      <p className="font-medium">{name}</p>
                      <p className="text-sm text-ink-muted tabular-nums">
                        {formatLkr(product.price_lkr, locale)} ·{" "}
                        {product.stock > 0 ? t("inStock", { count: product.stock }) : t("outOfStock")}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {product.status === "HIDDEN" ? <Badge>{t("statusHIDDEN")}</Badge> : null}
                      <AuthenticityBadge status={product.authenticity_status} />
                    </div>
                  </Card>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
