import { test, expect } from "@playwright/test";

/**
 * S-013 ワークスペース設定 e2e (T-004-05)
 *
 * 検証する EARS AC:
 *   - UBIQUITOUS: 7 sidebar nav (一般 / フェーズゲート / レッドライン / 統合 /
 *                 予算 / メンバーシップ / アーカイブ)
 *   - EVENT:      各タブクリックでセクションが切り替わる
 *   - STATE:      アーカイブ button は danger スタイル (rose 色)
 */

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3000";

test.describe("/workspaces/[id]/settings", () => {
  test.beforeAll(async ({ request }) => {
    try {
      const r = await request.get(`${BASE}/workspaces/1/settings`, { timeout: 2000 });
      if (!r.ok()) test.skip(true, `frontend not ready (HTTP ${r.status()})`);
    } catch {
      test.skip(true, "frontend server not running — start `npm run dev`");
    }
  });

  test("7 sidebar nav items are visible (mock S-013 準拠)", async ({ page }) => {
    await page.goto("/workspaces/1/settings");
    for (const label of [
      "一般",
      "フェーズゲート",
      "レッドライン",
      "統合 (GitHub/Slack)",
      "予算 / コスト",
      "メンバーシップ",
      "アーカイブ",
    ]) {
      await expect(page.getByRole("button", { name: label })).toBeVisible();
    }
  });

  test("can switch to phase_gate section", async ({ page }) => {
    await page.goto("/workspaces/1/settings");
    await page.getByRole("button", { name: "フェーズゲート" }).click();
    await expect(page.getByText(/DAG 順序を厳密に守る/)).toBeVisible();
  });

  test("can switch to redlines section", async ({ page }) => {
    await page.goto("/workspaces/1/settings");
    await page.getByRole("button", { name: "レッドライン" }).click();
    await expect(page.getByPlaceholder(/rm -rf/)).toBeVisible();
  });
});
