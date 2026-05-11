"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Workspace, fetchWorkspace, updateWorkspace, archiveWorkspace,
  fetchMembers, transferOwnership, type WorkspaceMember,
} from "@/lib/workspaces";
import { WorkspaceShell } from "@/components/workspace-shell";
import {
  Info, GitBranch, Palette, Cpu, Bell, KeyRound, Archive,
  AlertTriangle, Lock, Navigation, Zap, CheckCircle2,
  Users, Crown,
} from "lucide-react";

const NAV_ITEMS = [
  { id: "info",        label: "基本情報",   icon: Info },
  { id: "membership",  label: "メンバーシップ", icon: Users },
  { id: "phase",       label: "フェーズ制御", icon: GitBranch },
  { id: "penpot",      label: "Penpot 連携",  icon: Palette },
  { id: "ai",          label: "AI モデル",    icon: Cpu },
  { id: "notify",      label: "通知",         icon: Bell },
  { id: "tokens",      label: "API トークン", icon: KeyRound },
  { id: "archive",     label: "アーカイブ",   icon: Archive },
  { id: "danger",      label: "危険ゾーン",   icon: AlertTriangle, danger: true },
];

const CURRENT_USER_ID = "masato";  // TODO: auth から取得

export default function SettingsPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params?.id);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [section, setSection] = useState("info");
  const [phaseMode, setPhaseMode] = useState<"strict" | "guide" | "free">("guide");
  const [parallelOn, setParallelOn] = useState(true);
  const [pmApprovalOn, setPmApprovalOn] = useState(true);
  const [reasonRequiredOn, setReasonRequiredOn] = useState(true);
  const [clientCanEdit, setClientCanEdit] = useState(false);
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
    if (!confirm(`プロジェクト「${workspace.name}」をアーカイブします。一覧から非表示になります（後から復元可能）。よろしいですか？`)) return;
    try {
      await archiveWorkspace(workspace.id);
      router.push("/workspaces");
    } catch {
      setToast({ kind: "err", msg: "アーカイブに失敗しました" });
    }
  };

  if (!workspace) return <div className="p-6" style={{ color: "var(--bf-text-3)" }}>読み込み中…</div>;

  return (
    <WorkspaceShell
      workspaceId={id}
      workspaceName={workspace.name}
      progressPercent={45}
      daysLeft={23}
      active="settings"
      breadcrumbs={[
        { label: "Workspaces", href: "/workspaces" },
        { label: workspace.name, href: `/workspaces/${id}` },
        { label: "プロジェクト設定" },
      ]}
    >
      <div style={{ marginBottom: "var(--bf-space-6)" }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.01em", color: "var(--bf-text-1)", marginBottom: 4 }}>
          プロジェクト設定
        </h1>
        <div style={{ color: "var(--bf-text-3)", fontSize: 13 }}>
          基本情報 / フェーズ制御 / Penpot 連携 / 通知 / アーカイブ
        </div>
      </div>

      {toast && (
        <div
          role="status"
          style={{
            position: "fixed", top: 24, right: 24, zIndex: 60,
            background: toast.kind === "ok" ? "var(--bf-primary)" : "var(--bf-danger)",
            color: "#fff",
            padding: "10px 16px",
            borderRadius: "var(--bf-radius-md)",
            fontSize: 13,
            fontWeight: 600,
            boxShadow: "0 6px 24px rgba(0,0,0,.18)",
            display: "flex", alignItems: "center", gap: 8,
          }}
        >
          <CheckCircle2 className="w-4 h-4" />
          {toast.msg}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: "var(--bf-space-6)" }}>
        {/* Nav */}
        <nav style={{
          background: "var(--bf-bg-elev)",
          border: "1px solid var(--bf-border)",
          borderRadius: "var(--bf-radius-lg)",
          padding: "var(--bf-space-3)",
          height: "fit-content",
          position: "sticky", top: 0,
        }}>
          {NAV_ITEMS.map((it) => (
            <button
              key={it.id}
              onClick={() => setSection(it.id)}
              className="w-full flex items-center gap-2.5 transition-colors"
              style={{
                padding: "8px 12px",
                margin: "1px 0",
                borderRadius: "var(--bf-radius-md)",
                fontSize: 13,
                fontWeight: section === it.id ? 600 : 400,
                background: section === it.id ? "var(--bf-primary-bg)" : "transparent",
                color: section === it.id ? "var(--bf-primary)" : it.danger ? "var(--bf-danger)" : "var(--bf-text-2)",
              }}
            >
              <it.icon className="w-3.5 h-3.5" />
              {it.label}
            </button>
          ))}
        </nav>

        {/* Content */}
        <div>
          {section === "info" && (
            <BasicSection
              workspace={workspace}
              onSaved={(w) => { setWorkspace(w); setToast({ kind: "ok", msg: "基本情報を保存しました" }); }}
              onError={(m) => setToast({ kind: "err", msg: m })}
            />
          )}
          {section === "phase" && (
            <PhaseControlSection
              mode={phaseMode} setMode={setPhaseMode}
              parallel={parallelOn} setParallel={setParallelOn}
              pmApproval={pmApprovalOn} setPmApproval={setPmApprovalOn}
              reasonRequired={reasonRequiredOn} setReasonRequired={setReasonRequiredOn}
            />
          )}
          {section === "penpot" && <PenpotSection clientEdit={clientCanEdit} setClientEdit={setClientCanEdit} />}
          {section === "ai" && <AiModelSection />}
          {section === "membership" && (
            <MembershipSection
              workspaceId={id}
              onToast={setToast}
            />
          )}
          {section === "danger" && <DangerSection onArchive={handleArchive} />}
          {!["info", "membership", "phase", "penpot", "ai", "danger"].includes(section) && (
            <SettingsCard title={NAV_ITEMS.find((n) => n.id === section)?.label ?? ""} icon={NAV_ITEMS.find((n) => n.id === section)?.icon ?? Info}>
              <div style={{ padding: "var(--bf-space-12) var(--bf-space-6)", textAlign: "center", color: "var(--bf-text-3)", fontSize: 13 }}>
                この設定セクションは実装中です。
              </div>
            </SettingsCard>
          )}
        </div>
      </div>
    </WorkspaceShell>
  );
}

