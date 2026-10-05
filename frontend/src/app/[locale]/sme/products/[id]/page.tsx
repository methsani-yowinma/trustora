import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import { ProductForm } from "@/components/sme/ProductForm";
import { ProductEvidence, ProductImages, RemoveProductButton } from "@/components/sme/ProductMedia";
import { AuthenticityBadge } from "@/components/trust/StatusBadges";
import type { Locale } from "@/i18n/routing";
import { ApiError, apiFetch } from "@/lib/api/client";
import type { Category, ProductDetail } from "@/lib/api/types";
import { serverApi } from "@/lib/auth";
import { localizedString } from "@/lib/localize";
import { requireSme } from "@/lib/sme";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function EditProductPage({ params }: PageProps<"/[locale]/sme/products/[id]">) {
  const { locale, id } = await params;
  setRequestLocale(locale as Locale);
  if (!UUID.test(id)) notFound();

  const guard = await requireSme(locale as Locale, `/${locale}/sme/products/${id}`);
  if (guard.kind !== "allowed") {
    return <AccessState kind={guard.kind === "forbidden" ? "forbidden" : "unavailable"} roles={["SME"]} />;
  }

  let product: ProductDetail;
  try {
    product = await serverApi<ProductDetail>(`/sme/products/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const [t, categories] = await Promise.all([
    getTranslations("sme.products"),
    apiFetch<Category[]>("/categories"),
  ]);

  return (
    <div className="space-y-6">
      <PageHeader
        title={localizedString(product.name_i18n, locale) || t("edit")}
        description={<AuthenticityBadge status={product.authenticity_status} />}
        actions={<RemoveProductButton productId={product.id} />}
      />
      <ProductForm categories={categories} product={product} />
      <ProductImages product={product} />
      <ProductEvidence product={product} />
    </div>
  );
}
