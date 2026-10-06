import { render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";

import en from "../../messages/en.json";
import si from "../../messages/si.json";

export const MESSAGES = { en, si } as const;

/** Renders with the real translation files, as the app does. */
export function renderWithIntl(ui: ReactElement, locale: "en" | "si" = "en") {
  return render(
    <NextIntlClientProvider locale={locale} messages={MESSAGES[locale]} timeZone="Asia/Colombo">
      {ui}
    </NextIntlClientProvider>,
  );
}
