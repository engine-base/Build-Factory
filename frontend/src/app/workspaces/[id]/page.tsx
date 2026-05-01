"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  Workspace,
  WorkspaceMember,
  fetchWorkspace,
  fetchMembers,
  updateWorkspace,
} from "@/lib/workspaces";
import { ArrowLeft, Settings, Palette, ListTodo, MessageSquare, Users, Package, Eye } from "lucide-react";

type Tab = "overview" | "design" | "tasks" | "chat" | "artifacts" | "members";

/**
 * Workspace ダッシュボード（プロジェクト個別）
 * - タブ: 概要 / Design / タスク / チャット / Artifacts / メンバー
 */
export default function WorkspaceDetailPage() {
  const params = useParams();
  const id = Number(params?.id);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    (async () => {
      setLoading(true);
      const [w, ms] = await Promise.all([fetchWorkspace(id), fetchMembers(id)]);
      setWorkspace(w);
      setMembers(ms);
      setLoading(false);
    })();
  }, [id]);

  if (loading) {
    return <div className="p-6 text-gray-500">読み込み中…</div>;
  }
  if (!workspace) {
    return <div className="p-6 text-red-500">workspace が見つかりません</div>;
  }

  return (
    <div className="min-h-full">
      {/* ヘッダ */}
      <div className="border-b bg-white">
        <div className="max-w-6xl mx-auto px-6 py-4">
          <div className="flex items-center gap-3 mb-2">
            <Link
              href="/workspaces"
              className="text-gray-500 hover:text-gray-700"
              title="Account ダッシュボードへ"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <span className="text-xs text-gray-500">Build-Factory / Workspace #{workspace.id}</span>
          </div>
          <h1 className="text-2xl font-bold">{workspace.name}</h1>
          {workspace.description && (
            <p className="text-sm text-gray-600 mt-1">{workspace.description}</p>
          )}
        </div>

        {/* タブナビ */}
        <div className="max-w-6xl mx-auto px-6 flex gap-1 -mb-px overflow-x-auto">
          <TabButton tab="overview" current={tab} onClick={setTab} icon={<Eye className="w-3.5 h-3.5" />}>
            概要
          </TabButton>
          <TabButton tab="design" current={tab} onClick={setTab} icon={<Palette className="w-3.5 h-3.5" />}>
            Design
          </TabButton>
          <TabButton tab="tasks" current={tab} onClick={setTab} icon={<ListTodo className="w-3.5 h-3.5" />}>
            タスク
          </TabButton>
          <TabButton tab="chat" current={tab} onClick={setTab} icon={<MessageSquare className="w-3.5 h-3.5" />}>
            チャット
          </TabButton>
          <TabButton tab="artifacts" current={tab} onClick={setTab} icon={<Package className="w-3.5 h-3.5" />}>
            Artifacts
          </TabButton>
          <TabButton tab="members" current={tab} onClick={setTab} icon={<Users className="w-3.5 h-3.5" />}>
            メンバー ({members.length})
          </TabButton>
        </div>
      </div>

      {/* タブ内容 */}
      <div className="max-w-6xl mx-auto p-6">
        {tab === "overview" && <OverviewTab workspace={workspace} memberCount={members.length} />}
        {tab === "design" && <DesignTab workspace={workspace} onUpdate={setWorkspace} />}
        {tab === "tasks" && <TasksTab workspace={workspace} />}
        {tab === "chat" && <ChatTab workspace={workspace} />}
        {tab === "artifacts" && <ArtifactsTab workspace={workspace} />}
        {tab === "members" && <MembersTab workspace={workspace} members={members} setMembers={setMembers} />}
      </div>
    </div>
  );
}

