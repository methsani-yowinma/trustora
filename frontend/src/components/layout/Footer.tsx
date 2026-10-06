import { getTranslations } from "next-intl/server";

import { LogoMark } from "@/components/ui/Logo";

export async function Footer() {
  const t = await getTranslations("footer");
  const tBrand = await getTranslations("brand");

  // Bottom padding keeps footer content clear of the Trustora AI launcher.
  return (
    <footer className="mt-16 border-t border-line bg-surface pb-20 sm:pb-24">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-8 text-sm text-ink-muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div className="flex items-center gap-2">
          <LogoMark className="h-5 w-5" />
          <span>{tBrand("tagline")}</span>
        </div>
        <p className="max-w-xl">{t("disclaimer")}</p>
        <p>{t("rights", { year: new Date().getFullYear() })}</p>
      </div>
    </footer>
  );
}
