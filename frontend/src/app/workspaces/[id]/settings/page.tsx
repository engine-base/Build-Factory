"use client";

/**
 * S-013 案件設定 ページ — mock 完全準拠
 *
 * mock: docs/mocks/2026-05-09_v1/workspace/S-013-workspace-settings.html
 * tickets: T-004-05 (Owner 移譲) ほか F-004 系
 *
 * Tab 構成 (mock 準拠):
 *   1. 一般           : 案件名 / クライアント / 納期 / 予算上限 / GitHub リポジトリ
 *   2. フェーズゲート  : strict / guide / free (DAG 順序の厳密さ)
 *   3. レッドライン    : 禁止コマンド / 禁止ファイル パターン (JSON 配列)
 *   4. 統合            : GitHub repo / Slack channel
 *   5. 予算 / コスト   : monthly budget (Claude API) + 当月 spent (Phase 1.5)
 *   6. アーカイブ      : workspace 削除 (status=archived)
 *
 * 追加 (mock 範囲外、 T-004-05 要件):
 *   7. メンバーシップ : Owner 移譲
 */

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Workspace, fetchWorkspace, updateWorkspace, archiveWorkspace,
  fetchMembers, transferOwnership, type WorkspaceMember,
} from "@/lib/workspaces";
import { WorkspaceShell } from "@/components/workspace-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Info, GitBranch, ShieldAlert, Plug, Wallet, Archive,
  Users, Crown, CheckCircle2, Loader2,
  Lock, Navigation, Zap, MessageSquare, FolderGit2,
} from "lucide-react";

const CURRENT_USER_ID = "masato";  // TODO: auth integration

type SectionId =
  | "general"
  | "phase_gate"
  | "redlines"
  | "integrations"
  | "budget"
  | "archive"
  | "membership";

const NAV_ITEMS: { id: SectionId; label: string; icon: typeof Info; danger?: boolean }[] = [
  { id: "general",      label: "一般",             icon: Info },
  { id: "phase_gate",   label: "フェーズゲート",     icon: GitBranch },
  { id: "redlines",     label: "レッドライン",       icon: ShieldAlert },
  { id: "integrations", label: "統合 (GitHub/Slack)", icon: Plug },
  { id: "budget",       label: "予算 / コスト",      icon: Wallet },
  { id: "membership",   label: "メンバーシップ",     icon: Users },
  { id: "archive",      label: "アーカイブ",         icon: Archive, danger: true },
];

