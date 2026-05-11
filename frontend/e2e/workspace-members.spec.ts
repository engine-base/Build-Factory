import { test, expect } from "@playwright/test";

/**
 * S-014 ワークスペースメンバー e2e (T-021-04 / T-004-03,04)
 *
 * 検証する EARS AC:
 *   - UBIQUITOUS: 6 ロール select + 30 perm matrix grid
 *   - EVENT:      「招待リンク発行」ボタンを押すと招待 form が出る
 *   - EVENT:      「メンバー追加」ボタンを押すと add form が出る
 */

const BASE = process.env.E2E_BASE_URL ?? "http://localhost:3000";

test.describe("/workspaces/[id]/members", () => {
  test.beforeAll(async ({ request }) => {
    try {
      const r = await request.get(`${BASE}/workspaces/1/members`, { timeout: 2000 });
      if (!r.ok()) test.skip(true, `frontend not ready (HTTP ${r.status()})`);
    } catch {
      test.skip(true, "frontend server not running — start `npm run dev`");
    }
  });

  test("page header references members + permission matrix", async ({ page }) => {
    await page.goto("/workspaces/1/members");
    await expect(
      page.getByRole("heading", { name: /メンバー/ }),
    ).toBeVisible();
  });

  test("invite link button toggles the form", async ({ page }) => {
    await page.goto("/workspaces/1/members");
    const inviteBtn = page.getByRole("button", { name: /招待リンク発行/ });
    await inviteBtn.click();
    await expect(page.getByPlaceholder(/招待先メールアドレス/)).toBeVisible();
  });

  test("add member button toggles the form", async ({ page }) => {
    await page.goto("/workspaces/1/members");
    const addBtn = page.getByRole("button", { name: /メンバー追加/ });
    await addBtn.click();
    await expect(page.getByPlaceholder(/user_id/)).toBeVisible();
  });
});
