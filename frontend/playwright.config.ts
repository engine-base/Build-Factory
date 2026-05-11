import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for Build-Factory frontend e2e.
 *
 * 前提:
 *   - backend: http://localhost:8001 で起動済み
 *   - frontend: http://localhost:3000 で起動済み (npm run dev)
 *
 * CI:
 *   - browser binary は `npx playwright install` で別途取得
 *   - `npm run e2e` で実行 (services が落ちている場合は skip)
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
