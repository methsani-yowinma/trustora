import { describe, expect, it } from "vitest";

import { safeNextPath } from "./redirect";

describe("safeNextPath (post-login redirects)", () => {
  it.each([
    ["/en/orders", "/en/orders"],
    ["/si/sme/passport?tab=history#top", "/si/sme/passport?tab=history#top"],
  ])("keeps same-site path %s", (input, expected) => {
    expect(safeNextPath(input)).toBe(expected);
  });

  it.each([
    "https://evil.example/",
    "//evil.example",
    "/\\evil.example",
    "/\t/evil.example", // browsers drop the tab → //evil.example
    "/\n/evil.example",
    "\\\\evil.example",
    "javascript:alert(1)",
    "en/orders",
    "",
    null,
    undefined,
    `/${"a".repeat(3000)}`,
  ])("rejects %j", (input) => {
    expect(safeNextPath(input)).toBeNull();
  });
});
