"use client";

/**
 * S-009 / T-023-01 + T-023-02: プロフィール設定 + API キー管理
 *
 * 対応モック: docs/mocks/2026-05-09_v1/account/S-009-profile-settings.html
 * 対応 backend:
 *   - GET/PATCH /api/bf-profile       (T-023-01 本 PR で新規追加)
 *   - GET/DELETE /api/oauth/{provider}/status (T-023-04 PR #25)
 *   - GET /api/oauth/{provider}/authorize     (T-023-04)
 *   - GET/POST /api/user/clone-optin          (T-023-05 PR #25)
 *   - POST /api/user/deletion                 (T-023-05 PR #25)
 *
 * Tab 構成 (mock 準拠):
 *   - プロフィール (T-023-01)
 *   - 通知 / 外観 / セキュリティ (Phase 1 stub)
 *   - API キー (T-023-02) = OAuth 連携 + クローン opt-in + GDPR 削除権
 */

import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  User, Bell, Palette, ShieldCheck, KeyRound, Save, Check, Loader2,
  Sun, Moon, Monitor, Link2, Unlink, AlertTriangle, Trash2,
  MessageSquare, Bot, FileCode2,
} from "lucide-react";
import {
  fetchProfile, patchProfile, type BfProfile,
  fetchOAuthProviders, fetchOAuthStatus, startOAuthAuthorize, disconnectOAuth,
  fetchCloneOptin, setCloneOptin, requestUserDeletion,
  type OAuthProvider,
} from "@/lib/workspace-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

// TODO(auth): セッション統合後に動的取得
const USER_ID = "masato";
const REDIRECT_URI = (typeof window !== "undefined" ? window.location.origin : "http://localhost:3000") + "/settings/profile/oauth-callback";

type TabKey = "profile" | "notifications" | "appearance" | "security" | "api_keys";

const TABS: { key: TabKey; label: string; icon: typeof User }[] = [
  { key: "profile",       label: "プロフィール", icon: User },
  { key: "notifications", label: "通知",         icon: Bell },
  { key: "appearance",    label: "外観",         icon: Palette },
  { key: "security",      label: "セキュリティ", icon: ShieldCheck },
  { key: "api_keys",      label: "API キー",     icon: KeyRound },
];

