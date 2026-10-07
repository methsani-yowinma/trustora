import { BadgeCheck, PackageCheck, ShieldCheck, Truck } from "lucide-react";
import { useTranslations } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import Image from "next/image";
import { use } from "react";

import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Link } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";

const DIMENSIONS = [
  { key: "business", Icon: BadgeCheck },
  { key: "product", Icon: PackageCheck },
  { key: "transaction", Icon: Truck },
] as const;

export default function HomePage({ params }: PageProps<"/[locale]">) {
  const { locale } = use(params);
  setRequestLocale(locale as Locale);
  const t = useTranslations("home");
  const tNav = useTranslations("nav");

  return (
    <div className="space-y-16 py-12 sm:py-20">
      <section className="grid items-center gap-10 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="max-w-3xl space-y-6">
          <p className="inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1 text-sm font-medium text-brand-700">
            <ShieldCheck aria-hidden="true" className="h-4 w-4" />
            {t("eyebrow")}
          </p>
          <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl">{t("title")}</h1>
          <p className="text-lg text-ink-muted">{t("body")}</p>
          <div className="flex flex-wrap gap-3">
            <Link href="/discover" className={buttonClasses("primary")}>
              {tNav("discover")}
            </Link>
            <Link href={{ pathname: "/signup", query: { type: "customer" } }} className={buttonClasses("secondary")}>
              {t("ctaCustomer")}
            </Link>
            <Link href={{ pathname: "/signup", query: { type: "sme" } }} className={buttonClasses("secondary")}>
              {t("ctaSme")}
            </Link>
          </div>
        </div>

        {/* Trustora AI mascot. A soft brand glow sits behind the transparent image. */}
        <div className="relative mx-auto w-full max-w-[15rem] sm:max-w-[18rem] lg:max-w-none">
          <div
            aria-hidden="true"
            className="absolute inset-[12%] -z-10 rounded-full bg-brand-100 blur-3xl"
          />
          <Image
            src="/images/trustora-ai-robot.png"
            alt={t("robotAlt")}
            width={1275}
            height={1234}
            priority
            sizes="(min-width: 1024px) 24rem, (min-width: 640px) 18rem, 15rem"
            className="h-auto w-full motion-safe:animate-robot-float"
          />
        </div>
      </section>

      <section aria-labelledby="dimensions-title" className="space-y-6">
        <h2 id="dimensions-title" className="text-2xl font-semibold tracking-tight">
          {t("dimensionsTitle")}
        </h2>
        <div className="grid gap-4 md:grid-cols-3">
          {DIMENSIONS.map(({ key, Icon }) => (
            <Card key={key} className="space-y-3">
              <Icon aria-hidden="true" className="h-6 w-6 text-brand-600" />
              <h3 className="font-semibold">{t(`${key}.title`)}</h3>
              <p className="font-medium text-ink">“{t(`${key}.question`)}”</p>
              <p className="text-sm text-ink-muted">{t(`${key}.body`)}</p>
            </Card>
          ))}
        </div>
      </section>

      <section className="rounded-[var(--radius-card)] border border-brand-100 bg-brand-50 p-6 sm:p-8">
        <h2 className="text-lg font-semibold text-brand-900">{t("principleTitle")}</h2>
        <p className="mt-2 max-w-3xl text-brand-900/80">{t("principleBody")}</p>
      </section>
    </div>
  );
}