function SettingsCard({ title, desc, icon: Icon, children, danger }: {
  title: string; desc?: string; icon: any; children: React.ReactNode; danger?: boolean;
}) {
  return (
    <div style={{
      background: danger ? "#FEF2F2" : "var(--bf-bg-elev)",
      border: `1px solid ${danger ? "var(--bf-danger-bg)" : "var(--bf-border)"}`,
      borderRadius: "var(--bf-radius-lg)",
      marginBottom: "var(--bf-space-5)",
      overflow: "hidden",
    }}>
      <div style={{ padding: "14px var(--bf-space-5)", borderBottom: `1px solid ${danger ? "var(--bf-danger-bg)" : "var(--bf-divider)"}` }}>
        <div className="flex items-center gap-2" style={{ fontSize: 15, fontWeight: 700, color: danger ? "var(--bf-danger)" : "var(--bf-text-1)", marginBottom: 4 }}>
          <Icon className="w-4 h-4" />
          {title}
        </div>
        {desc && <div style={{ fontSize: 12.5, color: "var(--bf-text-3)" }}>{desc}</div>}
      </div>
      <div style={{ padding: "var(--bf-space-5)" }}>
        {children}
      </div>
    </div>
  );
}

function FormGroup({ label, children, help }: { label: string; children: React.ReactNode; help?: string }) {
  return (
    <div style={{ marginBottom: "var(--bf-space-4)" }}>
      <label style={{ display: "block", fontSize: 12.5, fontWeight: 600, color: "var(--bf-text-2)", marginBottom: 6 }}>
        {label}
      </label>
      {children}
      {help && <div style={{ fontSize: 11.5, color: "var(--bf-text-3)", marginTop: 4 }}>{help}</div>}
    </div>
  );
}

function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      style={{
        width: "100%", height: 40, padding: "0 12px",
        background: "var(--bf-bg-input)",
        border: "1px solid var(--bf-border)",
        borderRadius: "var(--bf-radius-md)",
        color: "var(--bf-text-1)",
        fontSize: 13, outline: "none",
        ...(props.style ?? {}),
      }}
    />
  );
}

function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      style={{
        width: "100%", padding: "10px 12px",
        background: "var(--bf-bg-input)",
        border: "1px solid var(--bf-border)",
        borderRadius: "var(--bf-radius-md)",
        color: "var(--bf-text-1)",
        fontSize: 13, outline: "none",
        lineHeight: 1.5, resize: "vertical",
        ...(props.style ?? {}),
      }}
    />
  );
}

function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      style={{
        width: "100%", height: 40, padding: "0 12px",
        background: "var(--bf-bg-input)",
        border: "1px solid var(--bf-border)",
        borderRadius: "var(--bf-radius-md)",
        color: "var(--bf-text-1)",
        fontSize: 13, outline: "none",
        ...(props.style ?? {}),
      }}
    >
      {props.children}
    </select>
  );
}

