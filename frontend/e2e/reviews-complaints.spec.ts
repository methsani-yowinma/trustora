import { expect, test } from "@playwright/test";

// Seed (backend/tests/e2e_server.py): "matale-spice" has one verified review with a seller
// response, and one open DELIVERY complaint whose text must never be shown publicly.

test("store page shows verified reviews and the seller's response", async ({ page }) => {
  await page.goto("/en/stores/matale-spice");
  await expect(page.getByRole("heading", { name: "Verified buyer reviews" })).toBeVisible();
  await expect(page.getByText("1 review")).toBeVisible();
  await expect(page.getByText("Fresh cinnamon, well packed.")).toBeVisible();
  await expect(page.getByText("Verified buyer").first()).toBeVisible();
  await expect(page.getByText("Thank you for shopping with us!")).toBeVisible();
  await expect(page.getByRole("img", { name: "5 stars" }).first()).toBeVisible();
});

test("open complaints are shown only as customer allegations, without their text", async ({ page }) => {
  await page.goto("/en/stores/matale-spice");
  const record = page.locator("section, div").filter({ has: page.getByRole("heading", { name: "Complaints on Trustora" }) }).last();
  await expect(record.getByText("Customer allegation: Delivery")).toBeVisible();
  await expect(record.getByText("Customer allegation", { exact: true })).toBeVisible();
  await expect(record.getByText(/do not affect the score/)).toBeVisible();
  await expect(page.getByText(/Private complaint text/)).toHaveCount(0);
});

test("passport lists the open complaint as an unscored allegation", async ({ page }) => {
  await page.goto("/en/stores/matale-spice/passport");
  const signal = page.getByRole("listitem").filter({ hasText: "1 open customer complaint (allegations, not yet reviewed)" });
  await expect(signal).toBeVisible();
  await expect(signal.getByText("Customer allegation")).toBeVisible();
  await expect(signal.getByText(/points/)).toHaveCount(0);
});

test("complaint record is available in Sinhala", async ({ page }) => {
  await page.goto("/si/stores/matale-spice");
  await expect(page.getByText("පාරිභෝගික චෝදනාව: බෙදාහැරීම")).toBeVisible();
  await expect(page.getByText("තහවුරු කළ ගැනුම්කරුවන්ගේ සමාලෝචන")).toBeVisible();
});

test("complaint management pages require sign-in", async ({ page }) => {
  for (const [path, next] of [
    ["/en/sme/complaints", "%2Fen%2Fsme%2Fcomplaints"],
    ["/en/sme/reviews", "%2Fen%2Fsme%2Freviews"],
    ["/en/admin/complaints", "%2Fen%2Fadmin%2Fcomplaints"],
  ]) {
    await page.goto(path);
    await expect(page).toHaveURL(new RegExp(`/login\\?next=${next}$`));
  }
});
