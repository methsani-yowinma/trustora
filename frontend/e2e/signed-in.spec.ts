import { expect, test } from "@playwright/test";

import { ACCOUNTS, API, apiAs, ownCustomer, placeOrder, signIn, TEST_STORE } from "./helpers";

// Signed-in journeys against the real API and database. Sign-in goes through the real login
// form; tokens come from the Supabase Auth stand-in served by the e2e API.

test.describe("customers", () => {
  test("sign in, see the account in the header and sign out", async ({ page }) => {
    await signIn(page, ACCOUNTS.nimal);
    await expect(page.getByRole("link", { name: "My orders" }).first()).toBeVisible();
    await page.getByRole("button", { name: "Sign out" }).first().click();
    await expect(page.getByRole("link", { name: "Sign in" }).first()).toBeVisible();
  });

  test("wrong password is rejected", async ({ page }) => {
    await page.goto("/en/login");
    await page.getByLabel("Email address").fill(ACCOUNTS.nimal);
    await page.getByLabel("Password").fill("not-the-password");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByText("Email or password is incorrect.")).toBeVisible();
    await expect(page).toHaveURL(/\/en\/login/);
  });

  test("buy through the cart and checkout, then track the order", async ({ page }, testInfo) => {
    await signIn(page, ownCustomer(testInfo));
    await page.goto(`/en/stores/${TEST_STORE}`);
    await page.getByRole("link", { name: /Kithul treacle/ }).first().click();
    await page.getByRole("button", { name: "Add to cart" }).click();
    await page.getByRole("link", { name: "View cart" }).click();
    await page.getByRole("link", { name: "Continue to checkout" }).click();

    await page.getByLabel("Recipient name").fill("Kumari Perera");
    await page.getByLabel("Phone number").fill("+94 77 123 4567");
    await page.getByLabel("Address line 1").fill("12 Temple Road");
    await page.getByLabel("City / town").fill("Kandy");
    await page.getByRole("button", { name: "Place order" }).click();

    await expect(page).toHaveURL(/\/en\/orders\/[0-9a-f-]{36}$/);
    await expect(page.getByRole("heading", { level: 1, name: /^Order TR-[A-Z0-9]{8}$/ })).toBeVisible();
    await expect(page.getByText("Order placed")).toBeVisible();
  });

  test("customer A cannot open customer B's order", async ({ page, request }) => {
    const order = await placeOrder(request, ACCOUNTS.nimal, TEST_STORE);
    await signIn(page, ACCOUNTS.buyer);
    const response = await page.goto(`/en/orders/${order.id}`);
    expect(response?.status()).toBe(404);
    await expect(page.getByText("Page not found")).toBeVisible();
    await expect(page.getByText(order.order_number)).toHaveCount(0);
  });

  test("customers cannot open seller or admin areas", async ({ page }) => {
    await signIn(page, ACCOUNTS.nimal);
    await page.goto("/en/admin");
    await expect(page.getByText("You don’t have access to this page")).toBeVisible();
    await page.goto("/en/sme/orders");
    await expect(page.getByText("You don’t have access to this page")).toBeVisible();
  });
});

test.describe("sellers", () => {
  test("a seller sees and confirms a new order", async ({ page, request }) => {
    const order = await placeOrder(request, ACCOUNTS.nimal, TEST_STORE);
    await signIn(page, ACCOUNTS.kitchen);
    await expect(page).toHaveURL(/\/en\/sme$/);
    await page.goto(`/en/sme/orders/${order.id}`);
    await expect(page.getByText(order.order_number).first()).toBeVisible();
    await page.getByRole("button", { name: "Confirm order" }).click();
    await expect(page.getByRole("button", { name: "Mark as dispatched" })).toBeVisible();
  });

  test("seller A cannot open seller B's products or orders", async ({ page, request }) => {
    const [product] = await (await request.get(`${API}/api/v1/stores/${TEST_STORE}/products`)).json();
    const order = await placeOrder(request, ACCOUNTS.nimal, TEST_STORE);
    await signIn(page, ACCOUNTS.spice); // owns Matale Spice Garden, not Kegalle Kitchen

    let response = await page.goto(`/en/sme/products/${product.id}`);
    expect(response?.status()).toBe(404);
    response = await page.goto(`/en/sme/orders/${order.id}`);
    expect(response?.status()).toBe(404);

    await page.goto("/en/sme/orders");
    await expect(page.getByText(order.order_number)).toHaveCount(0);
  });
});

test.describe("administrators", () => {
  test("an admin approves a business verification", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "desktop", "one-time decision on shared seed data");
    await signIn(page, ACCOUNTS.admin);
    await expect(page).toHaveURL(/\/en\/admin$/);
    await page.goto("/en/admin/verifications");
    await page.getByRole("link", { name: /Draft Store/ }).first().click();
    await expect(page.getByText("PV 00123")).toBeVisible();
    await page.getByLabel("Note to the business").fill("Registration certificate checked against the registry.");
    await page.getByRole("button", { name: "Approve verification" }).click();
    await expect(page.getByText("Decided on", { exact: false })).toBeVisible();
  });

  test("sellers cannot open admin pages", async ({ page }) => {
    await signIn(page, ACCOUNTS.shop);
    await page.goto("/en/admin/verifications");
    await expect(page.getByText("You don’t have access to this page")).toBeVisible();
  });
});

test.describe("Trustora AI for signed-in users", () => {
  test("answers from the customer's own orders and drafts a complaint they confirm", async ({ page, request }, testInfo) => {
    const email = ownCustomer(testInfo);
    const order = await placeOrder(request, email, TEST_STORE);
    await signIn(page, email);

    await page.getByRole("button", { name: "Open Trustora AI assistant" }).click();
    const panel = page.getByRole("dialog", { name: "Trustora AI" });
    await panel.getByRole("button", { name: "Where is my order?" }).click();
    await expect(panel.getByText(new RegExp(`Your orders: .*${order.order_number}`))).toBeVisible();

    const input = panel.getByRole("textbox", { name: "Message Trustora AI" });
    await input.fill("I want to complain about my order");
    await input.press("Enter");
    await expect(panel.getByText("Complaint draft (not submitted)")).toBeVisible();
    await expect(panel.getByLabel("Description")).toHaveValue("My order has not arrived yet.");

    // Nothing exists until the customer submits the draft.
    const customer = await apiAs(request, email);
    const before = await customer.get(`/orders/${order.id}`);
    expect(before.complaint).toBeNull();

    await panel.getByRole("button", { name: "Submit complaint" }).click();
    await expect(panel.getByText("Complaint submitted.")).toBeVisible();
    const after = await customer.get(`/orders/${order.id}`);
    expect(after.complaint.status).toBe("SUBMITTED");
  });

  test("does not reveal another customer's orders", async ({ page, request }) => {
    const order = await placeOrder(request, ACCOUNTS.nimal, TEST_STORE);
    await signIn(page, ACCOUNTS.buyer);
    await page.getByRole("button", { name: "Open Trustora AI assistant" }).click();
    const panel = page.getByRole("dialog", { name: "Trustora AI" });
    await panel.getByRole("button", { name: "Where is my order?" }).click();
    await expect(panel.getByText(/Your orders:|You have no orders yet\./)).toBeVisible();
    await expect(panel.getByText(order.order_number)).toHaveCount(0);
  });
});

test("the signed-in experience is available in Sinhala", async ({ page }) => {
  await signIn(page, ACCOUNTS.nimal);
  await page.goto("/si/orders");
  await expect(page.getByRole("heading", { level: 1, name: "මගේ ඇණවුම්" })).toBeVisible();
});
