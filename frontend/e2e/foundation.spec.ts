import { expect, test } from "@playwright/test";

test("root redirects to a locale", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/(en|si)$/);
});

test("home renders in English with the trust dimensions", async ({ page }) => {
  await page.goto("/en");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Know who you are buying from");
  for (const title of ["Business Trust", "Product Trust", "Transaction Trust"]) {
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
  }
  // The platform never promises certainty.
  await expect(page.getByText("Evidence, not guarantees")).toBeVisible();
});

test("home renders in Sinhala", async ({ page }) => {
  await page.goto("/si");
  await expect(page.locator("html")).toHaveAttribute("lang", "si");
  await expect(page.getByRole("heading", { name: "ව්‍යාපාර විශ්වාසය" })).toBeVisible();
  await expect(page.getByText("මෙම ගනුදෙනුව විශ්වාස කළ හැකිද?")).toBeVisible();
});

test("language switcher keeps the current page", async ({ page }) => {
  await page.goto("/en/login");
  await page.getByRole("button", { name: "සිංහල" }).click();
  await expect(page).toHaveURL(/\/si\/login$/);
  await expect(page.getByRole("heading", { name: "Trustora වෙත පිවිසෙන්න" })).toBeVisible();
});

test("protected SME page redirects anonymous users to login with a return path", async ({ page }) => {
  await page.goto("/si/sme");
  await expect(page).toHaveURL(/\/si\/login\?next=%2Fsi%2Fsme$/);
});

test("protected admin page redirects anonymous users to login", async ({ page }) => {
  await page.goto("/en/admin");
  await expect(page).toHaveURL(/\/en\/login\?next=%2Fen%2Fadmin$/);
});

test("signup validates input before contacting Supabase", async ({ page }) => {
  await page.goto("/en/signup?type=sme");
  await expect(page.getByRole("radio", { name: /Business \(SME\)/ })).toBeChecked();
  await page.getByLabel("Email address").fill("not-an-email");
  await page.getByLabel("Password").fill("short");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Enter your name.")).toBeVisible();
  await expect(page.getByText("Enter a valid email address.")).toBeVisible();
  await expect(page.getByText("Password must be at least 8 characters.")).toBeVisible();
});

test("unknown pages show the localized not-found page", async ({ page }) => {
  const response = await page.goto("/si/does-not-exist");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "පිටුව හමු නොවීය" })).toBeVisible();
});

test("security headers are set", async ({ request }) => {
  const response = await request.get("/en");
  expect(response.headers()["x-frame-options"]).toBe("DENY");
  expect(response.headers()["x-content-type-options"]).toBe("nosniff");
  expect(response.headers()["x-powered-by"]).toBeUndefined();
});
