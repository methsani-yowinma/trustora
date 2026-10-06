import { ArrowRight, ExternalLink } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { AccessState } from "@/components/layout/AccessState";
import { PageHeader } from "@/components/layout/PageHeader";
import { PassportView } from "@/components/trust/PassportView";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Link } from "@/i18n/navigation";
import type { Locale } from "@/i18n/routing";
import { serverFetch } from "@/lib/api/server";
import type { SmeTrust, TrustExplanation, TrustSuggestion } from "@/lib/api/types";
import { serverApi } from "@/lib/auth";
import { requireSme } from "@/lib/sme";

const SUGGESTION_LINKS: Record<string, string> = {
  GET_VERIFIED: "/sme/verification",
  CONFIRM_SOCIAL_ACCOUNT: "/sme/store",
  PUBLISH_POLICIES: "/sme/store",
  COMPLETE_PROFILE: "/sme/store",
  ADD_PRODUCTS: "/sme/products/new",
  ADD_PRODUCT_EVIDENCE: "/sme/products",
};

export default async function SmePassportPage({ params }: PageProps<"/[locale]/sme/passport">) {
  const { locale } = await params;
  setRequestLocale(locale as Locale);

  const guard = await requireSme(locale as Locale, `/${locale}/sme/passport`);
  if (guard.kind !== "allowed") {
    return <AccessState kind={guard.kind === "forbidden" ? "forbidden" : "unavailable"} roles={["SME"]} />;
  }
  const [t, tSuggest, tPolicies] = await Promise.all([
    getTranslations("smeTrust"),
    getTranslations("trustSuggestions"),
    getTranslations("policies"),
  ]);
  const trust = await serverApi<SmeTrust>("/sme/trust");
  // The public summary exists only once the store is published.
  const explanation = guard.sme.is_published
    ? await serverFetch<TrustExplanation>(`/stores/${guard.sme.slug}/trust/explanation?locale=${locale}`).catch(() => null)
    : null;

  const suggestionText = (s: TrustSuggestion) => {
    const values: Record<string, string | number> = {};
    for (const [key, value] of Object.entries(s.params)) {
      values[key] = Array.isArray(value)
        ? value.map((v) => tPolicies(v as "returns")).join(", ")
        : (value as string | number);
    }
    const key = s.code as Parameters<typeof tSuggest>[0];
    return tSuggest.has(key) ? tSuggest(key, values as never) : s.code;
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("title")}
        description={t("body")}
        actions={
          guard.sme.is_published ? (
            <Link href={`/stores/${guard.sme.slug}/passport`} className={buttonClasses("secondary")}>
              <ExternalLink aria-hidden="true" className="h-4 w-4" />
              {t("viewPublic")}
            </Link>
          ) : null
        }
      />

      <Card className="space-y-3">
        <h2 className="font-semibold">{t("suggestionsTitle")}</h2>
        {trust.suggestions.length === 0 ? (
          <p className="text-sm text-ink-muted">{t("noSuggestions")}</p>
        ) : (
          <ul className="space-y-2">
            {trust.suggestions.map((s) => {
              const href = SUGGESTION_LINKS[s.code];
              return (
                <li key={s.code} className="flex items-start gap-2 text-sm">
                  <ArrowRight aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
                  {href ? (
                    <Link href={href} className="hover:underline">
                      {suggestionText(s)}
                    </Link>
                  ) : (
                    <span>{suggestionText(s)}</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <PassportView passport={trust} explanation={explanation} />
    </div>
  );
}
