import { getTranslations, setRequestLocale } from "next-intl/server";

import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import { LogoUploader, PublishToggle } from "@/components/sme/LogoAndVisibility";
import { SocialAccountsManager } from "@/components/sme/SocialAccountsManager";
import { StoreSettingsForm } from "@/components/sme/StoreSettingsForm";
import type { Locale } from "@/i18n/routing";
import { requireSme } from "@/lib/sme";

export default async function SmeStorePage({ params }: PageProps<"/[locale]/sme/store">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);

  const guard = await requireSme(locale as Locale, `/${locale}/sme/store`);
  if (guard.kind !== "allowed") {
    return <AccessState kind={guard.kind === "forbidden" ? "forbidden" : "unavailable"} roles={["SME"]} />;
  }
  const { sme } = guard;
  const t = await getTranslations("sme.store");

  return (
    <div className="space-y-6">
      <PageHeader title={t("title")} description={`/stores/${sme.slug}`} />
      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <StoreSettingsForm sme={sme} />
        <div className="space-y-6">
          <PublishToggle sme={sme} />
          <LogoUploader sme={sme} />
        </div>
      </div>
      <SocialAccountsManager accounts={sme.social_accounts} />
    </div>
  );
}
