import { expect, test } from "@playwright/test";

// Seed (backend/tests/e2e_server.py): "ceylon-crafts" sells a Dumbara handloom saree (LKR 12,500,
// stock 4) and a lacquer box (out of stock); "matale-spice" sells cinnamon sticks (LKR 850).

test("discover search finds products with their store's trust", async ({ page }) => {
  await page.goto("/en/discover?q=saree");
  await expect(page.getByText("1 result")).toBeVisible();
  const card = page.getByRole("link", { name: /Dumbara handloom saree/ });
  await expect(card).toContainText("Ceylon Crafts");
  await expect(card).toContainText("LKR 12,500.00");
  await expect(card).toContainText("Authenticity not verified");

  await page.goto("/en/discover?tab=stores&q=Matale");
  await expect(page.getByRole("link", { name: /Matale Spice Garden/ })).toBeVisible();
});

test("discover works in Sinhala", async ({ page }) => {
  await page.goto("/si/discover?q=සාරිය");
  await expect(page.getByText("දුම්බර අත්යන්ත්‍ර සාරිය")).toBeVisible();
  await expect(page.getByText("ප්‍රතිඵල 1")).toBeVisible();
});

test("product page links to the store's trust and adds to cart", async ({ page }) => {
  await page.goto("/en/discover?q=saree");
  await page.getByRole("link", { name: /Dumbara handloom saree/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Dumbara handloom saree" })).toBeVisible();
  await expect(page.getByRole("link", { name: "View Trust Passport" })).toBeVisible();
  await expect(page.getByText(/never from how a photo looks/)).toBeVisible();

  await page.getByRole("button", { name: "Increase quantity" }).click();
  await page.getByRole("button", { name: "Add to cart" }).click();
  await expect(page.getByText("Added to cart")).toBeVisible();
  await expect(page.getByRole("link", { name: "Cart, 2 items" })).toBeVisible();
});

test("cart is priced by the server and delivery depends on the district", async ({ page }) => {
  await page.goto("/en/discover?q=saree");
  await page.getByRole("link", { name: /Dumbara handloom saree/ }).click();
  await page.getByRole("button", { name: "Add to cart" }).click();
  await page.goto("/en/cart");

  await expect(page.getByText("LKR 12,500.00").first()).toBeVisible();
  await expect(page.getByText("LKR 12,850.00")).toBeVisible(); // + 350 delivery to Colombo
  await page.getByLabel("Deliver to district").selectOption("JAFFNA");
  await expect(page.getByText("LKR 13,100.00")).toBeVisible(); // + 600 delivery to Jaffna

  // Signed out: checkout asks for sign-in and returns to the cart afterwards.
  await page.getByRole("link", { name: "Sign in to check out" }).click();
  await expect(page).toHaveURL(/\/en\/login\?next=%2Fen%2Fcart$/);
});

test("a cart holds products from one store at a time", async ({ page }) => {
  await page.goto("/en/discover?q=saree");
  await page.getByRole("link", { name: /Dumbara handloom saree/ }).click();
  await page.getByRole("button", { name: "Add to cart" }).click();

  await page.goto("/en/discover?q=cinnamon");
  await page.getByRole("link", { name: /Ceylon cinnamon sticks/ }).click();
  await page.getByRole("button", { name: "Add to cart" }).click();
  await expect(page.getByText("Your cart has items from Ceylon Crafts.")).toBeVisible();
  await page.getByRole("button", { name: "Replace cart" }).click();
  await expect(page.getByText("Added to cart")).toBeVisible();

  await page.goto("/en/cart");
  await expect(page.getByText("Ceylon cinnamon sticks")).toBeVisible();
  await expect(page.getByText("Dumbara handloom saree")).toHaveCount(0);
});

test("out-of-stock products cannot be added", async ({ page }) => {
  await page.goto("/en/discover?q=lacquer");
  await page.getByRole("link", { name: /Lacquer jewellery box/ }).click();
  await expect(page.getByText("Out of stock").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Add to cart" })).toHaveCount(0);
});

test("order pages require a customer sign-in", async ({ page }) => {
  for (const [path, next] of [
    ["/en/checkout", "%2Fen%2Fcheckout"],
    ["/en/orders", "%2Fen%2Forders"],
    ["/en/sme/orders", "%2Fen%2Fsme%2Forders"],
  ]) {
    await page.goto(path);
    await expect(page).toHaveURL(new RegExp(`/login\\?next=${next}$`));
  }
});
