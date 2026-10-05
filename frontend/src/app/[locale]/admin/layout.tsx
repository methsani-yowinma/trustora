import { getTranslations, setRequestLocale } from "next-intl/server";

import { SectionNav } from "@/components/layout/SectionNav";
import type { Locale } from "@/i18n/routing";

// Navigation only. Every admin page performs its own server-side role check.
export default async function AdminLayout({ children, params }: LayoutProps<"/[locale]/admin">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);
  const t = await getTranslations("admin.nav");

  return (
    <div className="space-y-8 py-6">
      <SectionNav
        label={t("label")}
        items={[
          { href: "/admin", label: t("dashboard"), exact: true },
          { href: "/admin/verifications", label: t("verifications") },
          { href: "/admin/evidence", label: t("evidence") },
        ]}
      />
      {children}
    </div>
  );
}
