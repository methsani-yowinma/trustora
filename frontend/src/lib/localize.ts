import type { LocalizedText } from "@/lib/api/types";

/**
 * Picks SME-authored content in the requested locale, falling back to another available
 * locale. Returns the language actually used so it can be set as the element's `lang`.
 */
export function localize(
  text: LocalizedText | null | undefined,
  locale: string,
): { text: string; lang: string; isFallback: boolean } | null {
  if (!text) return null;
  const preferred = text[locale as keyof LocalizedText];
  if (preferred) return { text: preferred, lang: locale, isFallback: false };
  for (const [lang, value] of Object.entries(text)) {
    if (value) return { text: value, lang, isFallback: true };
  }
  return null;
}

/** Plain string version for places that only need text (titles, alt text). */
export function localizedString(text: LocalizedText | null | undefined, locale: string): string {
  return localize(text, locale)?.text ?? "";
}

export function formatLkr(amount: string | number, locale: string): string {
  return new Intl.NumberFormat(locale === "si" ? "si-LK" : "en-LK", {
    style: "currency",
    currency: "LKR",
    minimumFractionDigits: 2,
  }).format(Number(amount));
}

export function formatDate(value: string, locale: string): string {
  return new Intl.DateTimeFormat(locale === "si" ? "si-LK" : "en-LK", { dateStyle: "medium" }).format(
    new Date(value),
  );
}
