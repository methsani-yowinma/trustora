import { expect, test } from "@playwright/test";

// Redirect validation is unit-tested in src/lib/redirect.test.ts.

test("pages send a Content-Security-Policy and render without violations", async ({ page }) => {
  const violations: string[] = [];
  page.on("console", (message) => {
    if (/Content Security Policy|Refused to/i.test(message.text())) violations.push(message.text());
  });

  const response = await page.goto("/en/stores/ceylon-crafts");
  const csp = response?.headers()["content-security-policy"] ?? "";
  expect(csp).toContain("frame-ancestors 'none'");
  expect(csp).toContain("object-src 'none'");
  expect(csp).toContain("connect-src 'self' http://localhost:8100");
  expect(response?.headers()["x-frame-options"]).toBe("DENY");

  // Client-side features still work under the policy: hydration, API calls, the assistant.
  await page.getByRole("button", { name: "Open Trustora AI assistant" }).click();
  await page.getByRole("button", { name: "Is this seller trustworthy?" }).click();
  await expect(page.getByText("calculated by Trustora's rules.")).toBeVisible();
  await page.goto("/si/stores/ceylon-crafts/passport");
  await page.goto("/en/discover");

  expect(violations).toEqual([]);
});
