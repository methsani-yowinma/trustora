import { existsSync } from "node:fs";
import { join } from "node:path";

import { defineConfig, devices } from "@playwright/test";

const PORT = 3100;
const API_PORT = 8100;

// Signed-out flows only: no test signs in, so a placeholder Supabase project is enough.
// The API is the real FastAPI app on an embedded, seeded Postgres (backend/tests/e2e_server.py).
const testEnv = {
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://placeholder.supabase.co",
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "placeholder",
  NEXT_PUBLIC_API_URL: `http://localhost:${API_PORT}`,
};

// Playwright loads this config as CommonJS, so __dirname is available.
const backendDir = join(__dirname, "..", "backend");
const python =
  process.env.E2E_PYTHON ??
  [join(backendDir, ".venv", "Scripts", "python.exe"), join(backendDir, ".venv", "bin", "python")].find(
    existsSync,
  ) ??
  "python";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  // Each worker drives a browser against one local Next.js + API pair; more overloads laptops.
  workers: process.env.CI ? 2 : 4,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "retain-on-failure",
    // Set PW_CHANNEL=msedge (or chrome) to use an installed browser instead of Playwright's Chromium.
    channel: process.env.PW_CHANNEL || undefined,
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: [
    {
      command: `"${python}" -m tests.e2e_server --port ${API_PORT}`,
      cwd: backendDir,
      url: `http://localhost:${API_PORT}/api/v1/health`,
      timeout: 120_000,
      reuseExistingServer: false,
    },
    {
      command: `npx next build && npx next start -p ${PORT}`,
      url: `http://localhost:${PORT}/en`,
      timeout: 300_000,
      reuseExistingServer: !process.env.CI,
      env: testEnv,
    },
  ],
});