function TabButton({
  tab, current, onClick, icon, children,
}: {
  tab: Tab;
  current: Tab;
  onClick: (t: Tab) => void;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={() => onClick(tab)}
      className={`flex items-center gap-1.5 px-3 py-2 text-sm border-b-2 transition ${
        current === tab
          ? "border-blue-600 text-blue-600 font-medium"
          : "border-transparent text-gray-600 hover:text-gray-900"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}

function OverviewTab({ workspace, memberCount }: { workspace: Workspace; memberCount: number }) {
  return (
    <div className="space-y-6">
      <Card title="メタ情報">
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <Field label="ID" value={String(workspace.id)} />
          <Field label="ステータス" value={workspace.status} />
          <Field label="作成日" value={new Date(workspace.created_at).toLocaleString("ja-JP")} />
          <Field label="更新日" value={new Date(workspace.updated_at).toLocaleString("ja-JP")} />
          <Field label="メンバー数" value={String(memberCount)} />
          <Field label="design_system_ref" value={workspace.design_system_ref || "未設定"} />
        </dl>
      </Card>

      <Card title="開発フローの状況（実装中）">
        <div className="text-sm text-gray-600 space-y-2">
          <Step title="Phase A: 設計確定" detail="hearing → requirements → architecture → tech-stack → api-design" />
          <Step title="Phase A: デザイン確定" detail="brand-voice → design-md → frontend-design → ui-mockup" />
          <Step title="Phase B: 完成モック" detail="Onlook で全画面まとめ生成 + 反復編集" />
          <Step title="Phase C: タスク分解" detail="feature-decomposition → task-decomposition" />
          <Step title="Phase D: 実装" detail="Claude Code 3 分離 (Planner / Generator / Evaluator)" />
        </div>
      </Card>
    </div>
  );
}

function DesignTab({
  workspace, onUpdate,
}: {
  workspace: Workspace;
  onUpdate: (w: Workspace) => void;
}) {
  const [refValue, setRefValue] = useState(workspace.design_system_ref || "");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    const updated = await updateWorkspace(workspace.id, {
      design_system_ref: refValue || null as unknown as string,
    });
    onUpdate(updated);
    setSaving(false);
  };

  return (
    <div className="space-y-4">
      <Card title="Design System 参照">
        <p className="text-xs text-gray-600 mb-3">
          Open Design 取込みの 129 デザインシステムから 1 つ選んで設定。
          Onlook 起動時に AI への prompt として渡される。
        </p>
        <div className="flex items-center gap-2">
          <input
            list="design-system-list"
            value={refValue}
            onChange={(e) => setRefValue(e.target.value)}
            placeholder="例: linear / stripe / vercel / airbnb / notion ..."
            className="flex-1 rounded border px-3 py-2 text-sm"
          />
          <datalist id="design-system-list">
            {COMMON_DESIGN_SYSTEMS.map((d) => (
              <option key={d} value={d} />
            ))}
          </datalist>
          <button
            onClick={save}
            disabled={saving}
            className="rounded bg-blue-600 text-white px-4 py-2 text-sm hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </Card>

      <Card title="Phase A 設計スキル（手動連鎖・実装中）">
        <p className="text-xs text-gray-500">
          brand-voice → design-md → frontend-design → ui-mockup を順に発火する自動連鎖は
          Iteration 6 で実装予定。現在はチャットから個別に呼び出す形。
        </p>
      </Card>

      <Card title="Onlook 連携（実装中）">
        <p className="text-xs text-gray-500">
          Iteration 7 で Onlook self-host を起動し、ここから「[ Onlook で開く ]」が押せるようにする。
        </p>
      </Card>
    </div>
  );
}

function TasksTab({ workspace }: { workspace: Workspace }) {
  return (
    <Card title="タスク（実装中）">
      <p className="text-xs text-gray-500">
        feature-decomposition / task-decomposition の出力をここに表示します。
        Claude Code への引き渡しは MCP `bf_get_next_task` 経由。
      </p>
    </Card>
  );
}

function ChatTab({ workspace }: { workspace: Workspace }) {
  return (
    <Card title="AI 社員チャット">
      <Link
        href="/secretary"
        className="inline-flex items-center gap-2 rounded bg-blue-600 text-white px-4 py-2 text-sm hover:bg-blue-700"
      >
        🎀 PM 秘書（ナナ）と話す
      </Link>
      <p className="text-xs text-gray-500 mt-3">
        他の AI 社員（アーキテクト / エンジニア / レビュー / QA / DevOps / Docs）への切替はチャット画面で。
      </p>
    </Card>
  );
}

function ArtifactsTab({ workspace }: { workspace: Workspace }) {
  return (
    <Card title="Artifacts">
      <Link
        href="/artifacts"
        className="inline-flex items-center gap-2 rounded bg-blue-600 text-white px-4 py-2 text-sm hover:bg-blue-700"
      >
        📦 Artifacts ライブラリ
      </Link>
      <p className="text-xs text-gray-500 mt-3">
        この workspace で生成された artifact のみ後ほどフィルタ表示する予定。
      </p>
    </Card>
  );
}

function MembersTab({
  workspace, members, setMembers,
}: {
  workspace: Workspace;
  members: WorkspaceMember[];
  setMembers: (ms: WorkspaceMember[]) => void;
}) {
  const ROLES = ["admin", "contributor", "viewer", "client"];
  return (
    <Card title="Workspace メンバー">
      <table className="w-full text-sm">
        <thead className="text-xs text-gray-500 uppercase">
          <tr>
            <th className="text-left py-2">User ID</th>
            <th className="text-left">Role</th>
            <th className="text-left">招待者</th>
            <th className="text-left">追加日</th>
          </tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.id} className="border-t">
              <td className="py-2">{m.user_id}</td>
              <td>
                <span className={`rounded px-2 py-0.5 text-xs ${
                  m.role === "admin" ? "bg-red-100 text-red-700" :
                  m.role === "contributor" ? "bg-blue-100 text-blue-700" :
                  m.role === "client" ? "bg-purple-100 text-purple-700" :
                  "bg-gray-100 text-gray-700"
                }`}>
                  {m.role}
                </span>
              </td>
              <td className="text-gray-600">{m.invited_by || "-"}</td>
              <td className="text-gray-500 text-xs">{new Date(m.created_at).toLocaleDateString("ja-JP")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-gray-500 mt-3">
        メンバー追加・招待発行は API で可能（UI は Iteration 後半で）。
      </p>
    </Card>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border bg-white p-5">
      <h3 className="text-sm font-semibold mb-3">{title}</h3>
      {children}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-gray-500 uppercase">{label}</dt>
      <dd className="text-sm mt-0.5">{value}</dd>
    </div>
  );
}

function Step({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded border-l-4 border-blue-200 pl-3 py-1.5">
      <div className="font-medium">{title}</div>
      <div className="text-xs text-gray-600">{detail}</div>
    </div>
  );
}

const COMMON_DESIGN_SYSTEMS = [
  "linear", "stripe", "vercel", "airbnb", "notion", "apple", "anthropic",
  "spotify", "uber", "github", "shopify", "figma", "discord", "slack",
];
