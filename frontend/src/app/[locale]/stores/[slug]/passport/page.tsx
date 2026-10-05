import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { cache } from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import { PassportView } from "@/components/trust/PassportView";
import { VerificationBadge } from "@/components/trust/StatusBadges";
import { Alert } from "@/components/ui/Alert";
import { RemoteImage } from "@/components/ui/RemoteImage";
import { Link } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";
import { ApiError, apiFetch } from "@/lib/api/client";
import type { Passport } from "@/lib/api/types";
import { formatDate } from "@/lib/localize";

const SLUG = /^[A-Za-z0-9-]{3,40}$/;

const loadPassport = cache(async (slug: string) => {
  if (!SLUG.test(slug)) return null;
  try {
    return await apiFetch<Passport>(`/stores/${slug}/passport`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
});

export async function generateMetadata({
  params,
}: PageProps<"/[locale]/stores/[slug]/passport">): Promise<Metadata> {
  const { slug, locale } = await params;
  const passport = await loadPassport(slug).catch(() => null);
  if (!passport) return {};
  const t = await getTranslations({ locale: locale as Locale, namespace: "passport" });
  return { title: `${t("title")} · ${passport.store.name}` };
}

export default async function PassportPage({ params }: PageProps<"/[locale]/stores/[slug]/passport">) {
  const { locale, slug } = await params;
  setRequestLocale(locale as Locale);
  const t = await getTranslations("passport");

  let passport: Passport | null;
  try {
    passport = await loadPassport(slug);
  } catch {
    const tCommon = await getTranslations("common");
    return (
      <div className="py-16">
        <Alert tone="error">{tCommon("loadFailed")}</Alert>
      </div>
    );
  }
  if (!passport) notFound();
  const { store } = passport;

  return (
    <div className="space-y-6 py-8">
      <Link
        href={`/stores/${store.slug}`}
        className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline"
      >
        <ArrowLeft aria-hidden="true" className="h-4 w-4" />
        {t("storeLink")}
      </Link>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <RemoteImage src={store.logo_url} alt={store.name} className="h-16 w-16 shrink-0 rounded-xl border border-line" />
        <PageHeader
          title={t("title")}
          description={
            <span className="flex flex-wrap items-center gap-2">
              <span>{t("subtitle", { name: store.name })}</span>
              <VerificationBadge status={store.verification_status} />
              {store.verified_at ? (
                <span className="text-sm">{t("verifiedOn", { date: formatDate(store.verified_at, locale) })}</span>
              ) : null}
            </span>
          }
        />
      </div>
      <PassportView passport={passport} />
    </div>
  );
}
