import { expect, test } from "@playwright/test";

// The e2e API uses a deterministic stand-in for Gemini that calls the real get_seller_trust tool
// (backend/tests/e2e_server.py), so these tests check the UI against real, authorized data.

test("Trustora AI answers from the store's real trust data, with a source link", async ({ page }) => {
  await page.goto("/en/stores/ceylon-crafts");
  const launcher = page.getByRole("button", { name: "Open Trustora AI assistant" });
  await launcher.click();

  const panel = page.getByRole("dialog", { name: "Trustora AI" });
  await expect(panel).toBeVisible();
  await expect(panel.getByText("Trust scores are calculated by Trustora's rules, not by AI.")).toBeVisible();
  await expect(panel.getByRole("textbox", { name: "Message Trustora AI" })).toBeFocused();

  await panel.getByRole("button", { name: "Is this seller trustworthy?" }).click();
  await expect(panel.getByText("Ceylon Crafts has the trust level DEVELOPING (62/100)")).toBeVisible();
  const source = panel.getByRole("link", { name: "Trust Passport: Ceylon Crafts" });
  await expect(source).toHaveAttribute("href", "/en/stores/ceylon-crafts/passport");

  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(launcher).toBeFocused();
});

test("Trustora AI says when there is not enough evidence", async ({ page }) => {
  await page.goto("/en");
  await page.getByRole("button", { name: "Open Trustora AI assistant" }).click();
  const panel = page.getByRole("dialog", { name: "Trustora AI" });
  await expect(panel.getByRole("button", { name: "Where is my order?" })).toBeVisible();

  const input = panel.getByRole("textbox", { name: "Message Trustora AI" });
  await input.fill("Is Kandy Gems genuine?");
  await input.press("Enter");
  await expect(panel.getByText("Is Kandy Gems genuine?")).toBeVisible();
  await expect(panel.getByText("There isn't enough verified evidence to determine this.")).toBeVisible();
  await expect(input).toHaveValue("");
});

test("Trustora AI is available in Sinhala", async ({ page }) => {
  await page.goto("/si/stores/ceylon-crafts");
  await page.getByRole("button", { name: "Trustora AI සහායකයා විවෘත කරන්න" }).click();
  const panel = page.getByRole("dialog", { name: "Trustora AI" });
  await expect(panel.getByText("Trustora හි තහවුරු කළ වාර්තා මත පදනම් පිළිතුරු")).toBeVisible();
  await panel.getByRole("button", { name: "මේ විකුණුම්කරු විශ්වාස කරන්න පුළුවන්ද?" }).click();
  await expect(panel.getByRole("link", { name: "Trust Passport: Ceylon Crafts" })).toHaveAttribute(
    "href",
    "/si/stores/ceylon-crafts/passport",
  );
});

test("Trustora AI uses the full width on phones", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "phone layout only");
  await page.goto("/en");
  await page.getByRole("button", { name: "Open Trustora AI assistant" }).click();
  const box = await page.getByRole("dialog", { name: "Trustora AI" }).boundingBox();
  const viewport = page.viewportSize();
  expect(box?.width).toBe(viewport?.width);
  // The panel's own close button replaces the launcher, which would otherwise cover the input.
  await expect(page.getByRole("button", { name: "Open Trustora AI assistant" })).toBeHidden();
  await page.getByRole("button", { name: "Close assistant" }).click();
  await expect(page.getByRole("button", { name: "Open Trustora AI assistant" })).toBeVisible();
});