function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={on}
      style={{
        width: 40, height: 22, position: "relative",
        background: on ? "var(--bf-primary)" : "var(--bf-text-4)",
        borderRadius: 999,
        transition: "background 200ms",
        flexShrink: 0,
      }}
    >
      <span style={{
        position: "absolute", top: 2, left: 2,
        width: 18, height: 18, background: "#fff",
        borderRadius: "50%",
        transform: on ? "translateX(18px)" : "translateX(0)",
        transition: "transform 200ms",
      }} />
    </button>
  );
}

function SettingRow({ title, desc, control }: { title: string; desc?: string; control: React.ReactNode }) {
  return (
    <div className="flex items-center gap-4" style={{ padding: "var(--bf-space-3) 0", borderBottom: "1px dashed var(--bf-divider)" }}>
      <div className="flex-1">
        <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--bf-text-1)", marginBottom: 2 }}>{title}</div>
        {desc && <div style={{ fontSize: 12, color: "var(--bf-text-3)", lineHeight: 1.5 }}>{desc}</div>}
      </div>
      {control}
    </div>
  );
}

function BasicSection({
  workspace,
  onSaved,
  onError,
}: {
  workspace: Workspace;
  onSaved: (w: Workspace) => void;
  onError: (msg: string) => void;
}) {
  const [name, setName] = useState(workspace.name);
  const [description, setDescription] = useState(workspace.description ?? "");
  const [status, setStatus] = useState<Workspace["status"]>(workspace.status);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setName(workspace.name);
    setDescription(workspace.description ?? "");
    setStatus(workspace.status);
  }, [workspace.id, workspace.name, workspace.description, workspace.status]);

  const dirty =
    name !== workspace.name ||
    description !== (workspace.description ?? "") ||
    status !== workspace.status;

  const handleSave = async () => {
    if (!dirty || saving) return;
    setSaving(true);
    try {
      const updated = await updateWorkspace(workspace.id, {
        name: name.trim(),
        description: description.trim() || null,
        status,
      } as any);
      onSaved(updated);
    } catch {
      onError("保存に失敗しました");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setName(workspace.name);
    setDescription(workspace.description ?? "");
    setStatus(workspace.status);
  };

  return (
    <SettingsCard title="基本情報" desc="プロジェクトの名前・概要・ステータス" icon={Info}>
      <FormGroup label="プロジェクト名">
        <Input value={name} onChange={(e) => setName(e.target.value)} />
      </FormGroup>
      <FormGroup label="概要">
        <Textarea
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="このワークスペースの目的・コンテキストを記入"
        />
      </FormGroup>
      <FormGroup label="ステータス">
        <Select value={status} onChange={(e) => setStatus(e.target.value as Workspace["status"])}>
          <option value="active">進行中 (active)</option>
          <option value="paused">一時停止 (paused)</option>
          <option value="archived">アーカイブ (archived)</option>
        </Select>
      </FormGroup>
      <div className="flex gap-2" style={{ marginTop: "var(--bf-space-4)" }}>
        <button
          onClick={handleSave}
          disabled={!dirty || saving}
          className="inline-flex items-center"
          style={{
            height: 34, padding: "0 14px",
            background: dirty && !saving ? "var(--bf-primary)" : "var(--bf-text-4)",
            color: "#fff", borderRadius: "var(--bf-radius-md)", fontSize: 13, fontWeight: 600,
            cursor: dirty && !saving ? "pointer" : "not-allowed",
          }}
        >
          {saving ? "保存中…" : "保存"}
        </button>
        <button
          onClick={handleReset}
          disabled={!dirty || saving}
          className="inline-flex items-center"
          style={{
            height: 34, padding: "0 14px", background: "transparent",
            color: dirty ? "var(--bf-text-2)" : "var(--bf-text-4)",
            borderRadius: "var(--bf-radius-md)", fontSize: 13, fontWeight: 600,
            cursor: dirty ? "pointer" : "not-allowed",
          }}
        >
          変更を破棄
        </button>
      </div>
    </SettingsCard>
  );
}

