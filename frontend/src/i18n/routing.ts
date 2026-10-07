import { defineRouting } from "next-intl/routing";

// Adding Tamil later: add "ta" here and create messages/ta.json.
export const routing = defineRouting({
  locales: ["en", "si"],
  defaultLocale: "en",
});

export type Locale = (typeof routing.locales)[number];
