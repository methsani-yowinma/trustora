import { getTranslations, setRequestLocale } from "next-intl/server";

import { CartView } from "@/components/commerce/CartView";
import { PageHeader } from "@/components/layout/PageHeader";
import type { Locale } from "@/i18n/routing";
import { getSession } from "@/lib/auth";

export default async function CartPage({ params }: PageProps<"/[locale]/cart">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);
  const t = await getTranslations("cart");
  const session = await getSession();
  const signedIn = session.status === "authenticated" && session.profile.role === "CUSTOMER";

  return (
    <div className="space-y-6 py-8">
      <PageHeader title={t("title")} />
      <CartView signedIn={signedIn} />
    </div>
  );
}