function PhaseControlSection({
  mode, setMode, parallel, setParallel, pmApproval, setPmApproval, reasonRequired, setReasonRequired,
}: {
  mode: "strict" | "guide" | "free"; setMode: (m: any) => void;
  parallel: boolean; setParallel: (b: boolean) => void;
  pmApproval: boolean; setPmApproval: (b: boolean) => void;
  reasonRequired: boolean; setReasonRequired: (b: boolean) => void;
}) {
  const cards = [
    { id: "strict", icon: Lock,      title: "厳格",        desc: "前提フェーズが完了しないと次に進めません。新人 PM や教育用に。" },
    { id: "guide",  icon: Navigation,title: "ガイド (推奨)", desc: "前提未完了は警告モーダル。理由入力で強制突破可能。通常はこれ。" },
    { id: "free",   icon: Zap,       title: "自由",        desc: "制限なし。表示のみ。経験者・小規模案件向け。" },
  ];
  return (
    <SettingsCard title="フェーズ制御モード" desc="DAG 順序を厳密に守るか、自由に飛ばせるかを設定" icon={GitBranch}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "var(--bf-space-3)", marginBottom: "var(--bf-space-5)" }}>
        {cards.map((c) => {
          const selected = mode === c.id;
          return (
            <button
              key={c.id}
              onClick={() => setMode(c.id as any)}
              className="text-left"
              style={{
                background: selected ? "var(--bf-primary-soft)" : "var(--bf-bg-soft)",
                border: `1.5px solid ${selected ? "var(--bf-primary)" : "var(--bf-border)"}`,
                borderRadius: "var(--bf-radius-md)",
                padding: "var(--bf-space-4)",
              }}
            >
              <div className="flex items-center gap-1.5" style={{ fontSize: 13, fontWeight: 700, color: "var(--bf-text-1)", marginBottom: 4 }}>
                <c.icon className="w-3.5 h-3.5" />
                {c.title}
              </div>
              <div style={{ fontSize: 11.5, color: "var(--bf-text-3)", lineHeight: 1.5 }}>
                {c.desc}
              </div>
            </button>
          );
        })}
      </div>
      <SettingRow
        title="並行進行を許可"
        desc="並行可能なフェーズ (アーキ + デザイン + API 等) を同時に進められる"
        control={<Toggle on={parallel} onClick={() => setParallel(!parallel)} />}
      />
      <SettingRow
        title="フェーズ完了に PM 承認を必須にする"
        desc="AI が STEP を全完了してもプロジェクトオーナーの承認なしでは次へ進めない"
        control={<Toggle on={pmApproval} onClick={() => setPmApproval(!pmApproval)} />}
      />
      <SettingRow
        title="強行突破時に理由入力を必須にする"
        desc="スキップしたフェーズの記録を残す"
        control={<Toggle on={reasonRequired} onClick={() => setReasonRequired(!reasonRequired)} />}
      />
    </SettingsCard>
  );
}

function PenpotSection({ clientEdit, setClientEdit }: { clientEdit: boolean; setClientEdit: (b: boolean) => void }) {
  return (
    <SettingsCard title="Penpot 連携" desc="デザイナー AI のモック作成キャンバス連携設定" icon={Palette}>
      <FormGroup label="Penpot Workspace" help="Penpot 側のワークスペース名と紐付け">
        <Input defaultValue="Build-Factory Designs" />
      </FormGroup>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--bf-space-4)" }}>
        <FormGroup label="Project ID"><Input defaultValue="prj_a1b2c3d4..." /></FormGroup>
        <FormGroup label="File ID"><Input defaultValue="fil_x9y8z7..." /></FormGroup>
      </div>
      <SettingRow
        title="クライアントにモック編集権限を付与"
        desc="通常はコメント権限のみ。チェックすると client ロールでも編集可能になる"
        control={<Toggle on={clientEdit} onClick={() => setClientEdit(!clientEdit)} />}
      />
    </SettingsCard>
  );
}

function AiModelSection() {
  return (
    <SettingsCard title="AI モデル設定" desc="各 AI 社員が使う LLM プロバイダ・モデルを指定" icon={Cpu}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--bf-space-4)" }}>
        <FormGroup label="秘書 AI">
          <Select defaultValue="opus-4-7">
            <option value="opus-4-7">Claude Opus 4.7 (1M)</option>
            <option value="sonnet-4-6">Claude Sonnet 4.6</option>
            <option value="haiku-4-5">Claude Haiku 4.5</option>
            <option value="gpt-4o">GPT-4o</option>
          </Select>
        </FormGroup>
        <FormGroup label="PM AI">
          <Select defaultValue="sonnet-4-6">
            <option value="sonnet-4-6">Claude Sonnet 4.6</option>
            <option value="opus-4-7">Claude Opus 4.7</option>
          </Select>
        </FormGroup>
        <FormGroup label="設計 AI">
          <Select defaultValue="opus-4-7">
            <option value="opus-4-7">Claude Opus 4.7 (1M)</option>
          </Select>
        </FormGroup>
        <FormGroup label="エンジニア AI (Claude Code 連携)">
          <Select defaultValue="claude-code">
            <option value="claude-code">Claude Code (MCP 経由)</option>
          </Select>
        </FormGroup>
      </div>
    </SettingsCard>
  );
}

