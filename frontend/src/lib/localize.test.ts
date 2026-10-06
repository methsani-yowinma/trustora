import { describe, expect, it } from "vitest";

import { formatDate, formatLkr, localize, localizedString } from "./localize";

describe("localize (seller-written content)", () => {
  it("uses the requested language when the seller provided it", () => {
    expect(localize({ en: "Saree", si: "සාරිය" }, "si")).toEqual({ text: "සාරිය", lang: "si", isFallback: false });
  });

  it("falls back to another language and reports which one, for the lang attribute", () => {
    expect(localize({ en: "Saree" }, "si")).toEqual({ text: "Saree", lang: "en", isFallback: true });
  });

  it("handles missing content", () => {
    expect(localize(null, "en")).toBeNull();
    expect(localizedString(undefined, "en")).toBe("");
  });
});

describe("formatting", () => {
  it("formats rupees with two decimals in both languages", () => {
    expect(formatLkr("12500", "en")).toMatch(/12,500\.00/);
    expect(formatLkr(12500, "si")).toMatch(/12,500\.00/);
  });

  it("formats dates per locale", () => {
    expect(formatDate("2026-10-06T08:00:00Z", "en")).toMatch(/2026/);
    expect(formatDate("2026-10-06T08:00:00Z", "si")).toMatch(/2026/);
  });
});