export default function SettingsPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params?.id);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [section, setSection] = useState<SectionId>("general");
  const [toast, setToast] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchWorkspace(id).then(setWorkspace).catch(() => setWorkspace(null));
  }, [id]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  const handleArchive = async () => {
    if (!workspace) return;
    if (!confirm(`「${workspace.name}」をアーカイブします。一覧から非表示になります (後から status=active で復元可能)。よろしいですか？`)) return;
    try {
      await archiveWorkspace(workspace.id);
      router.push("/workspaces");
    } catch {
      setToast({ kind: "err", msg: "アーカイブに失敗しました" });
    }
  };

  if (!workspace) {
    return (
      <div className="p-6 flex items-center gap-2 text-slate-400 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" /> ワークスペースを読み込み中…
      </div>
    );
  }

  return (
    <WorkspaceShell
      workspaceId={id}
      workspaceName={workspace.name}
      active="settings"
      breadcrumbs={[
        { label: "Workspaces", href: "/workspaces" },
        { label: workspace.name, href: `/workspaces/${id}` },
        { label: "案件設定" },
      ]}
    >
      <div className="mb-6">
        <h1 className="text-xl font-bold text-slate-900">案件設定 — {workspace.name}</h1>
        <p className="text-xs text-slate-500 mt-1">
          mock: S-013 / feature: F-004
        </p>
      </div>

      {toast && (
        <div
          role="status"
          className={`fixed top-6 right-6 z-50 px-4 py-2.5 rounded-md text-white text-sm font-bold shadow-lg flex items-center gap-2 ${
            toast.kind === "ok" ? "bg-eb-500" : "bg-rose-600"
          }`}
        >
          <CheckCircle2 className="w-4 h-4" />
          {toast.msg}
        </div>
      )}

      <div className="grid grid-cols-[200px_1fr] gap-6">
        <nav className="text-sm space-y-1 sticky top-0 h-fit">
          {NAV_ITEMS.map((it) => {
            const Icon = it.icon;
            const active = section === it.id;
            return (
              <button
                key={it.id}
                onClick={() => setSection(it.id)}
                className={`w-full text-left px-3 py-2 rounded inline-flex items-center gap-2 transition-colors ${
                  active
                    ? "bg-eb-50 text-eb-700 font-bold"
                    : it.danger
                    ? "text-rose-600 hover:bg-rose-50"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {it.label}
              </button>
            );
          })}
        </nav>

        <section className="space-y-6">
          {section === "general" && (
            <GeneralSection
              workspace={workspace}
              onSaved={(w) => { setWorkspace(w); setToast({ kind: "ok", msg: "一般設定を保存しました" }); }}
              onError={(m) => setToast({ kind: "err", msg: m })}
            />
          )}
          {section === "phase_gate" && (
            <PhaseGateSection
              workspace={workspace}
              onSaved={(w) => { setWorkspace(w); setToast({ kind: "ok", msg: "フェーズゲート設定を保存しました" }); }}
              onError={(m) => setToast({ kind: "err", msg: m })}
            />
          )}
          {section === "redlines" && (
            <RedlinesSection
              workspace={workspace}
              onSaved={(w) => { setWorkspace(w); setToast({ kind: "ok", msg: "レッドラインを保存しました" }); }}
              onError={(m) => setToast({ kind: "err", msg: m })}
            />
          )}
          {section === "integrations" && (
            <IntegrationsSection
              workspace={workspace}
              onSaved={(w) => { setWorkspace(w); setToast({ kind: "ok", msg: "統合設定を保存しました" }); }}
              onError={(m) => setToast({ kind: "err", msg: m })}
            />
          )}
          {section === "budget" && (
            <BudgetSection
              workspace={workspace}
              onSaved={(w) => { setWorkspace(w); setToast({ kind: "ok", msg: "予算を保存しました" }); }}
              onError={(m) => setToast({ kind: "err", msg: m })}
            />
          )}
          {section === "membership" && (
            <MembershipSection workspaceId={id} onToast={setToast} />
          )}
          {section === "archive" && (
            <ArchiveSection onArchive={handleArchive} />
          )}
        </section>
      </div>
    </WorkspaceShell>
  );
}


// ═══════════════════════════════════════════════════════════
// 共通コンポーネント
// ═══════════════════════════════════════════════════════════
function Card({ title, desc, danger, children }: {
  title: string; desc?: string; danger?: boolean; children: React.ReactNode;
}) {
  return (
    <div className={`bg-white border rounded-lg overflow-hidden ${
      danger ? "border-rose-200" : "border-slate-200"
    }`}>
      <div className="px-5 py-3 border-b border-slate-100">
        <h2 className={`text-sm font-bold ${danger ? "text-rose-700" : "text-slate-900"}`}>{title}</h2>
        {desc && <p className="text-xs text-slate-500 mt-1">{desc}</p>}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function Field({ label, help, children }: {
  label: string; help?: string; children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-bold text-slate-700 block">{label}</label>
      {children}
      {help && <p className="text-[11px] text-slate-500">{help}</p>}
    </div>
  );
}

/** shadcn Input の薄いラッパ — max-w-md を当てる */
function TextInput(props: React.ComponentProps<typeof Input>) {
  return <Input {...props} className={`max-w-md ${props.className ?? ""}`} />;
}

function NumberInput(props: React.ComponentProps<typeof Input>) {
  return <Input type="number" {...props} className={`w-32 mono ${props.className ?? ""}`} />;
}


// ═══════════════════════════════════════════════════════════
// 1. 一般 (S-013 mock 一般タブ準拠)
// ═══════════════════════════════════════════════════════════
function GeneralSection({
  workspace, onSaved, onError,
}: {
  workspace: Workspace;
  onSaved: (w: Workspace) => void;
  onError: (m: string) => void;
}) {
  const [name, setName] = useState(workspace.name);
  const [clientName, setClientName] = useState(workspace.client_name ?? "");
  const [dueDate, setDueDate] = useState(workspace.due_date ?? "");
  const [description, setDescription] = useState(workspace.description ?? "");
  const [status, setStatus] = useState<Workspace["status"]>(workspace.status);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setName(workspace.name);
    setClientName(workspace.client_name ?? "");
    setDueDate(workspace.due_date ?? "");
    setDescription(workspace.description ?? "");
    setStatus(workspace.status);
  }, [workspace.id, workspace.name, workspace.client_name, workspace.due_date,
      workspace.description, workspace.status]);

  const dirty =
    name !== workspace.name ||
    clientName !== (workspace.client_name ?? "") ||
    dueDate !== (workspace.due_date ?? "") ||
    description !== (workspace.description ?? "") ||
    status !== workspace.status;

  const handleSave = async () => {
    if (!dirty || saving) return;
    setSaving(true);
    try {
      const updated = await updateWorkspace(workspace.id, {
        name: name.trim(),
        client_name: clientName.trim() || null,
        due_date: dueDate || null,
        description: description.trim() || null,
        status,
      });
      onSaved(updated);
    } catch {
      onError("保存に失敗しました");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setName(workspace.name);
    setClientName(workspace.client_name ?? "");
    setDueDate(workspace.due_date ?? "");
    setDescription(workspace.description ?? "");
    setStatus(workspace.status);
  };

  return (
    <Card title="案件設定" desc="プロジェクトの基本情報">
      <div className="space-y-4">
        <Field label="案件名">
          <TextInput value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="クライアント">
          <TextInput
            placeholder="例: 株式会社XX"
            value={clientName}
            onChange={(e) => setClientName(e.target.value)}
          />
        </Field>
        <Field label="納期">
          <TextInput type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
        </Field>
        <Field label="概要">
          <Textarea
            className="max-w-xl h-24"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <Field label="ステータス">
          <select
            className="w-full max-w-md px-3 py-2 text-sm border border-slate-300 rounded bg-white focus:outline-none focus:ring-2 focus:ring-eb-500/30 focus:border-eb-500"
            value={status}
            onChange={(e) => setStatus(e.target.value as Workspace["status"])}
          >
            <option value="active">進行中 (active)</option>
            <option value="paused">一時停止 (paused)</option>
            <option value="archived">アーカイブ (archived)</option>
          </select>
        </Field>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={handleReset} disabled={!dirty || saving}>
            キャンセル
          </Button>
          <Button
            className="bg-eb-500 hover:bg-eb-600 text-white font-bold"
            onClick={handleSave}
            disabled={!dirty || saving}
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            保存
          </Button>
        </div>
      </div>
    </Card>
  );
}


// ═══════════════════════════════════════════════════════════
// 2. フェーズゲート (DAG 順序の厳密さ)
// ═══════════════════════════════════════════════════════════
function PhaseGateSection({
  workspace, onSaved, onError,
}: {
  workspace: Workspace;
  onSaved: (w: Workspace) => void;
  onError: (m: string) => void;
}) {
  const [mode, setMode] = useState<"strict" | "guide" | "free">(
    (workspace.phase_gate_mode ?? "guide") as any,
  );
  const [saving, setSaving] = useState(false);
  const initial = (workspace.phase_gate_mode ?? "guide") as "strict" | "guide" | "free";

  const dirty = mode !== initial;

  const cards = [
    { id: "strict", icon: Lock,       title: "厳格",         desc: "前提フェーズ完了まで次に進めない。新人 PM や教育用。" },
    { id: "guide",  icon: Navigation, title: "ガイド (推奨)", desc: "前提未完了は警告モーダル。理由入力で強制突破可能。" },
    { id: "free",   icon: Zap,        title: "自由",         desc: "制限なし。表示のみ。経験者向け。" },
  ];

  const handleSave = async () => {
    if (!dirty || saving) return;
    setSaving(true);
    try {
      const updated = await updateWorkspace(workspace.id, { phase_gate_mode: mode });
      onSaved(updated);
    } catch {
      onError("保存に失敗しました");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card title="フェーズゲート モード" desc="DAG 順序を厳密に守るか、自由に飛ばせるかを設定">
      <div className="grid grid-cols-3 gap-3 mb-5">
        {cards.map((c) => {
          const selected = mode === c.id;
          const Icon = c.icon;
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => setMode(c.id as any)}
              className={`text-left p-4 rounded border-2 transition-colors ${
                selected
                  ? "border-eb-500 bg-eb-50"
                  : "border-slate-200 hover:border-slate-300"
              }`}
            >
              <div className="flex items-center gap-1.5 text-sm font-bold text-slate-900 mb-1">
                <Icon className="w-3.5 h-3.5" />
                {c.title}
              </div>
              <p className="text-[11px] text-slate-600 leading-relaxed">{c.desc}</p>
            </button>
          );
        })}
      </div>
      <div className="flex justify-end">
        <Button
          className="bg-eb-500 hover:bg-eb-600 text-white font-bold"
          onClick={handleSave}
          disabled={!dirty || saving}
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
          保存
        </Button>
      </div>
    </Card>
  );
}


// ═══════════════════════════════════════════════════════════
// 3. レッドライン (禁止コマンド・ファイル パターン)
// ═══════════════════════════════════════════════════════════
function RedlinesSection({
  workspace, onSaved, onError,
}: {
  workspace: Workspace;
  onSaved: (w: Workspace) => void;
  onError: (m: string) => void;
}) {
  const initialRedlines: string[] = (() => {
    try {
      return JSON.parse(workspace.redlines ?? "[]");
    } catch {
      return [];
    }
  })();
  const [items, setItems] = useState<string[]>(initialRedlines);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);

  const dirty = JSON.stringify(items) !== JSON.stringify(initialRedlines);

  const handleAdd = () => {
    const v = draft.trim();
    if (!v) return;
    if (items.includes(v)) return;
    setItems([...items, v]);
    setDraft("");
  };

  const handleRemove = (s: string) => setItems(items.filter((x) => x !== s));

  const handleSave = async () => {
    if (!dirty || saving) return;
    setSaving(true);
    try {
      const updated = await updateWorkspace(workspace.id, { redlines: items });
      onSaved(updated);
    } catch {
      onError("保存に失敗しました");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card title="レッドライン" desc="AI が触れない/実行できないコマンドやファイル パターンを定義">
      <div className="space-y-3">
        <div className="flex gap-2">
          <TextInput
            placeholder="例: rm -rf / または .env"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleAdd(); } }}
          />
          <Button variant="outline" onClick={handleAdd} disabled={!draft.trim()}>
            追加
          </Button>
        </div>

        {items.length === 0 ? (
          <p className="text-xs text-slate-500">レッドラインは未設定です。CLAUDE.md §5.4 のデフォルトのみ適用されます。</p>
        ) : (
          <ul className="space-y-1.5">
            {items.map((it) => (
              <li key={it} className="flex items-center justify-between px-3 py-2 bg-rose-50 border border-rose-200 rounded text-xs mono text-rose-800">
                <span>{it}</span>
                <button
                  className="text-rose-600 hover:text-rose-800 text-[11px]"
                  onClick={() => handleRemove(it)}
                >
                  削除
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="flex justify-end pt-2">
          <Button
            className="bg-eb-500 hover:bg-eb-600 text-white font-bold"
            onClick={handleSave}
            disabled={!dirty || saving}
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            保存
          </Button>
        </div>
      </div>
    </Card>
  );
}


// ═══════════════════════════════════════════════════════════
// 4. 統合 (GitHub / Slack)
// ═══════════════════════════════════════════════════════════
function IntegrationsSection({
  workspace, onSaved, onError,
}: {
  workspace: Workspace;
  onSaved: (w: Workspace) => void;
  onError: (m: string) => void;
}) {
  const [github, setGithub] = useState(workspace.github_repo ?? "");
  const [slack, setSlack] = useState(workspace.slack_channel ?? "");
  const [saving, setSaving] = useState(false);

  const dirty =
    github !== (workspace.github_repo ?? "") ||
    slack !== (workspace.slack_channel ?? "");

  const handleSave = async () => {
    if (!dirty || saving) return;
    setSaving(true);
    try {
      const updated = await updateWorkspace(workspace.id, {
        github_repo: github.trim() || null,
        slack_channel: slack.trim() || null,
      });
      onSaved(updated);
    } catch {
      onError("保存に失敗しました");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card title="統合" desc="GitHub / Slack 連携">
      <div className="space-y-4">
        <Field label="GitHub リポジトリ" help="形式: owner/repo (例: engine-base/proj-ec-4)">
          <div className="flex items-center gap-2">
            <FolderGit2 className="w-4 h-4 text-slate-600" />
            <TextInput
              placeholder="engine-base/proj-ec-4"
              value={github}
              onChange={(e) => setGithub(e.target.value)}
            />
          </div>
        </Field>
        <Field label="Slack チャネル" help="形式: #channel_name">
          <div className="flex items-center gap-2">
            <MessageSquare className="w-4 h-4 text-slate-600" />
            <TextInput
              placeholder="#proj-ec-4"
              value={slack}
              onChange={(e) => setSlack(e.target.value)}
            />
          </div>
        </Field>
        <div className="flex justify-end pt-2">
          <Button
            className="bg-eb-500 hover:bg-eb-600 text-white font-bold"
            onClick={handleSave}
            disabled={!dirty || saving}
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            保存
          </Button>
        </div>
      </div>
    </Card>
  );
}


// ═══════════════════════════════════════════════════════════
// 5. 予算 / コスト
// ═══════════════════════════════════════════════════════════
function BudgetSection({
  workspace, onSaved, onError,
}: {
  workspace: Workspace;
  onSaved: (w: Workspace) => void;
  onError: (m: string) => void;
}) {
  const [budget, setBudget] = useState<string>(
    workspace.budget_jpy_monthly != null ? String(workspace.budget_jpy_monthly) : "",
  );
  const [saving, setSaving] = useState(false);

  const dirty = budget !== (workspace.budget_jpy_monthly != null ? String(workspace.budget_jpy_monthly) : "");

  const handleSave = async () => {
    if (!dirty || saving) return;
    const n = budget ? Number(budget) : null;
    if (budget && (Number.isNaN(n) || (n as number) < 0)) {
      onError("予算は 0 以上の数値で指定してください");
      return;
    }
    setSaving(true);
    try {
      const updated = await updateWorkspace(workspace.id, { budget_jpy_monthly: n as any });
      onSaved(updated);
    } catch {
      onError("保存に失敗しました");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card title="予算 / コスト" desc="Claude API の月次予算上限 (超過時はキュー停止)">
      <div className="space-y-4">
        <Field label="予算上限 (JPY / 月)" help="未設定 = 制限なし。 例: 40000">
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-500">¥</span>
            <NumberInput
              placeholder="40000"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              min={0}
            />
            <span className="text-xs text-slate-500">/ 月</span>
          </div>
        </Field>
        <div className="px-3 py-2 bg-slate-50 rounded text-xs text-slate-500">
          当月実績の集計表示は Phase 1.5 で実装予定 (cost_logs 連携)
        </div>
        <div className="flex justify-end pt-2">
          <Button
            className="bg-eb-500 hover:bg-eb-600 text-white font-bold"
            onClick={handleSave}
            disabled={!dirty || saving}
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
            保存
          </Button>
        </div>
      </div>
    </Card>
  );
}


// ═══════════════════════════════════════════════════════════
// 6. メンバーシップ (T-004-05 Owner 移譲)
// ═══════════════════════════════════════════════════════════
function MembershipSection({
  workspaceId,
  onToast,
}: {
  workspaceId: number;
  onToast: (t: { kind: "ok" | "err"; msg: string }) => void;
}) {
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [targetUserId, setTargetUserId] = useState("");
  const [transferring, setTransferring] = useState(false);

  useEffect(() => {
    fetchMembers(workspaceId)
      .then((m) => setMembers(m))
      .finally(() => setLoading(false));
  }, [workspaceId]);

  const currentOwner = members.find((m) => m.role === "owner");
  const isOwner = currentOwner?.user_id === CURRENT_USER_ID;
  const eligibleTargets = members.filter((m) => m.user_id !== CURRENT_USER_ID && m.role !== "owner");

  const handleTransfer = async () => {
    if (!isOwner) return;
    if (!targetUserId) {
      onToast({ kind: "err", msg: "移譲先メンバーを選択してください" });
      return;
    }
    const target = members.find((m) => m.user_id === targetUserId);
    if (!confirm(`Owner 権限を ${target?.user_id} に移譲します。あなたは ws_admin に降格します。よろしいですか？`)) return;
    setTransferring(true);
    try {
      const result = await transferOwnership(workspaceId, CURRENT_USER_ID, targetUserId);
      if (result.ok) {
        onToast({ kind: "ok", msg: `Owner を ${targetUserId} に移譲しました` });
        const updated = await fetchMembers(workspaceId);
        setMembers(updated);
        setTargetUserId("");
      } else if (result.detail?.code === "target_not_member") {
        onToast({ kind: "err", msg: "選択したユーザーはこのワークスペースのメンバーではありません" });
      } else {
        onToast({ kind: "err", msg: result.detail?.message ?? "Owner 移譲に失敗しました" });
      }
    } catch {
      onToast({ kind: "err", msg: "Owner 移譲に失敗しました" });
    } finally {
      setTransferring(false);
    }
  };

  return (
    <Card title="メンバーシップ" desc="ワークスペースのオーナーシップ管理">
      <div className="space-y-5">
        <div>
          <div className="text-xs font-bold text-slate-700 mb-2">現在の Owner</div>
          <div className="flex items-center gap-2 px-3 py-2.5 bg-eb-50 border border-eb-100 rounded text-sm">
            <Crown className="w-4 h-4 text-eb-500" />
            <span className="font-bold text-slate-900">
              {loading ? "読み込み中…" : currentOwner?.user_id ?? "未割当"}
            </span>
            {isOwner && <span className="ml-auto text-[11px] text-eb-500">(あなた)</span>}
          </div>
        </div>

        <div className="border-t border-slate-100 pt-4">
          <div className="text-sm font-bold text-slate-900 mb-1">Owner を移譲する</div>
          <p className="text-xs text-slate-500 mb-3">
            {isOwner
              ? "別のメンバーを Owner にします。あなたは ws_admin に降格します。"
              : "Owner のみがこの操作を実行できます。"}
          </p>

          {isOwner && (
            <div className="flex items-center gap-2">
              <select
                className="flex-1 max-w-md px-3 py-2 text-sm border border-slate-300 rounded bg-white focus:outline-none focus:ring-2 focus:ring-eb-500/30 focus:border-eb-500"
                value={targetUserId}
                onChange={(e) => setTargetUserId(e.target.value)}
              >
                <option value="">移譲先メンバーを選択…</option>
                {eligibleTargets.map((m) => (
                  <option key={m.user_id} value={m.user_id}>
                    {m.user_id} ({m.role})
                  </option>
                ))}
              </select>
              <Button
                className="bg-eb-500 hover:bg-eb-600 text-white font-bold"
                onClick={handleTransfer}
                disabled={!targetUserId || transferring}
              >
                {transferring ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Crown className="w-3.5 h-3.5" />}
                移譲する
              </Button>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}


// ═══════════════════════════════════════════════════════════
// 7. アーカイブ
// ═══════════════════════════════════════════════════════════
function ArchiveSection({ onArchive }: { onArchive: () => void }) {
  return (
    <Card title="アーカイブ" desc="ワークスペースを読み取り専用にして一覧から非表示にします" danger>
      <div className="space-y-3">
        <p className="text-sm text-slate-700">
          アーカイブ済みワークスペースは <code className="mono text-xs bg-slate-100 px-1 rounded">status=archived</code> になり、 一覧から非表示になります。 後から status を active に戻すことで復元できます。
        </p>
        <div className="flex justify-end">
          <Button
            className="bg-rose-600 hover:bg-rose-700 text-white font-bold"
            onClick={onArchive}
          >
            <Archive className="w-3.5 h-3.5" />
            アーカイブする
          </Button>
        </div>
      </div>
    </Card>
  );
}
