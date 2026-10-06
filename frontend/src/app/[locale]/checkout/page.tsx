import { getTranslations, setRequestLocale } from "next-intl/server";

import { CheckoutForm } from "@/components/commerce/CheckoutForm";
import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import type { Locale } from "@/i18n/routing";
import { requireRole } from "@/lib/auth";
import { DISTRICTS } from "@/lib/districts";

export default async function CheckoutPage({ params, searchParams }: PageProps<"/[locale]/checkout">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);
  const guard = await requireRole(locale as Locale, ["CUSTOMER"], `/${locale}/checkout`);
  if (guard.kind !== "allowed") return <AccessState kind={guard.kind} roles={["CUSTOMER"]} />;

  const t = await getTranslations("checkout");
  const requested = (await searchParams).district;
  const district = DISTRICTS.find((d) => d === requested) ?? "COLOMBO";

  return (
    <div className="space-y-6 py-8">
      <PageHeader title={t("title")} />
      <CheckoutForm initialDistrict={district} defaultName={guard.profile.full_name ?? ""} />
    </div>
  );
}
