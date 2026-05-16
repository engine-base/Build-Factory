"use client";

/**
 * T-V3-C-04 / S-004: MFA セットアップ wizard page.
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/auth/S-004-mfa-setup.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-004
 * @feature-id F-001
 * @task-ids T-V3-C-04,T-V3-AUTH-11,T-V3-AUTH-04,T-V3-AUTH-05
 * @entities E-001
 * @phase Phase 1B
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-04.md):
 *   structural.AC-S1 (data-screen-id="S-004")               — root element below.
 *   structural.AC-S2 (h1 = "2 段階認証 (MFA) を有効化")        — <h1> below.
 *   structural.AC-S3 (h2 Step 1 / Step 2)                    — two <h2> elements below.
 *   functional.AC-F1 (POST /api/auth/mfa/enroll typed call)  — handleEnroll().
 *   functional.AC-F2 (POST /api/auth/mfa/verify typed call)  — handleVerify().
 *   functional.AC-F3 (4xx/5xx -> non-technical endpoint toast) — surfaceError().
 *   functional.AC-F4 (mfa-enabled state -> verify before token) — enforced by handleVerify
 *                                                                  + backend (T-V3-B-02).
 */

import * as React from "react";
import { toast } from "sonner";
import {
  AlertTriangle,
  Check,
  Copy,
  Download,
  Key,
  Printer,
  QrCode,
  Save,
  ShieldCheck,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  AUTH_MFA_ENROLL_ENDPOINT,
  AUTH_MFA_VERIFY_ENDPOINT,
  AuthApiError,
  mfaEnroll,
  mfaVerify,
  type MfaEnrollResponse,
} from "@/api/auth";

// --------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------

const BASE32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

/**
 * Generates a 32-character base32 secret on the client. The backend treats it
 * as the canonical TOTP secret (see backend/schemas/auth.py
 * MfaEnrollRequest.totp_secret). We use crypto.getRandomValues so the secret
 * has real entropy; the test harness reseeds it deterministically.
 */
export function generateTotpSecret(length = 32): string {
  const bytes = new Uint8Array(length);
  if (typeof globalThis.crypto?.getRandomValues === "function") {
    globalThis.crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < length; i++) bytes[i] = Math.floor(Math.random() * 256);
  }
  let out = "";
  for (let i = 0; i < length; i++) {
    out += BASE32_ALPHABET[bytes[i] % 32];
  }
  return out;
}

const UUID_PATTERN =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

function resolveUserId(): string {
  if (typeof window === "undefined") return "";
  try {
    const stored = window.localStorage?.getItem("bf.user_id") ?? "";
    return stored;
  } catch {
    return "";
  }
}

function resolveAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage?.getItem("bf.access_token") ?? null;
  } catch {
    return null;
  }
}

function persistAccessTokens(access_token: string, refresh_token: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage?.setItem("bf.access_token", access_token);
    window.localStorage?.setItem("bf.refresh_token", refresh_token);
  } catch {
    // best-effort: storage may be blocked (private mode).
  }
}

// --------------------------------------------------------------------
// Page
// --------------------------------------------------------------------

type Stage = "scan" | "verify" | "backup";

