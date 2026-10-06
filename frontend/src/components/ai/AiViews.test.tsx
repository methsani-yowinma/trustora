import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AiAnalysis, TrustExplanation } from "@/lib/api/types";
import { renderWithIntl } from "@/test/render";

import { AiAnalysisView, AiSummaryCard } from "./AiViews";

const explanation = (source: "AI" | "TEMPLATE", locale: "en" | "si" = "en"): TrustExplanation => ({
  text: "Ceylon Crafts currently has a trust level of “Developing” (62/100).",
  source,
  locale,
  model: source === "AI" ? "gemini-2.5-flash" : null,
  rules_version: "2026.10-3",
  generated_at: "2026-10-06T08:00:00Z",
});

describe("AiSummaryCard", () => {
  it("labels AI-written text and says the score is not from AI", () => {
    renderWithIntl(<AiSummaryCard explanation={explanation("AI")} />);
    expect(screen.getByText("AI summary")).toBeTruthy();
    expect(screen.getByText(/The score itself is calculated by Trustora's rules, not by AI/)).toBeTruthy();
  });

  it("shows template text without any AI label", () => {
    renderWithIntl(<AiSummaryCard explanation={explanation("TEMPLATE")} />);
    expect(screen.queryByText("AI summary")).toBeNull();
    expect(screen.getByText("Generated from the signals on this page.")).toBeTruthy();
  });

  it("marks the language of the summary text", () => {
    renderWithIntl(<AiSummaryCard explanation={{ ...explanation("TEMPLATE", "si"), text: "සාරාංශය" }} />, "si");
    expect(screen.getByText("සාරාංශය", { selector: "p" }).getAttribute("lang")).toBe("si");
  });
});

const base = { id: "a1", status: "DONE", model: "gemini-test", error_code: null, created_at: "2026-10-06T08:00:00Z", provenance: "AI_ANALYSIS" } as const;

describe("AiAnalysisView", () => {
  it("presents complaint triage as AI analysis of an allegation, not a finding", () => {
    const analysis = { ...base, kind: "COMPLAINT", checks: null,
      output: { category: "DELIVERY", severity: "HIGH", sentiment: "NEGATIVE", summary: "Parcel not received." } } as unknown as AiAnalysis;  // prettier-ignore
    renderWithIntl(<AiAnalysisView analysis={analysis} />);
    expect(screen.getByText("AI triage")).toBeTruthy();
    expect(screen.getByText("AI analysis")).toBeTruthy(); // provenance badge
    expect(screen.getByText(/It is not a finding/)).toBeTruthy();
    expect(screen.getByText("High")).toBeTruthy();
  });

  it("shows Trustora's own checks separately from what AI extracted", () => {
    const analysis = { ...base, kind: "DOCUMENT", checks: { registered_name: "MATCH", registration_number: "MISMATCH" },
      output: { business_name: "Draft Store (Pvt) Ltd", registration_number: "PV 99999", product_names: [] } } as unknown as AiAnalysis;  // prettier-ignore
    renderWithIntl(<AiAnalysisView analysis={analysis} />);
    expect(screen.getByText("Checked by Trustora against the application")).toBeTruthy();
    expect(screen.getByText("Registered name: Matches")).toBeTruthy();
    expect(screen.getByText("Registration number: Does not match")).toBeTruthy();
    expect(screen.getByText("Extracted by AI")).toBeTruthy();
    expect(screen.queryByText("Products mentioned")).toBeNull(); // empty fields are hidden
    expect(screen.getByText(/AI never makes verification decisions/)).toBeTruthy();
  });

  it("explains failed analyses instead of showing output", () => {
    const analysis = { ...base, kind: "DOCUMENT", status: "FAILED", output: null, checks: null } as unknown as AiAnalysis;
    renderWithIntl(<AiAnalysisView analysis={analysis} />);
    expect(screen.getByText("AI could not analyse this item. Review it manually.")).toBeTruthy();
  });
});
