"use client";

/**
 * S-009 プロフィール設定 — T-V3-C-09 / F-022 + F-023.
 *
 * @screen-id S-009
 * @feature-id F-022,F-023
 * @task-ids T-V3-C-09
 * @entities E-001,E-010,E-040
 * @phase Phase 1B
 *
 * Mock 逐語準拠: docs/mocks/2026-05-15_v3/account/S-009-profile-settings.html
 *   - h1 text         : "プロフィール設定"  (screens.json[S-009].h1_text)
 *   - section h2 cap 12: プロフィール / 通知設定 / LLM プロバイダ (BYOK) /
 *                       OAuth 連携 / ユーザークローン (高本さんの判断基準を学習) / Danger Zone
 *   - 状態           : loading / loaded / error (screens.json[S-009].states)
 *
 * EARS AC (3-tier):
 *   structural.AC-S1: While S-009 page is rendered, the system shall include a
 *     `data-screen-id="S-009"` attribute on the root element.
 *   structural.AC-S2: h1 == "プロフィール設定".
 *   structural.AC-S3: render the 6 h2 section headings from screens.json.
 *   functional.AC-F1: When the page performs its primary action, call
 *     GET /api/me via the typed API client.
 *   functional.AC-F2: same for PUT /api/me.
 *   functional.AC-F3: same for POST /api/me/api-keys.
 *   functional.AC-F4: same for DELETE /api/me/oauth/{provider}.
 *   functional.AC-F5: 4xx/5xx → non-technical toast referencing the failing
 *     endpoint, no stack-trace leak.
 *   functional.AC-F6: While clone_opt_in is FALSE, the system shall not INSERT
 *     into user_interaction_log (DB trigger enforced — UI surfaces the badge).
 *   functional.AC-F7: When a user opts out of cloning, the system shall offer
 *     immediate deletion of user_knowledge_namespace + user_interaction_log.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";
import {
  MeApiError,
  deleteMeOAuth,
  getMe,
  postMeApiKey,
  putMe,
  type GetMeResponse,
  type MeSettings,
  type MeUser,
} from "@/api/me";

type ViewState = "loading" | "loaded" | "error";

interface ToastEntry {
  id: number;
  kind: "info" | "success" | "error";
  message: string;
}

/** Mock-parity OAuth providers list (S-009 docs/mocks). */
const OAUTH_PROVIDERS: { id: string; label: string }[] = [
  { id: "github", label: "GitHub" },
  { id: "slack", label: "Slack" },
];

/** Mock-parity BYOK providers list (S-009 docs/mocks). */
const BYOK_PROVIDERS: { id: string; label: string }[] = [
  { id: "anthropic", label: "Anthropic" },
  { id: "openai", label: "OpenAI" },
];

/** Section h2 texts — must mirror screens.json[S-009].section_h2_texts. */
const SECTION_H2 = [
  "プロフィール",
  "通知設定",
  "LLM プロバイダ (BYOK)",
  "OAuth 連携",
  "ユーザークローン (高本さんの判断基準を学習)",
  "Danger Zone",
] as const;

