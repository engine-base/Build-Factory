// @ts-nocheck
/**
 * T-V3-C-07 / S-007 — Account settings screen specs.
 *
 * Runner: `vitest run frontend/tests/screens/` (target AC-R1, >= 5 cases).
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the new screen
 *       test harness; they are wired by the Wave 2 frontend test setup ticket.
 *
 * Covers (mapped to T-V3-C-07 acceptance_criteria):
 *   structural.AC-S1  -> "renders root with data-screen-id=S-007"
 *   structural.AC-S2  -> "h1 reads 'アカウント設定'"
 *   structural.AC-S3  -> "renders the 4 h2 section headings from screens.json"
 *   functional.AC-F1  -> "GET /api/accounts/{id} via typed client on mount"
 *   functional.AC-F2  -> "PUT /api/accounts/{id} typed client on Save"
 *   functional.AC-F3  -> "POST /api/accounts/{id}/transfer-owner typed client"
 *   functional.AC-F4  -> "DELETE /api/accounts/{id} typed client (Danger Zone)"
 *   functional.AC-F5  -> "4xx/5xx surfaces non-technical toast referencing endpoint"
 *   functional.AC-F7  -> "409 from transfer-owner shows endpoint-referenced toast"
 *   functional.AC-F9  -> "navigation guard shows S-052 dialog when dirty"
 *   functional.AC-F10 -> "Danger Zone (S-055) requires typed-name confirmation"
 */

import * as React from "react";
import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
} from "vitest";
import {
  render,
  screen,
  waitFor,
  cleanup,
  fireEvent,
} from "@testing-library/react";

import AccountSettingsPage from "@/app/(app)/settings/account/page";

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const ACCOUNT_FIXTURE = {
  id: 1,
  name: "ENGINE BASE",
  account_type: "agency",
  plan: "Pro",
  owner_user_id: "masato",
};

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  // Default: GET succeeds with the fixture. Specific tests override.
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    if (
      (!init || init.method === "GET" || init.method === undefined) &&
      typeof url === "string" &&
      url.endsWith("/api/accounts/1")
    ) {
      return Promise.resolve(jsonResponse(200, ACCOUNT_FIXTURE));
    }
    return Promise.resolve(jsonResponse(500, { detail: { code: "X" } }));
  });
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