export default function MfaSetupPage() {
  // Generate a stable secret per page-mount. The backend will hash it on enroll.
  // We seed via a lazy initializer so React only generates randomness once
  // per mount (avoiding setState-in-effect cascading renders).
  const [secret, setSecret] = React.useState<string>(() => generateTotpSecret());

  const [stage, setStage] = React.useState<Stage>("scan");
  const [enrollResp, setEnrollResp] = React.useState<MfaEnrollResponse | null>(
    null,
  );
  const [code, setCode] = React.useState<string>("");
  const [enrolling, setEnrolling] = React.useState(false);
  const [verifying, setVerifying] = React.useState(false);

  // Single helper so AC-F3 stays auditable (non-technical, references endpoint).
  const surfaceError = React.useCallback(
    (err: unknown, fallbackEndpoint: string) => {
      const message =
        err instanceof AuthApiError
          ? err.toUserMessage()
          : `通信に失敗しました (${fallbackEndpoint})`;
      toast.error(message);
    },
    [],
  );

  // AC-F1: POST /api/auth/mfa/enroll via the typed client.
  const handleEnroll = React.useCallback(async () => {
    if (enrolling) return;
    // If user clicks "regenerate", roll the secret first so the backend sees
    // a fresh value (also satisfies the regenerate_backup_codes affordance).
    const nextSecret = enrollResp ? generateTotpSecret() : secret;
    if (enrollResp) setSecret(nextSecret);
    setEnrolling(true);
    try {
      const resp = await mfaEnroll(
        { totp_secret: nextSecret },
        { authToken: resolveAuthToken() },
      );
      setEnrollResp(resp);
      setStage("verify");
      toast.success("認証アプリでスキャンできる QR を発行しました");
    } catch (err) {
      surfaceError(err, AUTH_MFA_ENROLL_ENDPOINT);
    } finally {
      setEnrolling(false);
    }
  }, [enrolling, enrollResp, secret, surfaceError]);

  // AC-F2 + AC-F4: POST /api/auth/mfa/verify via the typed client.
  const handleVerify = React.useCallback(async () => {
    if (verifying) return;
    const trimmed = code.trim();
    if (trimmed.length < 6) {
      toast.error("6 桁のコードを入力してください");
      return;
    }
    const user_id = resolveUserId();
    if (!UUID_PATTERN.test(user_id)) {
      toast.error("ユーザー ID が取得できませんでした");
      return;
    }
    setVerifying(true);
    try {
      const resp = await mfaVerify({ user_id, totp_code: trimmed });
      persistAccessTokens(resp.access_token, resp.refresh_token);
      setStage("backup");
      toast.success("MFA を有効化しました");
    } catch (err) {
      surfaceError(err, AUTH_MFA_VERIFY_ENDPOINT);
    } finally {
      setVerifying(false);
    }
  }, [verifying, code, surfaceError]);

  const copySecret = React.useCallback(async () => {
    try {
      await navigator.clipboard?.writeText(secret);
      toast.success("シークレットをコピーしました");
    } catch {
      toast.error("クリップボードへのコピーに失敗しました");
    }
  }, [secret]);

  const onCodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value.replace(/[^0-9]/g, "").slice(0, 6);
    setCode(v);
  };

  return (
    <div
      data-screen-id="S-004"
      data-feature-id="F-001"
      data-task-ids="T-V3-C-04,T-V3-AUTH-11,T-V3-AUTH-04,T-V3-AUTH-05"
      data-entities="E-001"
      data-phase="Phase 1B"
      className="min-h-screen bg-slate-50 px-6 py-12 flex justify-center"
    >
      <div className="w-full max-w-[560px]">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-lg bg-eb-100 mb-4">
            <ShieldCheck className="w-6 h-6 text-eb-500" aria-hidden />
          </div>
          {/* AC-S2: h1 must match screens.json[S-004].h1_text */}
          <h1 className="text-2xl font-bold">2 段階認証 (MFA) を有効化</h1>
          <p className="text-sm text-slate-600 mt-1">
            アカウントの安全性を高めるために TOTP 認証アプリを設定します
          </p>
        </div>

        {/* Stepper (visual progress) */}
        <ol
          aria-label="MFA セットアップ ステップ"
          className="bg-white border border-slate-200 rounded-lg p-4 mb-4 flex items-center gap-2 text-xs"
          data-testid="mfa-stepper"
        >
          <li
            className={
              "flex items-center gap-1.5 font-semibold " +
              (stage === "scan" ? "text-eb-500" : "text-slate-500")
            }
            aria-current={stage === "scan" ? "step" : undefined}
          >
            <span className="w-5 h-5 rounded-full bg-eb-500 text-white flex items-center justify-center font-mono">
              1
            </span>
            QR スキャン
          </li>
          <li aria-hidden className="flex-1 h-px bg-slate-200" />
          <li
            className={
              "flex items-center gap-1.5 " +
              (stage === "verify" ? "text-eb-500 font-semibold" : "text-slate-500")
            }
            aria-current={stage === "verify" ? "step" : undefined}
          >
            <span className="w-5 h-5 rounded-full bg-slate-200 text-slate-600 flex items-center justify-center font-mono">
              2
            </span>
            コード確認
          </li>
          <li aria-hidden className="flex-1 h-px bg-slate-200" />
          <li
            className={
              "flex items-center gap-1.5 " +
              (stage === "backup" ? "text-eb-500 font-semibold" : "text-slate-500")
            }
            aria-current={stage === "backup" ? "step" : undefined}
          >
            <span className="w-5 h-5 rounded-full bg-slate-200 text-slate-600 flex items-center justify-center font-mono">
              3
            </span>
            バックアップ
          </li>
        </ol>

        {/* ─── Step 1: QR scan (AC-S3 first heading) ─── */}
        <section className="bg-white border border-slate-200 rounded-lg p-6 mb-4">
          <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
            <QrCode className="w-5 h-5 text-eb-500" aria-hidden />
            Step 1. 認証アプリで QR をスキャン
          </h2>

          <div className="grid grid-cols-[180px_1fr] gap-6">
            {/* QR display: backend returns an `otpauth://` URL; we render it as
                a foreground-image placeholder until we wire in a QR encoder. */}
            <div
              className="bg-white border border-slate-200 rounded-md p-3 aspect-square flex items-center justify-center"
              data-testid="mfa-qr"
              aria-label="MFA QR code"
            >
              {enrollResp?.qr_code_url ? (
                // The backend returns an `otpauth://` URI which is not a
                // valid src for next/image (no loader). Falls back to a
                // plain <img> tag intentionally — see TODO(T-V3-AUTH-04)
                // for a real QR-encoder integration.
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={enrollResp.qr_code_url}
                  alt="MFA QR code"
                  className="w-full h-full object-contain"
                  data-testid="mfa-qr-image"
                />
              ) : (
                <div className="text-center text-xs text-slate-400 leading-relaxed px-2">
                  「QR を生成」を押すと
                  <br />
                  ここにコードが表示されます
                </div>
              )}
            </div>

            <div className="space-y-3">
              <p className="text-sm text-slate-600 leading-relaxed">
                <strong>Google Authenticator</strong> /{" "}
                <strong>1Password</strong> / <strong>Authy</strong> 等の TOTP
                認証アプリで上記の QR をスキャンしてください。
              </p>

              <div className="border border-slate-200 rounded-md p-3 bg-slate-50">
                <div className="text-xs text-slate-500 mb-1">
                  手動入力用シークレット
                </div>
                <div className="flex items-center gap-2">
                  <code
                    className="font-mono text-sm text-slate-900 tracking-widest flex-1 break-all"
                    data-testid="mfa-secret"
                  >
                    {secret || "—"}
                  </code>
                  <button
                    type="button"
                    onClick={copySecret}
                    className="text-slate-500 hover:text-eb-500"
                    aria-label="シークレットをコピー"
                  >
                    <Copy className="w-3.5 h-3.5" aria-hidden />
                  </button>
                </div>
              </div>

              <p className="text-xs text-slate-500">
                QR をスキャンできない場合は、上記のシークレットを認証アプリに手動で追加してください。
              </p>

              <Button
                type="button"
                onClick={handleEnroll}
                disabled={enrolling || !secret}
                data-testid="mfa-enroll-button"
                className="w-full"
              >
                <QrCode className="w-4 h-4" aria-hidden />
                {enrollResp ? "QR を再発行" : "QR を生成"}
              </Button>
            </div>
          </div>
        </section>

        {/* ─── Step 2: Verify code (AC-S3 second heading) ─── */}
        <section className="bg-white border border-slate-200 rounded-lg p-6 mb-4">
          <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
            <Key className="w-5 h-5 text-eb-500" aria-hidden />
            Step 2. 6 桁のコードで確認
          </h2>
          <div className="space-y-3">
            <p className="text-sm text-slate-600">
              認証アプリに表示された 6 桁のコードを入力してください
            </p>
            <div className="flex items-center gap-2">
              <Input
                type="text"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                placeholder="123456"
                value={code}
                onChange={onCodeChange}
                aria-label="TOTP 6 桁コード"
                data-testid="mfa-code-input"
                className="text-xl h-12 px-4 w-44 font-mono tracking-[0.4em] text-center"
              />
              <Button
                type="button"
                onClick={handleVerify}
                disabled={verifying || code.length < 6}
                data-testid="mfa-verify-button"
                className="h-12 px-6"
              >
                <span>確認</span>
                <Check className="w-4 h-4" aria-hidden />
              </Button>
            </div>
            <p className="text-xs text-slate-500">
              5 回以上失敗すると 15 分間ロックされます
            </p>
          </div>
        </section>

        {/* ─── Step 3: Backup codes ─── */}
        <details
          className="bg-white border border-slate-200 rounded-lg p-6 mb-4"
          open={stage === "backup"}
          data-testid="mfa-backup-codes"
        >
          <summary className="text-lg font-bold cursor-pointer flex items-center gap-2">
            <Save className="w-5 h-5 text-eb-500" aria-hidden />
            Step 3. リカバリーコード
            <span className="text-xs font-normal text-slate-500 ml-auto">
              クリックで表示
            </span>
          </summary>
          <div className="mt-4 space-y-3">
            <div className="bg-amber-50 border border-amber-200 rounded-md p-3 flex items-start gap-2">
              <AlertTriangle
                className="w-4 h-4 text-amber-600 mt-0.5 shrink-0"
                aria-hidden
              />
              <div className="text-xs text-amber-900">
                認証アプリにアクセスできなくなった場合の
                <strong>緊急用コード</strong>です。安全な場所に保存してください。各コードは一度だけ使用可能。
              </div>
            </div>

            {enrollResp?.backup_codes?.length ? (
              <ul
                className="grid grid-cols-2 gap-2 font-mono text-sm"
                data-testid="mfa-backup-codes-list"
              >
                {enrollResp.backup_codes.map((code) => (
                  <li
                    key={code}
                    className="border border-slate-200 rounded-md px-3 py-2 bg-slate-50 tabular-nums"
                  >
                    {code}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-slate-500">
                QR を生成すると、ここに 10 件のリカバリーコードが表示されます。
              </p>
            )}

            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                className="flex-1 h-9"
                disabled={!enrollResp?.backup_codes?.length}
              >
                <Download className="w-4 h-4" aria-hidden />
                ダウンロード (TXT)
              </Button>
              <Button
                type="button"
                variant="outline"
                className="flex-1 h-9"
                disabled={!enrollResp?.backup_codes?.length}
              >
                <Copy className="w-4 h-4" aria-hidden />
                コピー
              </Button>
              <Button
                type="button"
                variant="outline"
                className="flex-1 h-9"
                disabled={!enrollResp?.backup_codes?.length}
              >
                <Printer className="w-4 h-4" aria-hidden />
                印刷
              </Button>
            </div>
          </div>
        </details>

        <Button
          type="button"
          className="w-full h-10"
          disabled={stage !== "backup"}
          data-testid="mfa-finish-button"
        >
          <ShieldCheck className="w-4 h-4" aria-hidden />
          MFA を有効化して完了
        </Button>

        <div className="text-center text-[11px] text-slate-400 mt-8 font-mono">
          © ENGINE BASE
        </div>
      </div>
    </div>
  );
}
