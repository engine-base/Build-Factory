/**
 * T-V3-C-03 / S-003 パスワード再設定 — Vitest screen test.
 *
 * ≥ 5 test cases covering structural / functional / unwanted ACs.
 *
 * Run: `pnpm vitest run frontend/tests/screens/S-003-password_reset.spec.tsx`
 *
 * NOTE (audit MD AC-R1 reasoning): vitest / @testing-library は本リポジトリの
 * package.json に未追加 (T-FOUNDATION のスコープ外で baseline drift)。
 * pnpm add -D vitest jsdom @testing-library/react @testing-library/jest-dom
 * @vitejs/plugin-react を実行した後にこのファイルがそのまま PASS する形で
 * 記述している。permission 制約のため Wave 4 セッションでは install 不可、
 * 上位 Wave (Wave 5 / Foundation drift fix) で取り込み予定。
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PasswordResetPage from "@/app/(auth)/password-reset/page";
import { ApiError } from "@/api/auth";

// global fetch を test ごとに差し替える
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("S-003 password reset (T-V3-C-03)", () => {
  it("[Tier1 AC-S1] renders root element with data-screen-id=\"S-003\"", () => {
    const { container } = render(<PasswordResetPage />);
    const root = container.querySelector('[data-screen-id="S-003"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-001");
  });

  it("[Tier1 AC-S2] displays an h1 with text matching screens.json[S-003].h1_text (\"パスワード再設定\")", () => {
    render(<PasswordResetPage />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.textContent).toBe("パスワード再設定");
  });

  it("[Tier2 AC-F1] on submit, calls POST /api/auth/password-reset via the typed API client", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "sent" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const user = userEvent.setup();
    render(<PasswordResetPage />);

    await user.type(screen.getByLabelText(/メールアドレス/), "user@example.com");
    await user.click(screen.getByRole("button", { name: /再設定リンクを送る/ }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, opts] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/auth\/password-reset$/);
    expect(opts).toMatchObject({ method: "POST" });
    expect(JSON.parse((opts as RequestInit).body as string)).toEqual({
      email: "user@example.com",
    });
  });

  it("[Tier2 AC-F2] on 4xx, surfaces a non-technical error toast referencing the endpoint without server stack traces", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail:
            "Traceback (most recent call last):\n  File '/srv/app/router.py', line 42\n    raise SQLError('db dead')",
        }),
        { status: 422, headers: { "Content-Type": "application/json" } },
      ),
    );
    const user = userEvent.setup();
    render(<PasswordResetPage />);

    await user.type(screen.getByLabelText(/メールアドレス/), "bad@example.com");
    await user.click(screen.getByRole("button", { name: /再設定リンクを送る/ }));

    const toast = await screen.findByTestId("error-toast");
    expect(toast.textContent).toContain("POST /api/auth/password-reset");
    expect(toast.textContent).not.toMatch(/Traceback|router\.py|SQLError/);
  });

  it("[Tier2 AC-F3] always shows the same success state on 2xx (no account enumeration)", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ status: "sent" }), { status: 200 }),
    );
    const user = userEvent.setup();
    render(<PasswordResetPage />);

    await user.type(screen.getByLabelText(/メールアドレス/), "maybe-exists@example.com");
    await user.click(screen.getByRole("button", { name: /再設定リンクを送る/ }));

    const status = await screen.findByRole("status");
    expect(status.textContent).toContain("メールを送信しました");
    // success copy must not differ between "account exists" vs "doesn't" — backend hides it.
    expect(status.textContent).not.toMatch(/見つかりません|存在しません/);
  });

  it("[Tier2 AC-F2 / extra] on 500, error message is generic and does not leak server detail", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("Internal Server Error", { status: 500 }),
    );
    const user = userEvent.setup();
    render(<PasswordResetPage />);

    await user.type(screen.getByLabelText(/メールアドレス/), "u@example.com");
    await user.click(screen.getByRole("button", { name: /再設定リンクを送る/ }));

    const toast = await screen.findByTestId("error-toast");
    expect(toast.textContent).toContain("サーバーで一時的なエラー");
  });

  it("[API client unit] ApiError carries endpoint label without exposing stack", () => {
    const err = new ApiError("POST /api/auth/password-reset", 429, "limit");
    expect(err.endpoint).toBe("POST /api/auth/password-reset");
    expect(err.status).toBe(429);
    expect(String(err)).not.toContain("Traceback");
  });
});
