"use client";

import { useLocale, useTranslations } from "next-intl";
import { useTransition } from "react";

import { usePathname, useRouter } from "@/i18n/navigation";
import { routing, type Locale } from "@/i18n/routing";
import { cn } from "@/lib/cn";

const LABELS: Record<Locale, { full: string; short: string }> = {
  en: { full: "English", short: "EN" },
  si: { full: "සිංහල", short: "සිං" },
};

export function LanguageSwitcher() {
  const t = useTranslations("nav");
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  return (
    <div role="group" aria-label={t("language")} className="flex rounded-lg border border-line bg-surface p-0.5">
      {routing.locales.map((option) => (
        <button
          key={option}
          type="button"
          lang={option}
          aria-pressed={option === locale}
          aria-label={LABELS[option].full}
          disabled={isPending}
          onClick={() => startTransition(() => router.replace(pathname, { locale: option }))}
          className={cn(
            "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
            option === locale ? "bg-brand-600 text-white" : "text-ink-muted hover:text-ink",
          )}
        >
          <span className="hidden sm:inline">{LABELS[option].full}</span>
          <span className="sm:hidden" aria-hidden="true">
            {LABELS[option].short}
          </span>
        </button>
      ))}
    </div>
  );
}
