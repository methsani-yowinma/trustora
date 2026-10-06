import { getTranslations, setRequestLocale } from "next-intl/server";

import { SectionNav } from "@/components/layout/SectionNav";
import type { Locale } from "@/i18n/routing";

// Navigation only. Every SME page performs its own server-side role check.
export default async function SmeLayout({ children, params }: LayoutProps<"/[locale]/sme">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);
  const t = await getTranslations("sme.nav");

  return (
    <div className="space-y-8 py-6">
      <SectionNav
        label={t("label")}
        items={[
          { href: "/sme", label: t("dashboard"), exact: true },
          { href: "/sme/store", label: t("store") },
          { href: "/sme/products", label: t("products") },
          { href: "/sme/orders", label: t("orders") },
          { href: "/sme/reviews", label: t("reviews") },
          { href: "/sme/complaints", label: t("complaints") },
          { href: "/sme/verification", label: t("verification") },
          { href: "/sme/passport", label: t("passport") },
        ]}
      />
      {children}
    </div>
  );
}
