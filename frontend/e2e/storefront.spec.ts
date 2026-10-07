import { expect, test } from "@playwright/test";

// Seeded by backend/tests/e2e_server.py: "ceylon-crafts" is published and verified,
// "draft-store" exists but is unpublished.

test("published store shows verified identity, evidence and products (English)", async ({ page }) => {
  await page.goto("/en/stores/ceylon-crafts");
  await expect(page.getByRole("heading", { level: 1, name: "Ceylon Crafts" })).toBeVisible();
  await expect(page.getByText("Verified business").first()).toBeVisible();
  await expect(page.getByText("Handloom textiles from Dumbara.")).toBeVisible();

  // Only ownership-confirmed social accounts are listed.
  await expect(page.getByRole("link", { name: /Instagram · @ceylon\.crafts/ })).toBeVisible();
  await expect(page.getByText("unconfirmed.handle")).toHaveCount(0);

  // Active products only; hidden products never appear publicly.
  await expect(page.getByText("Dumbara handloom saree")).toBeVisible();
  await expect(page.getByText("Hidden test product")).toHaveCount(0);
  await expect(page.getByText("Out of stock")).toBeVisible();

  // Authenticity is never implied without evidence.
  await expect(page.getByText("Authenticity not verified").first()).toBeVisible();
  await expect(page.getByText("Confirmed by Trustora")).toBeVisible();
});

test("store content is shown in Sinhala with a language fallback note", async ({ page }) => {
  await page.goto("/si/stores/ceylon-crafts");
  await expect(page.getByText("තහවුරු කළ ව්‍යාපාරය").first()).toBeVisible();
  await expect(page.getByText("දුම්බර අත්යන්ත්‍ර රෙදිපිළි.")).toBeVisible();
  await expect(page.getByText("දුම්බර අත්යන්ත්‍ර සාරිය")).toBeVisible();
  await expect(page.getByText("දින 7ක් ඇතුළත ආපසු භාර ගනී.")).toBeVisible();

  // "Lacquer jewellery box" only exists in English: shown with lang="en" and a fallback note.
  await expect(page.locator('p[lang="en"]', { hasText: "Lacquer jewellery box" })).toBeVisible();
  await expect(page.getByText("විකුණුම්කරු ලබා දුන් භාෂාවෙන් පෙන්වයි.")).toBeVisible();
});

test("unpublished and unknown stores are not found", async ({ page }) => {
  for (const path of ["/en/stores/draft-store", "/en/stores/no-such-store"]) {
    const response = await page.goto(path);
    expect(response?.status()).toBe(404);
  }
});

test("SME and admin management pages require sign-in", async ({ page }) => {
  for (const [path, next] of [
    ["/en/sme/products", "%2Fen%2Fsme%2Fproducts"],
    ["/en/sme/store", "%2Fen%2Fsme%2Fstore"],
    ["/si/admin/verifications", "%2Fsi%2Fadmin%2Fverifications"],
  ]) {
    await page.goto(path);
    await expect(page).toHaveURL(new RegExp(`/login\\?next=${next}$`));
  }
});