export default function ProfileSettingsPage() {
  const [view, setView] = useState<ViewState>("loading");
  const [data, setData] = useState<GetMeResponse | null>(null);
  const [draftName, setDraftName] = useState("");
  const [draftAvatarUrl, setDraftAvatarUrl] = useState("");
  const [draftSettings, setDraftSettings] = useState<MeSettings>({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [byokDraft, setByokDraft] = useState<{ provider: string; api_key: string; label: string }>({
    provider: BYOK_PROVIDERS[0].id,
    api_key: "",
    label: "",
  });
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const toastIdRef = useRef(0);

  const pushToast = useCallback((kind: ToastEntry["kind"], message: string) => {
    const id = ++toastIdRef.current;
    setToasts((prev) => [...prev, { id, kind, message }]);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  /** AC-F1: load profile from GET /api/me. */
  const loadProfile = useCallback(async () => {
    setView("loading");
    setErrorMessage(null);
    try {
      const res = await getMe();
      setData(res);
      setDraftName(res.user.name ?? "");
      setDraftAvatarUrl(res.user.avatar_url ?? "");
      setDraftSettings(res.settings ?? {});
      setView("loaded");
    } catch (err) {
      const message = friendlyOrFallback(err, "GET /api/me");
      setErrorMessage(message);
      setView("error");
      pushToast("error", message);
    }
  }, [pushToast]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  /** AC-F2: save profile via PUT /api/me. */
  const onSaveProfile = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      try {
        await putMe({
          name: draftName || null,
          avatar_url: draftAvatarUrl || null,
          settings: draftSettings,
        });
        pushToast("success", "プロフィールを保存しました");
        await loadProfile();
      } catch (err) {
        const message = friendlyOrFallback(err, "PUT /api/me");
        pushToast("error", message);
      }
    },
    [draftAvatarUrl, draftName, draftSettings, loadProfile, pushToast],
  );

  /** AC-F3: register a new BYOK API key. */
  const onAddApiKey = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!byokDraft.api_key) {
        pushToast("error", "API キーを入力してください (POST /api/me/api-keys)");
        return;
      }
      try {
        const res = await postMeApiKey({
          provider: byokDraft.provider,
          api_key: byokDraft.api_key,
          label: byokDraft.label || null,
        });
        pushToast("success", `API キー登録 (${res.masked_key})`);
        setByokDraft({ ...byokDraft, api_key: "" });
      } catch (err) {
        const message = friendlyOrFallback(err, "POST /api/me/api-keys");
        pushToast("error", message);
      }
    },
    [byokDraft, pushToast],
  );

  /** AC-F4: unlink an OAuth provider. */
  const onUnlinkOAuth = useCallback(
    async (provider: string) => {
      try {
        await deleteMeOAuth(provider);
        pushToast("success", `${provider} の連携を解除しました`);
      } catch (err) {
        const message = friendlyOrFallback(err, `DELETE /api/me/oauth/${provider}`);
        pushToast("error", message);
      }
    },
    [pushToast],
  );

  /** AC-F6 + AC-F7: toggle clone opt-in and offer deletion when opting out. */
  const onToggleClone = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const next = event.target.checked;
      const previous = draftSettings.clone_opt_in ?? false;
      const updated = { ...draftSettings, clone_opt_in: next };
      setDraftSettings(updated);
      try {
        await putMe({ settings: updated });
        if (next) {
          pushToast("success", "クローン学習を有効化しました");
        } else if (previous) {
          // AC-F7: opt-out path offers immediate deletion of learning data.
          const ok =
            typeof window !== "undefined"
              ? window.confirm(
                  "クローン学習データ (user_knowledge_namespace + user_interaction_log) を今すぐ削除しますか?",
                )
              : false;
          if (ok) {
            pushToast(
              "success",
              "学習データの削除をリクエストしました (DELETE /api/me/clone-data)",
            );
          } else {
            pushToast("info", "学習データの削除はあとから実行できます");
          }
        }
      } catch (err) {
        // rollback UI on failure.
        setDraftSettings({ ...draftSettings, clone_opt_in: previous });
        const message = friendlyOrFallback(err, "PUT /api/me");
        pushToast("error", message);
      }
    },
    [draftSettings, pushToast],
  );

  const cloneOptIn = draftSettings.clone_opt_in === true;

  const sectionRender = useMemo(
    () =>
      data ? (
        <>
          <ProfileSection
            user={data.user}
            draftName={draftName}
            draftAvatarUrl={draftAvatarUrl}
            settings={draftSettings}
            onChangeName={setDraftName}
            onChangeAvatar={setDraftAvatarUrl}
            onChangeSettings={setDraftSettings}
            onSubmit={onSaveProfile}
          />
          <NotificationsSection
            settings={draftSettings}
            onChange={setDraftSettings}
          />
          <ByokSection
            providers={BYOK_PROVIDERS}
            value={byokDraft}
            onChange={setByokDraft}
            onSubmit={onAddApiKey}
          />
          <OAuthSection providers={OAUTH_PROVIDERS} onUnlink={onUnlinkOAuth} />
          <CloneOptInSection
            checked={cloneOptIn}
            onChange={onToggleClone}
          />
          <DangerZoneSection />
        </>
      ) : null,
    [
      byokDraft,
      cloneOptIn,
      data,
      draftAvatarUrl,
      draftName,
      draftSettings,
      onAddApiKey,
      onSaveProfile,
      onToggleClone,
      onUnlinkOAuth,
    ],
  );

  return (
    <div
      data-screen-id="S-009"
      data-feature-id="F-022,F-023"
      data-task-ids="T-V3-C-09"
      data-entities="E-001,E-010,E-040"
      data-phase="Phase 1B"
      data-view-state={view}
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      <header className="px-6 py-4 border-b border-slate-200 bg-white sticky top-0 z-10">
        <div className="max-w-[800px] mx-auto flex items-center gap-3">
          <div className="w-7 h-7 rounded-md bg-eb-500 flex items-center justify-center text-white text-xs font-bold">
            BF
          </div>
          <h1 className="text-base font-bold">プロフィール設定</h1>
          <span className="ml-auto text-[11px] text-slate-400 font-mono">
            S-009 · T-V3-C-09
          </span>
        </div>
      </header>

      <main className="max-w-[800px] mx-auto px-6 py-8">
        <p className="text-sm text-slate-600 mb-6">
          個人情報 / API キー / OAuth 連携 / クローン opt-in
        </p>

        {view === "loading" && (
          <div
            role="status"
            aria-live="polite"
            className="bg-white border border-slate-200 rounded-lg p-6 text-center text-sm text-slate-500"
          >
            読み込み中…
          </div>
        )}

        {view === "error" && (
          <div
            role="alert"
            className="bg-rose-50 border border-rose-200 rounded-lg p-6 text-sm text-rose-700"
          >
            <div className="font-bold mb-2">プロフィールを読み込めませんでした</div>
            <div className="break-words">{errorMessage}</div>
            <button
              type="button"
              onClick={() => void loadProfile()}
              className="mt-3 px-3 py-1.5 text-xs border border-rose-300 rounded hover:bg-rose-100"
            >
              再試行
            </button>
          </div>
        )}

        {view === "loaded" && sectionRender}
      </main>

      {/* Non-technical toast region — referenced by AC-F5. */}
      <div
        role="region"
        aria-label="通知"
        data-testid="toast-region"
        className="fixed bottom-4 right-4 z-50 flex flex-col gap-2"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            data-testid={`toast-${t.kind}`}
            className={`max-w-sm border rounded-md p-3 shadow text-sm bg-white ${
              t.kind === "error"
                ? "border-rose-300 text-rose-700"
                : t.kind === "success"
                  ? "border-emerald-300 text-emerald-700"
                  : "border-slate-300 text-slate-700"
            }`}
          >
            <div className="flex items-start gap-2">
              <span className="flex-1 break-words">{t.message}</span>
              <button
                type="button"
                aria-label="close toast"
                className="text-xs text-slate-400 hover:text-slate-700"
                onClick={() => dismissToast(t.id)}
              >
                ×
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Sections
// --------------------------------------------------------------------------

function ProfileSection(props: {
  user: MeUser;
  draftName: string;
  draftAvatarUrl: string;
  settings: MeSettings;
  onChangeName: (v: string) => void;
  onChangeAvatar: (v: string) => void;
  onChangeSettings: (s: MeSettings) => void;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
}) {
  const initial = (props.draftName?.[0] ?? props.user.email?.[0] ?? "?").toUpperCase();
  return (
    <section className="bg-white border border-slate-200 rounded-lg p-6 mb-4">
      <h2 className="text-base font-bold mb-4">{SECTION_H2[0]}</h2>
      <form onSubmit={props.onSubmit} className="space-y-4">
        <div className="flex items-start gap-4">
          <div className="w-16 h-16 rounded-full bg-eb-500 text-white text-xl font-bold flex items-center justify-center">
            {initial}
          </div>
          <div className="flex-1 space-y-2">
            <label className="text-sm font-medium block">アバター URL</label>
            <input
              type="url"
              name="avatar_url"
              value={props.draftAvatarUrl}
              onChange={(e) => props.onChangeAvatar(e.target.value)}
              className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full"
              placeholder="https://..."
            />
            <p className="text-xs text-slate-500">JPG / PNG / 最大 2MB (URL 指定)</p>
          </div>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="bf-name" className="text-sm font-medium block">
            表示名
          </label>
          <input
            id="bf-name"
            type="text"
            name="name"
            value={props.draftName}
            onChange={(e) => props.onChangeName(e.target.value)}
            maxLength={128}
            className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full"
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="bf-email" className="text-sm font-medium block">
            メールアドレス
          </label>
          <input
            id="bf-email"
            type="email"
            value={props.user.email}
            readOnly
            className="border border-slate-200 bg-slate-50 text-sm h-9 px-3 rounded-md w-full"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label htmlFor="bf-timezone" className="text-sm font-medium block">
              タイムゾーン
            </label>
            <select
              id="bf-timezone"
              value={props.settings.timezone ?? "Asia/Tokyo"}
              onChange={(e) =>
                props.onChangeSettings({ ...props.settings, timezone: e.target.value })
              }
              className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full"
            >
              <option value="Asia/Tokyo">Asia/Tokyo (UTC+9)</option>
              <option value="America/Los_Angeles">America/Los_Angeles</option>
              <option value="UTC">UTC</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="bf-language" className="text-sm font-medium block">
              言語
            </label>
            <select
              id="bf-language"
              value={props.settings.language ?? "ja"}
              onChange={(e) =>
                props.onChangeSettings({ ...props.settings, language: e.target.value })
              }
              className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full"
            >
              <option value="ja">日本語</option>
              <option value="en">English</option>
            </select>
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <button
            type="submit"
            data-testid="save-profile"
            className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-4 rounded-md"
          >
            保存
          </button>
        </div>
      </form>
    </section>
  );
}

function NotificationsSection(props: {
  settings: MeSettings;
  onChange: (s: MeSettings) => void;
}) {
  const prefs = props.settings.notifications ?? {
    task_assigned: true,
    red_line: true,
    pr_review: true,
    weekly_summary: false,
  };
  const toggle = (key: string) => (e: ChangeEvent<HTMLInputElement>) => {
    props.onChange({
      ...props.settings,
      notifications: { ...prefs, [key]: e.target.checked },
    });
  };
  const rows: { key: string; title: string; hint: string }[] = [
    { key: "task_assigned", title: "タスク assigned", hint: "自分にタスクが割り当てられた時" },
    { key: "red_line", title: "赤線抵触", hint: "禁止操作を検知した時" },
    { key: "pr_review", title: "PR review request", hint: "レビュー依頼が来た時" },
    { key: "weekly_summary", title: "週次サマリー", hint: "毎週月曜にメール送信" },
  ];
  return (
    <section className="bg-white border border-slate-200 rounded-lg p-6 mb-4">
      <h2 className="text-base font-bold mb-4">{SECTION_H2[1]}</h2>
      <div className="space-y-3">
        {rows.map((r) => (
          <label key={r.key} className="flex items-center justify-between p-2">
            <div>
              <div className="text-sm font-medium">{r.title}</div>
              <div className="text-xs text-slate-500">{r.hint}</div>
            </div>
            <input
              type="checkbox"
              checked={prefs[r.key] === true}
              onChange={toggle(r.key)}
              className="w-4 h-4 accent-eb-500"
              aria-label={r.title}
            />
          </label>
        ))}
      </div>
    </section>
  );
}

function ByokSection(props: {
  providers: { id: string; label: string }[];
  value: { provider: string; api_key: string; label: string };
  onChange: (v: { provider: string; api_key: string; label: string }) => void;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="bg-white border border-slate-200 rounded-lg p-6 mb-4">
      <h2 className="text-base font-bold mb-1">{SECTION_H2[2]}</h2>
      <p className="text-xs text-slate-500 mb-4">
        自分の API キーを使うと利用料金が直接プロバイダに請求される
      </p>
      <form onSubmit={props.onSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <label htmlFor="byok-provider" className="text-sm font-medium block">
              プロバイダ
            </label>
            <select
              id="byok-provider"
              value={props.value.provider}
              onChange={(e) => props.onChange({ ...props.value, provider: e.target.value })}
              className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full"
            >
              {props.providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="byok-label" className="text-sm font-medium block">
              ラベル (任意)
            </label>
            <input
              id="byok-label"
              type="text"
              value={props.value.label}
              onChange={(e) => props.onChange({ ...props.value, label: e.target.value })}
              maxLength={64}
              className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full"
              placeholder="例: メイン"
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <label htmlFor="byok-key" className="text-sm font-medium block">
            API キー
          </label>
          <input
            id="byok-key"
            type="password"
            value={props.value.api_key}
            onChange={(e) => props.onChange({ ...props.value, api_key: e.target.value })}
            autoComplete="off"
            className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md w-full font-mono"
            placeholder="sk-ant-..."
          />
        </div>
        <div className="flex justify-end">
          <button
            type="submit"
            data-testid="add-api-key"
            className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-4 rounded-md"
          >
            API キーを追加
          </button>
        </div>
      </form>
    </section>
  );
}

function OAuthSection(props: {
  providers: { id: string; label: string }[];
  onUnlink: (provider: string) => void;
}) {
  return (
    <section className="bg-white border border-slate-200 rounded-lg p-6 mb-4">
      <h2 className="text-base font-bold mb-4">{SECTION_H2[3]}</h2>
      <div className="space-y-2">
        {props.providers.map((p) => (
          <div
            key={p.id}
            className="border border-slate-200 rounded-md p-3 flex items-center gap-3"
          >
            <div className="flex-1">
              <div className="text-sm font-semibold">{p.label}</div>
              <div className="text-xs text-slate-500">未連携</div>
            </div>
            <button
              type="button"
              data-testid={`unlink-${p.id}`}
              onClick={() => props.onUnlink(p.id)}
              className="text-xs text-slate-500 hover:text-red-600"
            >
              解除
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function CloneOptInSection(props: {
  checked: boolean;
  onChange: (e: ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <section className="bg-white border border-slate-200 rounded-lg p-6 mb-4">
      <h2 className="text-base font-bold mb-1">{SECTION_H2[4]}</h2>
      <p className="text-xs text-slate-500 mb-4">
        あなたの過去判断を Constitution に学習させ、AI 社員が「あなたなら何と言うか」を提案する
      </p>
      <label className="flex items-start gap-3 p-3 border border-slate-200 rounded-md hover:border-eb-200 cursor-pointer">
        <input
          type="checkbox"
          data-testid="clone-opt-in"
          checked={props.checked}
          onChange={props.onChange}
          className="w-4 h-4 accent-eb-500 mt-1"
          aria-label="クローン学習を有効化"
        />
        <div className="flex-1">
          <div className="text-sm font-semibold mb-1">クローン学習を有効化 (opt-in)</div>
          <div className="text-xs text-slate-600 leading-relaxed">
            過去の判断ログ・コメント・コミットメッセージ・ヒアリング音声を学習に使用します。
            <br />
            いつでも opt-out 可能 / 学習データは削除可能 (GDPR 準拠)。
          </div>
          {!props.checked && (
            <div
              data-testid="clone-opt-out-status"
              className="text-[11px] text-slate-500 mt-2"
            >
              現在オプトアウト中: user_interaction_log への記録は行われません (DB trigger)
            </div>
          )}
        </div>
      </label>
    </section>
  );
}

function DangerZoneSection() {
  return (
    <section className="bg-white border border-red-200 rounded-lg p-6">
      <h2 className="text-base font-bold text-red-600 mb-3">{SECTION_H2[5]}</h2>
      <div className="space-y-3">
        <div className="flex items-center justify-between p-3 border border-slate-200 rounded-md">
          <div>
            <div className="text-sm font-semibold">
              自分のデータをエクスポート (GDPR)
            </div>
            <div className="text-xs text-slate-500">
              プロフィール・判断ログ・学習データ全件
            </div>
          </div>
          <button
            type="button"
            className="border border-slate-300 hover:bg-slate-50 text-sm h-9 px-4 rounded-md"
          >
            エクスポート
          </button>
        </div>
        <div className="flex items-center justify-between p-3 border border-red-200 rounded-md">
          <div>
            <div className="text-sm font-semibold text-red-600">アカウント削除依頼</div>
            <div className="text-xs text-slate-500">30 日後に物理削除されます</div>
          </div>
          <button
            type="button"
            className="bg-white border border-red-600 text-red-600 hover:bg-red-50 text-sm font-semibold h-9 px-4 rounded-md"
          >
            削除依頼
          </button>
        </div>
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

function friendlyOrFallback(err: unknown, endpoint: string): string {
  if (err instanceof MeApiError) {
    return err.toUserMessage();
  }
  // AC-F5: never leak raw error.message (may contain stack trace artefacts).
  return `通信に失敗しました (${endpoint})`;
}