/**
 * T-004-05: Owner 移譲 セクション
 *
 * AC:
 *   - UBIQUITOUS: 既存メンバーへの owner 移譲 UI を提供する
 *   - EVENT: 移譲 submit で current_owner → new_owner を atomic 切替
 *   - STATE: current user が owner でなければ移譲 UI を hide / disable
 *   - UNWANTED: target がメンバーでなければ backend 400 (target_not_member)
 */
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
  const eligibleTargets = members.filter(
    (m) => m.user_id !== CURRENT_USER_ID && m.role !== "owner",
  );

  const handleTransfer = async () => {
    if (!isOwner) return;
    if (!targetUserId) {
      onToast({ kind: "err", msg: "移譲先メンバーを選択してください" });
      return;
    }
    const target = members.find((m) => m.user_id === targetUserId);
    if (!confirm(`Owner 権限を ${target?.user_id} に移譲します。あなたの権限は ws_admin に変更されます。よろしいですか?`)) {
      return;
    }
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
    <SettingsCard title="メンバーシップ" desc="ワークスペースのオーナーシップ管理" icon={Users}>
      <div style={{ marginBottom: "var(--bf-space-5)" }}>
        <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--bf-text-2)", marginBottom: 8 }}>
          現在の Owner
        </div>
        <div className="flex items-center gap-2" style={{
          padding: "10px 14px",
          background: "var(--bf-primary-soft)",
          border: "1px solid var(--bf-primary-bg)",
          borderRadius: "var(--bf-radius-md)",
          fontSize: 13,
        }}>
          <Crown className="w-4 h-4" style={{ color: "var(--bf-primary)" }} />
          <span style={{ fontWeight: 600, color: "var(--bf-text-1)" }}>
            {loading ? "読み込み中…" : currentOwner?.user_id ?? "未割当"}
          </span>
          {isOwner && (
            <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--bf-primary)" }}>
              (あなた)
            </span>
          )}
        </div>
      </div>

      <div style={{ borderTop: "1px dashed var(--bf-divider)", paddingTop: "var(--bf-space-4)" }}>
        <div style={{ fontSize: 13.5, fontWeight: 700, color: "var(--bf-text-1)", marginBottom: 4 }}>
          Owner を移譲する
        </div>
        <div style={{ fontSize: 12, color: "var(--bf-text-3)", marginBottom: 12, lineHeight: 1.5 }}>
          {isOwner
            ? "別のメンバーを新しい Owner にします。あなたは自動的に ws_admin に降格します。"
            : "Owner のみがこの操作を実行できます。"}
        </div>

        {isOwner && (
          <div className="flex items-center gap-2">
            <Select
              value={targetUserId}
              onChange={(e) => setTargetUserId(e.target.value)}
              style={{ flex: 1 }}
            >
              <option value="">移譲先メンバーを選択…</option>
              {eligibleTargets.map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.user_id} ({m.role})
                </option>
              ))}
            </Select>
            <button
              onClick={handleTransfer}
              disabled={!targetUserId || transferring}
              className="inline-flex items-center gap-1.5"
              style={{
                height: 40, padding: "0 16px",
                background: targetUserId && !transferring ? "var(--bf-primary)" : "var(--bf-text-4)",
                color: "#fff", borderRadius: "var(--bf-radius-md)",
                fontSize: 13, fontWeight: 600, flexShrink: 0,
                cursor: targetUserId && !transferring ? "pointer" : "not-allowed",
              }}
            >
              <Crown className="w-3.5 h-3.5" />
              {transferring ? "移譲中…" : "移譲する"}
            </button>
          </div>
        )}
      </div>
    </SettingsCard>
  );
}


function DangerSection({ onArchive }: { onArchive: () => void }) {
  return (
    <SettingsCard title="危険ゾーン" desc="取り返しのつかない操作。実行前に十分にご確認ください。" icon={AlertTriangle} danger>
      <SettingRow
        title="プロジェクトをアーカイブ"
        desc="読み取り専用にして一覧から非表示にします。後から status を active に戻せば復元可能。"
        control={
          <button
            onClick={onArchive}
            className="inline-flex items-center"
            style={{
              height: 34, padding: "0 14px",
              background: "var(--bf-danger)", color: "#fff",
              borderRadius: "var(--bf-radius-md)", fontSize: 13, fontWeight: 600,
              cursor: "pointer",
            }}
          >
            アーカイブする
          </button>
        }
      />
    </SettingsCard>
  );
}
