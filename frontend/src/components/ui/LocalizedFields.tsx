"use client";

import { useTranslations } from "next-intl";

import type { LocalizedText } from "@/lib/api/types";

import { Field, TextAreaField } from "./Field";

/**
 * English + Sinhala inputs for one piece of SME-authored content. Field names are
 * `${name}.en` and `${name}.si`; read them back with `readLocalized`.
 */
export function LocalizedFields({
  name,
  label,
  defaultValue,
  multiline = false,
  maxLength,
  required = false,
}: {
  name: string;
  label: string;
  defaultValue?: LocalizedText | null;
  multiline?: boolean;
  maxLength: number;
  required?: boolean;
}) {
  const t = useTranslations("common");
  const locales = [
    { code: "en" as const, label: t("english") },
    { code: "si" as const, label: t("sinhala") },
  ];

  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium text-ink">{label}</legend>
      <div className="grid gap-3 md:grid-cols-2">
        {locales.map(({ code, label: languageLabel }) =>
          multiline ? (
            <TextAreaField
              key={code}
              lang={code}
              name={`${name}.${code}`}
              label={languageLabel}
              defaultValue={defaultValue?.[code] ?? ""}
              maxLength={maxLength}
            />
          ) : (
            <Field
              key={code}
              lang={code}
              name={`${name}.${code}`}
              label={languageLabel}
              defaultValue={defaultValue?.[code] ?? ""}
              maxLength={maxLength}
              required={required && code === "en"}
            />
          ),
        )}
      </div>
    </fieldset>
  );
}

/** Reads a LocalizedFields group from FormData; returns null when every language is blank. */
export function readLocalized(form: FormData, name: string): LocalizedText | null {
  const value: LocalizedText = {};
  for (const code of ["en", "si"] as const) {
    const text = String(form.get(`${name}.${code}`) ?? "").trim();
    if (text) value[code] = text;
  }
  return Object.keys(value).length ? value : null;
}
