import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import { renderWithIntl } from "@/test/render";

import { chatTurns, pageContext, TrustoraAI } from "./TrustoraAI";

const clientApi = vi.fn();
vi.mock("@/lib/api/browser", () => ({ clientApi: (...args: unknown[]) => clientApi(...args) }));
let pathname = "/en/stores/ceylon-crafts";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

describe("pageContext", () => {
  it("resolves 'this seller' and 'this product' from the page", () => {
    expect(pageContext("/en/stores/ceylon-crafts/passport").context).toEqual({ store_slug: "ceylon-crafts" });
    expect(pageContext("/si/products/20000000-0000-4000-8000-000000000001").context).toEqual({
      product_id: "20000000-0000-4000-8000-000000000001",
    });
    expect(pageContext("/en/discover").context).toBeUndefined();
  });

  it("suggests questions that fit the page", () => {
    expect(pageContext("/en/stores/ceylon-crafts").suggestions).toContain("storeTrust");
    expect(pageContext("/en/products/20000000-0000-4000-8000-000000000001").suggestions).toContain("productVerified");
    expect(pageContext("/en/sme/passport").suggestions).toEqual(["myScore", "improve", "howScore"]);
    expect(pageContext("/en").suggestions).toContain("whereOrder");
  });

  it("ignores malformed store or product segments", () => {
    expect(pageContext("/en/stores/../admin").context).toBeUndefined();
    expect(pageContext("/en/products/not-an-id").context).toBeUndefined();
  });
});

describe("chatTurns", () => {
  it("sends at most 12 recent turns of at most 1000 characters", () => {
    const history = Array.from({ length: 15 }, (_, i) => ({
      role: (i % 2 ? "assistant" : "user") as "user" | "assistant",
      text: `${i} ${"x".repeat(1200)}`,
    }));
    const turns = chatTurns(history);
    expect(turns).toHaveLength(12);
    expect(turns[0].text.startsWith("3 ")).toBe(true);
    expect(turns.every((t) => t.text.length <= 1000)).toBe(true);
    expect(turns.at(-1)?.role).toBe("user");
  });
});

describe("TrustoraAI panel", () => {
  beforeEach(() => {
    clientApi.mockReset();
    pathname = "/en/stores/ceylon-crafts";
  });

  it("asks with the page context and shows the answer with its sources", async () => {
    clientApi.mockResolvedValue({
      reply: "Ceylon Crafts has the trust level DEVELOPING (62/100).",
      used_tools: ["get_seller_trust"],
      sources: [{ kind: "STORE", ref: "ceylon-crafts", label: "Ceylon Crafts" }],
      draft: null,
      model: "fake",
      provenance: "AI_ANALYSIS",
    });
    const user = userEvent.setup();
    renderWithIntl(<TrustoraAI />);

    await user.click(screen.getByRole("button", { name: "Open Trustora AI assistant" }));
    expect(screen.getByText(/Trust scores are calculated by Trustora's rules, not by AI/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Is this seller trustworthy?" }));

    await waitFor(() => expect(screen.getByText(/DEVELOPING \(62\/100\)/)).toBeTruthy());
    const [path, options] = clientApi.mock.calls[0];
    expect(path).toBe("/chat");
    expect(options.body).toEqual({
      messages: [{ role: "user", text: "Is this seller trustworthy?" }],
      locale: "en",
      context: { store_slug: "ceylon-crafts" },
    });
    expect(screen.getByRole("link", { name: "Trust Passport: Ceylon Crafts" }).getAttribute("href")).toBe(
      "/stores/ceylon-crafts/passport",
    );
  });

  it("shows a clear message when AI is unavailable and keeps the question for a retry", async () => {
    clientApi.mockImplementation(async () => {
      throw new ApiError(503, "ai_unavailable", "down");
    });
    const user = userEvent.setup();
    renderWithIntl(<TrustoraAI />);
    await user.click(screen.getByRole("button", { name: "Open Trustora AI assistant" }));
    const input = screen.getByRole("textbox", { name: "Message Trustora AI" });
    await user.type(input, "Is this seller genuine?{Enter}");

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe("Trustora AI is not available right now. Please try again later."),
    );
    expect((input as HTMLTextAreaElement).value).toBe("Is this seller genuine?");
  });

  it("works in Sinhala", async () => {
    clientApi.mockResolvedValue({ reply: "මෙය තීරණය කිරීමට ප්‍රමාණවත් තහවුරු කළ සාක්ෂි නොමැත.", used_tools: [], sources: [], draft: null, model: "fake", provenance: "AI_ANALYSIS" });  // prettier-ignore
    pathname = "/si";
    const user = userEvent.setup();
    renderWithIntl(<TrustoraAI />, "si");
    await user.click(screen.getByRole("button", { name: "Trustora AI සහායකයා විවෘත කරන්න" }));
    await user.click(screen.getByRole("button", { name: "මගේ ඇණවුම කොහෙද?" }));
    await waitFor(() => expect(screen.getByText(/ප්‍රමාණවත් තහවුරු කළ සාක්ෂි නොමැත/)).toBeTruthy());
    expect(clientApi.mock.calls[0][1].body.locale).toBe("si");
  });

  it("closes with Escape", async () => {
    const user = userEvent.setup();
    renderWithIntl(<TrustoraAI />);
    await user.click(screen.getByRole("button", { name: "Open Trustora AI assistant" }));
    expect(screen.getByRole("dialog")).toBeTruthy();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