export default function ProfileSettingsPage() {
  const [activeTab, setActiveTab] = useState<TabKey>("profile");

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      <header className="h-14 bg-white border-b border-slate-200 flex items-center px-6 gap-4 sticky top-0 z-10">
        <h1 className="text-base font-bold text-slate-900">プロフィール設定</h1>
        <span className="text-[11px] text-slate-400 font-mono ml-auto">S-009 · T-023-01 / T-023-02</span>
      </header>

      <div className="p-6 max-w-[1200px] mx-auto">
        <div className="grid grid-cols-[200px_1fr] gap-6">
          <nav className="text-sm space-y-1">
            {TABS.map((t) => {
              const Icon = t.icon;
              const active = activeTab === t.key;
              return (
                <button
                  key={t.key}
                  onClick={() => setActiveTab(t.key)}
                  className={`w-full text-left px-3 py-2 rounded inline-flex items-center gap-2 ${
                    active
                      ? "bg-eb-50 text-eb-700 font-bold"
                      : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {t.label}
                </button>
              );
            })}
          </nav>

          <section className="space-y-6">
            {activeTab === "profile" && <ProfileTab />}
            {activeTab === "appearance" && <AppearanceTab />}
            {activeTab === "api_keys" && <ApiKeysTab />}
            {activeTab === "notifications" && (
              <StubTab title="通知" hint="Phase 1.5 で実装予定 (T-014 Slack 連携と統合)" />
            )}
            {activeTab === "security" && (
              <StubTab title="セキュリティ" hint="2FA / セッション管理は Phase 1.5 (T-S0-08 後続) で実装" />
            )}
          </section>
        </div>
      </div>

      <footer className="h-9 bg-white border-t border-slate-200 flex items-center justify-between px-6 text-[11px] text-slate-500 font-mono">
        <span>S-009 profile_settings · F-023 · T-023-01 / T-023-02</span>
        <span>user: {USER_ID}</span>
      </footer>
    </div>
  );
}

// ──────────────────────────────────────────
// T-023-01: Profile tab
// ──────────────────────────────────────────

function ProfileTab() {
  const qc = useQueryClient();
  const profileQ = useQuery({
    queryKey: ["bf-profile", USER_ID],
    queryFn: () => fetchProfile(USER_ID),
  });
  const [draft, setDraft] = useState<BfProfile | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    if (profileQ.data && !draft) setDraft(profileQ.data);
  }, [profileQ.data, draft]);

  const saveMut = useMutation({
    mutationFn: async () => {
      if (!draft) return null;
      const res = await patchProfile(USER_ID, {
        display_name: draft.display_name ?? null,
        role_text: draft.role_text ?? null,
        bio: draft.bio ?? null,
      });
      if (!res) throw new Error("save failed");
      return res;
    },
    onSuccess: (res) => {
      if (res) {
        qc.setQueryData(["bf-profile", USER_ID], res);
        setDraft(res);
      }
      setSavedAt(Date.now());
      setTimeout(() => setSavedAt(null), 2200);
    },
  });

  if (profileQ.isLoading || !draft) {
    return (
      <div className="bg-white border border-slate-200 rounded-lg p-5 text-center text-slate-400">
        <Loader2 className="w-4 h-4 inline-block animate-spin mr-2" /> 読み込み中…
      </div>
    );
  }

  const initial = (draft.display_name?.[0] ?? "?").toUpperCase();

  return (
    <>
      <div className="bg-white border border-slate-200 rounded-lg p-5">
        <h2 className="text-sm font-bold mb-4">プロフィール</h2>
        <div className="flex items-center gap-4 mb-5">
          <div className="w-16 h-16 rounded-full bg-eb-500 text-white flex items-center justify-center text-xl font-bold">
            {initial}
          </div>
          <button
            className="px-3 py-1.5 text-xs border border-slate-300 rounded hover:bg-slate-50"
            disabled
            title="Phase 1.5 で実装"
          >
            画像をアップロード
          </button>
        </div>
        <div className="space-y-3 max-w-xl">
          <Field label="表示名">
            <Input
              value={draft.display_name ?? ""}
              onChange={(e) => setDraft({ ...draft, display_name: e.target.value })}
              maxLength={120}
            />
          </Field>
          <Field label="役割">
            <Input
              value={draft.role_text ?? ""}
              onChange={(e) => setDraft({ ...draft, role_text: e.target.value })}
              maxLength={120}
              placeholder="例: 代表 / フルスタック"
            />
          </Field>
          <Field label="略歴">
            <Textarea
              className="min-h-[80px]"
              value={draft.bio ?? ""}
              onChange={(e) => setDraft({ ...draft, bio: e.target.value })}
              maxLength={2000}
            />
          </Field>
        </div>
      </div>

      <div className="flex justify-end gap-2">
        {savedAt && (
          <span className="inline-flex items-center gap-1 text-xs text-emerald-700">
            <Check className="w-3.5 h-3.5" /> 保存しました
          </span>
        )}
        <Button
          variant="outline"
          size="default"
          onClick={() => profileQ.data && setDraft(profileQ.data)}
        >
          リセット
        </Button>
        <Button
          size="default"
          className="bg-eb-500 hover:bg-eb-600 text-white font-bold"
          onClick={() => saveMut.mutate()}
          disabled={saveMut.isPending}
        >
          {saveMut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          保存
        </Button>
      </div>
    </>
  );
}

// ──────────────────────────────────────────
// T-023-01: Appearance tab (theme)
// ──────────────────────────────────────────

function AppearanceTab() {
  const qc = useQueryClient();
  const profileQ = useQuery({
    queryKey: ["bf-profile", USER_ID],
    queryFn: () => fetchProfile(USER_ID),
  });

  const themeMut = useMutation({
    mutationFn: async (theme: "light" | "dark" | "system") => {
      const res = await patchProfile(USER_ID, { theme });
      if (!res) throw new Error("theme update failed");
      return res;
    },
    onSuccess: (res) => {
      if (res) qc.setQueryData(["bf-profile", USER_ID], res);
    },
  });

  const current = profileQ.data?.theme ?? "light";

  const options = useMemo(() => [
    { key: "light",  label: "Light",  icon: Sun },
    { key: "dark",   label: "Dark",   icon: Moon },
    { key: "system", label: "System", icon: Monitor },
  ] as const, []);

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-5">
      <h2 className="text-sm font-bold mb-3">外観</h2>
      <p className="text-xs text-slate-500 mb-3">テーマ設定 (Phase 1 はサーバ保存のみ、実反映は Phase 1.5)。</p>
      <div className="flex gap-2 flex-wrap">
        {options.map((o) => {
          const Icon = o.icon;
          const active = current === o.key;
          return (
            <button
              key={o.key}
              onClick={() => themeMut.mutate(o.key)}
              disabled={themeMut.isPending}
              className={`px-3 py-1.5 text-xs rounded inline-flex items-center gap-1 font-bold ${
                active
                  ? "border-2 border-eb-500 bg-eb-50 text-eb-700"
                  : "border border-slate-300 hover:bg-slate-50"
              } disabled:opacity-50`}
            >
              <Icon className="w-3.5 h-3.5" />
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────
// T-023-02: API keys (OAuth + clone opt-in + GDPR deletion)
// ──────────────────────────────────────────

function ApiKeysTab() {
  return (
    <>
      <OAuthConnectionsCard />
      <CloneOptinCard />
      <DeleteAccountCard />
    </>
  );
}

const PROVIDER_META: Record<OAuthProvider, { label: string; icon: typeof FileCode2; help: string }> = {
  slack:     { label: "Slack",     icon: MessageSquare, help: "通知 / ダイジェスト配信用 (T-014 連携)" },
  github:    { label: "GitHub",    icon: FileCode2,     help: "リポジトリ作成 / PR 自動化 (T-013 連携)" },
  anthropic: { label: "Anthropic", icon: Bot,           help: "Claude Pro/Max トークン (T-010b 連携)" },
};

function OAuthConnectionsCard() {
  const qc = useQueryClient();
  const providersQ = useQuery({
    queryKey: ["oauth-providers"],
    queryFn: fetchOAuthProviders,
  });

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-5">
      <div className="flex items-center gap-2 mb-3">
        <KeyRound className="w-4 h-4 text-eb-500" />
        <h2 className="text-sm font-bold flex-1">外部サービス連携 (OAuth)</h2>
      </div>
      <p className="text-xs text-slate-500 mb-4">
        backend `encrypted_store` 経由で暗号化保管 (Phase 1: Fernet local / Phase 2: pgsodium)。
      </p>
      <div className="divide-y divide-slate-100">
        {(providersQ.data ?? Object.keys(PROVIDER_META) as OAuthProvider[]).map((p) => (
          <OAuthRow
            key={p}
            provider={p as OAuthProvider}
            onChanged={() => qc.invalidateQueries({ queryKey: ["oauth-status", p, USER_ID] })}
          />
        ))}
      </div>
    </div>
  );
}

function OAuthRow({ provider, onChanged }: { provider: OAuthProvider; onChanged: () => void }) {
  const statusQ = useQuery({
    queryKey: ["oauth-status", provider, USER_ID],
    queryFn: () => fetchOAuthStatus(provider, USER_ID),
  });

  const meta = PROVIDER_META[provider];
  const Icon = meta.icon;
  const connected = statusQ.data?.connected === true;

  const onConnect = async () => {
    const r = await startOAuthAuthorize(provider, REDIRECT_URI);
    if (!r) {
      alert(`${meta.label} は backend で client_id 未設定です (.env を確認)`);
      return;
    }
    // state を sessionStorage に保存して callback 側で検証 (CSRF guard)
    sessionStorage.setItem(`oauth_state_${provider}`, r.state);
    window.location.href = r.authorize_url;
  };

  const onDisconnect = async () => {
    if (!confirm(`${meta.label} の連携を解除しますか?`)) return;
    await disconnectOAuth(provider, USER_ID);
    onChanged();
  };

  return (
    <div className="py-3 flex items-center gap-3">
      <Icon className="w-5 h-5 text-slate-600" />
      <div className="flex-1">
        <div className="text-sm font-bold">{meta.label}</div>
        <div className="text-[11px] text-slate-500">{meta.help}</div>
      </div>
      {statusQ.isLoading ? (
        <Loader2 className="w-4 h-4 animate-spin text-slate-400" />
      ) : connected ? (
        <Button variant="outline" size="sm" onClick={onDisconnect}>
          <Unlink className="w-3.5 h-3.5" /> 解除
        </Button>
      ) : (
        <Button
          size="sm"
          className="bg-eb-500 hover:bg-eb-600 text-white font-bold"
          onClick={onConnect}
        >
          <Link2 className="w-3.5 h-3.5" /> 接続
        </Button>
      )}
    </div>
  );
}

function CloneOptinCard() {
  const qc = useQueryClient();
  const optinQ = useQuery({
    queryKey: ["clone-optin", USER_ID],
    queryFn: () => fetchCloneOptin(USER_ID),
  });
  const optinMut = useMutation({
    mutationFn: (v: boolean) => setCloneOptin(USER_ID, v),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["clone-optin", USER_ID] }),
  });

  const optedIn = optinQ.data === true;

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-5">
      <div className="flex items-center gap-2 mb-2">
        <Bot className="w-4 h-4 text-eb-500" />
        <h2 className="text-sm font-bold flex-1">AI 社員クローン</h2>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        自分の persona / 過去会話を AI 社員のクローン作成 (Phase 2) に使うことを許可します。
        既定は <strong>OFF</strong>。いつでも変更可能 (T-023-05)。
      </p>
      <label className="inline-flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={optedIn}
          onChange={(e) => optinMut.mutate(e.target.checked)}
          disabled={optinMut.isPending || optinQ.isLoading}
          className="w-4 h-4 accent-eb-500"
        />
        <span className="text-sm">クローン作成を許可する</span>
        {optinMut.isPending && <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-400" />}
      </label>
    </div>
  );
}

function DeleteAccountCard() {
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState("");
  const [scheduledAt, setScheduledAt] = useState<string | null>(null);

  const deleteMut = useMutation({
    mutationFn: () => requestUserDeletion(USER_ID, reason || undefined),
    onSuccess: (r) => {
      if (r.ok) {
        setScheduledAt(r.execute_after ?? null);
        setConfirming(false);
      } else {
        alert("削除リクエストの作成に失敗しました。");
      }
    },
  });

  return (
    <div className="bg-rose-50 border border-rose-200 rounded-lg p-5">
      <div className="flex items-center gap-2 mb-2">
        <AlertTriangle className="w-4 h-4 text-rose-600" />
        <h2 className="text-sm font-bold text-rose-700 flex-1">アカウント削除 (GDPR)</h2>
      </div>
      <p className="text-xs text-rose-700/80 mb-3">
        削除リクエストは <strong>30 日間の grace 期間</strong> を経て確定実行されます (T-023-05)。
        期間内であれば backend <code>DELETE /api/user/deletion/&#123;id&#125;</code> でキャンセル可能です。
      </p>

      {scheduledAt ? (
        <div className="flex items-start gap-2 px-3 py-2 bg-white border border-rose-200 rounded text-xs text-rose-700">
          <Check className="w-3.5 h-3.5 mt-0.5" />
          <span>
            削除リクエスト受付済み。確定実行予定: <strong>{scheduledAt}</strong>
          </span>
        </div>
      ) : confirming ? (
        <div className="space-y-2">
          <Textarea
            className="border-rose-300"
            placeholder="削除理由 (任意)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              className="bg-rose-600 hover:bg-rose-700 text-white font-bold"
              onClick={() => deleteMut.mutate()}
              disabled={deleteMut.isPending}
            >
              {deleteMut.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
              30 日後に削除する
            </Button>
            <Button variant="ghost" size="sm" className="text-rose-700" onClick={() => setConfirming(false)}>
              キャンセル
            </Button>
          </div>
        </div>
      ) : (
        <Button
          variant="outline"
          size="sm"
          className="border-rose-400 text-rose-700 hover:bg-rose-100"
          onClick={() => setConfirming(true)}
        >
          <Trash2 className="w-3.5 h-3.5" /> アカウント削除をリクエスト
        </Button>
      )}
    </div>
  );
}

// ──────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs font-bold mb-1 block text-slate-700">{label}</label>
      {children}
    </div>
  );
}

function StubTab({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg p-5">
      <h2 className="text-sm font-bold mb-2">{title}</h2>
      <p className="text-xs text-slate-500">{hint}</p>
    </div>
  );
}
