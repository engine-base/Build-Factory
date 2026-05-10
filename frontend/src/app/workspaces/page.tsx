"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Account,
  Workspace,
  fetchAccounts,
  fetchWorkspacesByAccount,
  createWorkspace,
} from "@/lib/workspaces";
import { Plus, Folder, Users, Sparkles, ConstructionIcon, Building2Icon, UserIcon, PaletteIcon } from "lucide-react";

/**
 * Account ダッシュボード
 *  - account 一覧
 *  - 各 account 内の workspace 一覧（俯瞰）
 *  - 新規 workspace 作成
 */
export default function AccountDashboardPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [activeAccount, setActiveAccount] = useState<Account | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const accs = (await fetchAccounts()) ?? [];
        setAccounts(accs);
        if (accs.length > 0 && accs[0]) {
          setActiveAccount(accs[0]);
          const ws = (await fetchWorkspacesByAccount(accs[0].id)) ?? [];
          setWorkspaces(ws);
        }
      } catch (e) {
        console.error("[AccountDashboard] init failed", e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const switchAccount = async (a: Account) => {
    setActiveAccount(a);
    setLoading(true);
    setWorkspaces(await fetchWorkspacesByAccount(a.id));
    setLoading(false);
  };

  const handleCreate = async () => {
    if (!newName.trim() || !activeAccount) return;
    const ws = await createWorkspace({
      account_id: activeAccount.id,
      name: newName.trim(),
      description: newDesc.trim() || undefined,
    });
    setWorkspaces((prev) => [ws, ...prev]);
    setNewName("");
    setNewDesc("");
    setCreating(false);
  };

  return (
    <div className="min-h-full p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ConstructionIcon className="w-6 h-6" aria-label="construction" /> Build-Factory
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            開発フロー特化 AI 社員 OS
          </p>
        </div>
        <button
          onClick={() => setCreating(true)}
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          <Plus className="w-4 h-4" />
          新規 Workspace
        </button>
      </div>

      {/* Account 切替 */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-gray-500 uppercase tracking-wide">Account:</span>
        {accounts.map((a) => (
          <button
            key={a.id}
            onClick={() => switchAccount(a)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition ${
              activeAccount?.id === a.id
                ? "bg-blue-600 text-white"
                : "bg-gray-100 text-gray-700 hover:bg-gray-200"
            }`}
          >
            <span className="inline-flex items-center gap-1">
              {a.type === "company" ? <Building2Icon className="w-3 h-3" aria-label="company" /> : <UserIcon className="w-3 h-3" aria-label="individual" />}
              {a.name}
            </span>
            <span className="ml-1.5 opacity-70">·{a.plan}</span>
          </button>
        ))}
      </div>

      {/* 統計サマリ */}
      {activeAccount && (
        <div className="grid grid-cols-3 gap-3">
          <StatCard
            icon={<Folder className="w-4 h-4" />}
            label="Workspaces"
            value={workspaces.length}
          />
          <StatCard
            icon={<Sparkles className="w-4 h-4" />}
            label="Active"
            value={workspaces.filter((w) => w.status === "active").length}
          />
          <StatCard
            icon={<Users className="w-4 h-4" />}
            label="Plan"
            value={activeAccount.plan}
          />
        </div>
      )}

      {/* 新規作成モーダル */}
      {creating && (
        <div className="rounded-lg border bg-white p-4 space-y-3">
          <h3 className="font-semibold">新しい Workspace を作る</h3>
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="プロジェクト名 (例: B 社 SaaS MVP)"
            className="w-full rounded border px-3 py-2 text-sm"
            autoFocus
          />
          <textarea
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            placeholder="どんなプロジェクトか短く（任意）"
            className="w-full rounded border px-3 py-2 text-sm"
            rows={2}
          />
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => setCreating(false)}
              className="rounded px-3 py-1.5 text-sm hover:bg-gray-100"
            >
              キャンセル
            </button>
            <button
              onClick={handleCreate}
              disabled={!newName.trim()}
              className="rounded bg-blue-600 px-4 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              作成
            </button>
          </div>
        </div>
      )}

      {/* Workspace 一覧 */}
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500 mb-3">
          Workspaces
        </h2>
        {loading && <div className="text-gray-500 text-sm">読み込み中…</div>}
        {!loading && workspaces.length === 0 && (
          <div className="rounded-lg border border-dashed p-8 text-center text-gray-500">
            <Folder className="w-12 h-12 mx-auto opacity-30 mb-2" />
            <p>まだ workspace がありません</p>
            <button
              onClick={() => setCreating(true)}
              className="mt-3 text-blue-600 text-sm hover:underline"
            >
              最初の workspace を作成
            </button>
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {workspaces.map((w) => (
            <WorkspaceCard key={w.id} workspace={w} />
          ))}
        </div>
      </div>
    </div>
  );
}

function StatCard({
  icon, label, value,
}: { icon: React.ReactNode; label: string; value: string | number }) {
  return (
    <div className="rounded-lg border bg-white px-4 py-3">
      <div className="flex items-center gap-2 text-xs text-gray-500">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-xl font-bold">{value}</div>
    </div>
  );
}

function WorkspaceCard({ workspace: w }: { workspace: Workspace }) {
  return (
    <Link
      href={`/workspaces/${w.id}`}
      className="block rounded-lg border bg-white p-4 hover:shadow-md transition"
    >
      <div className="flex items-start justify-between">
        <h3 className="font-semibold">{w.name}</h3>
        <span
          className={`text-[10px] uppercase rounded-full px-2 py-0.5 ${
            w.status === "active"
              ? "bg-green-100 text-green-700"
              : w.status === "archived"
              ? "bg-gray-100 text-gray-500"
              : "bg-yellow-100 text-yellow-700"
          }`}
        >
          {w.status}
        </span>
      </div>
      {w.description && (
        <p className="mt-1.5 text-xs text-gray-600 line-clamp-2">{w.description}</p>
      )}
      <div className="mt-3 flex items-center gap-3 text-xs text-gray-500">
        {w.design_system_ref && (
          <span className="rounded bg-purple-50 text-purple-700 px-1.5 py-0.5 inline-flex items-center gap-1">
            <PaletteIcon className="w-3 h-3" aria-label="design system" /> {w.design_system_ref}
          </span>
        )}
        {w.member_role && (
          <span className="text-gray-500">role: {w.member_role}</span>
        )}
      </div>
    </Link>
  );
}
