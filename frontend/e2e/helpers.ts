import { expect, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";

// The e2e API serves a stand-in for Supabase Auth (backend/tests/fake_supabase_auth.py) with
// seeded accounts that share one test-only password.
export const API = "http://localhost:8100";
export const PASSWORD = "trustora-e2e-pass";

/** The store signed-in tests buy from (public-page tests assert on the other seeded stores). */
export const TEST_STORE = "kegalle-kitchen";

export const ACCOUNTS = {
  buyer: "buyer@example.test",
  nimal: "nimal@example.test",
  shop: "shop@example.test", // owns Ceylon Crafts
  spice: "spice@example.test", // owns Matale Spice Garden
  kitchen: "kitchen@example.test", // owns Kegalle Kitchen, the store signed-in tests change
  admin: "admin@example.test",
} as const;

/** A customer account reserved for one Playwright project, so parallel projects don't collide. */
export function ownCustomer(testInfo: TestInfo): string {
  return `complain-${testInfo.project.name}@example.test`;
}

/** Signs in through the real login form. */
export async function signIn(page: Page, email: string, next?: string) {
  await page.goto(next ? `/en/login?next=${encodeURIComponent(next)}` : "/en/login");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  // Sign-in, the profile lookup and the role-based redirect can take a while under parallel load.
  await expect(page).not.toHaveURL(/\/login/, { timeout: 20_000 });
}

async function token(request: APIRequestContext, email: string): Promise<string> {
  const response = await request.post(`${API}/auth/v1/token?grant_type=password`, {
    data: { email, password: PASSWORD },
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()).access_token;
}

/** Calls the real API as a seeded user — used to arrange data, never to assert UI behaviour. */
export async function apiAs(request: APIRequestContext, email: string) {
  const headers = { Authorization: `Bearer ${await token(request, email)}` };
  const call = async (method: "GET" | "POST", path: string, data?: unknown) => {
    const response = await request.fetch(`${API}/api/v1${path}`, { method, headers, data });
    expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBeTruthy();
    return response.json();
  };
  return {
    get: (path: string) => call("GET", path),
    post: (path: string, data?: unknown) => call("POST", path, data),
  };
}

/** Places an order for one product of a public store; returns the created order. */
export async function placeOrder(request: APIRequestContext, email: string, storeSlug: string) {
  const products = await (await request.get(`${API}/api/v1/stores/${storeSlug}/products`)).json();
  const product = products.find((p: { in_stock: boolean }) => p.in_stock);
  const items = [{ product_id: product.id, quantity: 1 }];
  const customer = await apiAs(request, email);
  const quote = await customer.post("/checkout/quote", { items, district: "COLOMBO" });
  return customer.post("/checkout", {
    items,
    shipping_address: {
      recipient_name: "E2E Customer",
      phone: "+94 77 123 4567",
      address_line1: "1 Test Lane",
      city: "Colombo",
      district: "COLOMBO",
    },
    payment_method: "COD",
    idempotency_key: crypto.randomUUID(),
    expected_total_lkr: quote.total_lkr,
  });
}