describe("S-007 Account settings page (T-V3-C-07)", () => {
  it("AC-S1: renders root with data-screen-id='S-007'", async () => {
    const { container } = render(<AccountSettingsPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const root = container.querySelector('[data-screen-id="S-007"]');
    expect(root).not.toBeNull();
    expect(root?.getAttribute("data-feature-id")).toBe("F-004");
  });

  it("AC-S2: h1 reads 'アカウント設定'", async () => {
    render(<AccountSettingsPage />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent).toBe("アカウント設定");
  });

  it("AC-S3: renders the 4 section h2 headings from screens.json", async () => {
    render(<AccountSettingsPage />);
    await waitFor(() => expect(screen.queryByText("基本情報")).not.toBeNull());
    expect(screen.getByText("基本情報").tagName).toBe("H2");
    expect(screen.getByText("プラン / 課金").tagName).toBe("H2");
    expect(screen.getByText("所有者 (Account Owner)").tagName).toBe("H2");
    // Danger Zone heading text is wrapped with the alert icon.
    expect(
      screen.getByRole("heading", { level: 2, name: /Danger Zone/ }),
    ).not.toBeNull();
  });

  it("AC-F1: GET /api/accounts/{id} on mount via typed client", async () => {
    render(<AccountSettingsPage />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [calledUrl, init] = fetchMock.mock.calls[0];
    expect(String(calledUrl)).toContain("/api/accounts/1");
    expect((init ?? {}).method).toBe("GET");
  });

  it("AC-F2: PATCH /api/accounts/{id} when Save is clicked with diff", async () => {
    fetchMock.mockReset();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, ACCOUNT_FIXTURE))
      .mockResolvedValueOnce(
        jsonResponse(200, { ...ACCOUNT_FIXTURE, name: "ENGINE BASE 2" }),
      );
    render(<AccountSettingsPage />);
    await waitFor(() =>
      expect(screen.getByTestId("save-button")).not.toBeNull(),
    );
    const input = screen.getByLabelText("アカウント名") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "ENGINE BASE 2" } });
    fireEvent.click(screen.getByTestId("save-button"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [calledUrl, init] = fetchMock.mock.calls[1];
    expect(String(calledUrl)).toContain("/api/accounts/1");
    expect((init ?? {}).method).toBe("PATCH");
    const body = JSON.parse((init?.body as string) ?? "{}");
    expect(body).toEqual({ name: "ENGINE BASE 2" });
  });

  it("AC-F3: POST /api/accounts/{id}/transfer-owner with typed client", async () => {
    fetchMock.mockReset();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, ACCOUNT_FIXTURE))
      .mockResolvedValueOnce(
        jsonResponse(201, {
          old_owner_id: "masato",
          new_owner_id: "alice",
          transferred_at: "2026-05-16T00:00:00Z",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse(200, { ...ACCOUNT_FIXTURE, owner_user_id: "alice" }),
      );
    render(<AccountSettingsPage />);
    await waitFor(() =>
      expect(screen.getByTestId("transfer-owner-toggle")).not.toBeNull(),
    );
    fireEvent.click(screen.getByTestId("transfer-owner-toggle"));
    fireEvent.change(screen.getByTestId("transfer-owner-input"), {
      target: { value: "alice" },
    });
    fireEvent.click(screen.getByTestId("transfer-owner-submit"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [calledUrl, init] = fetchMock.mock.calls[1];
    expect(String(calledUrl)).toContain(
      "/api/accounts/1/transfer-owner",
    );
    expect((init ?? {}).method).toBe("POST");
    const body = JSON.parse((init?.body as string) ?? "{}");
    expect(body).toEqual({ new_owner_user_id: "alice" });
  });

  it("AC-F5 + AC-F7: 409 from transfer-owner surfaces a non-technical toast referencing the endpoint w/o stack traces", async () => {
    fetchMock.mockReset();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, ACCOUNT_FIXTURE))
      .mockResolvedValueOnce(
        jsonResponse(409, {
          detail: {
            code: "accounts.target_not_member",
            message: "Traceback (most recent call last) ...",
          },
        }),
      );
    render(<AccountSettingsPage />);
    await waitFor(() =>
      expect(screen.getByTestId("transfer-owner-toggle")).not.toBeNull(),
    );
    fireEvent.click(screen.getByTestId("transfer-owner-toggle"));
    fireEvent.change(screen.getByTestId("transfer-owner-input"), {
      target: { value: "bob" },
    });
    fireEvent.click(screen.getByTestId("transfer-owner-submit"));
    const alert = await screen.findByTestId("error-toast");
    expect(alert.textContent ?? "").toContain(
      "/api/accounts/1/transfer-owner",
    );
    expect(alert.textContent ?? "").not.toMatch(/traceback/i);
    expect(alert.textContent ?? "").not.toMatch(/Exception/);
  });

  it("AC-F9: dirty form opens the S-052 unsaved-changes dialog when navigating away", async () => {
    render(<AccountSettingsPage />);
    await waitFor(() =>
      expect(screen.getByTestId("save-button")).not.toBeNull(),
    );
    const input = screen.getByLabelText("アカウント名") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "ENGINE BASE X" } });
    fireEvent.click(screen.getByTestId("breadcrumb-back"));
    const dialog = await screen.findByTestId("unsaved-changes-dialog");
    expect(dialog.getAttribute("data-dialog")).toBe("S-052");
    expect(dialog.getAttribute("role")).toBe("dialog");
  });

  it("AC-F4 + AC-F10: Danger Zone DELETE only fires after typed-name confirm (S-055 pattern)", async () => {
    fetchMock.mockReset();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, ACCOUNT_FIXTURE))
      .mockResolvedValueOnce(jsonResponse(204, null));
    // Prevent jsdom navigation error from window.location.replace.
    const replaceMock = vi.fn();
    Object.defineProperty(window, "location", {
      value: { ...window.location, replace: replaceMock, href: "" },
      writable: true,
    });
    render(<AccountSettingsPage />);
    await waitFor(() =>
      expect(screen.getByTestId("open-danger-zone")).not.toBeNull(),
    );
    fireEvent.click(screen.getByTestId("open-danger-zone"));
    const dialog = await screen.findByTestId("danger-zone-dialog");
    expect(dialog.getAttribute("data-dialog")).toBe("S-055");
    const confirmBtn = screen.getByTestId(
      "danger-zone-confirm",
    ) as HTMLButtonElement;
    // Disabled until name matches AND acknowledgement is ticked.
    expect(confirmBtn.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("danger-zone-name-input"), {
      target: { value: "WRONG NAME" },
    });
    fireEvent.click(screen.getByTestId("danger-zone-ack"));
    expect(confirmBtn.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("danger-zone-name-input"), {
      target: { value: "ENGINE BASE" },
    });
    expect(confirmBtn.disabled).toBe(false);
    fireEvent.click(confirmBtn);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [calledUrl, init] = fetchMock.mock.calls[1];
    expect(String(calledUrl)).toContain("/api/accounts/1");
    expect((init ?? {}).method).toBe("DELETE");
  });
});
