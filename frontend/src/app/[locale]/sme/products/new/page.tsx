import { getTranslations, setRequestLocale } from "next-intl/server";

import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import { ProductForm } from "@/components/sme/ProductForm";
import type { Locale } from "@/i18n/routing";
import { serverFetch } from "@/lib/api/server";
import type { Category } from "@/lib/api/types";
import { requireSme } from "@/lib/sme";

export default async function NewProductPage({ params }: PageProps<"/[locale]/sme/products/new">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);

  const guard = await requireSme(locale as Locale, `/${locale}/sme/products/new`);
  if (guard.kind !== "allowed") {
    return <AccessState kind={guard.kind === "forbidden" ? "forbidden" : "unavailable"} roles={["SME"]} />;
  }
  const t = await getTranslations("sme.products");
  const categories = await serverFetch<Category[]>("/categories");

  return (
    <div className="space-y-6">
      <PageHeader title={t("new")} />
      <ProductForm categories={categories} />
    </div>
  );
}
