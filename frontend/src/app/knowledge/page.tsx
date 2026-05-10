"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Search, FileText, RefreshCw, Folder, FolderOpen, ChevronRight, ChevronDown,
  FileEdit, Bot, MessageSquare, Database, Plus, X, Loader, Edit2, Trash2, Save,
  Sparkles, Filter, CheckIcon, BookmarkIcon, FolderIcon as FolderPathIcon,
} from "lucide-react";

const API = "http://localhost:8001";

type KnowledgeItem = {
  id: number;
  title: string;
  category: string;
  tags: string;
  skill_tags: string | null;
  summary: string;
  content: string;
  md_path: string;
  source: string;
  confidence: number;
  use_count: number;
};

type TreeNode = {
  name: string;
  children: Record<string, TreeNode>;
  items: KnowledgeItem[];
};

const SOURCE_BADGES: Record<string, { label: string; color: string }> = {
  obsidian:       { label: "Obsidian",   color: "#7E3AED" },
  approval:       { label: "承認",       color: "#16A34A" },
  task_curate:    { label: "タスク",     color: "#16A34A" },
  slack_manual:   { label: "Slack覚えて",color: "#4A154B" },
  slack_feedback: { label: "肯定FB",     color: "#2563EB" },
  document:       { label: "資料",       color: "#D97706" },
  manual:         { label: "手動",       color: "#6B7280" },
};

export default function KnowledgePage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<KnowledgeItem | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set(["root"]));
  const [showAdd, setShowAdd] = useState(false);
  const [showCleanup, setShowCleanup] = useState(false);

  const { data: tree } = useQuery<TreeNode>({
    queryKey: ["knowledge-tree"],
    queryFn: () => fetch(`${API}/api/knowledge/tree`).then(r => r.json()),
  });

  const sync = useMutation({
    mutationFn: () => fetch(`${API}/api/knowledge/sync-obsidian`, { method: "POST" }).then(r => r.json()),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["knowledge-tree"] }),
  });

  const toggle = (path: string) => {
    const ns = new Set(expanded);
    ns.has(path) ? ns.delete(path) : ns.add(path);
    setExpanded(ns);
  };

  const renderTree = (node: TreeNode, path: string, depth: number) => {
    const isOpen = expanded.has(path);
    const childKeys = Object.keys(node.children).sort();
    const hasContent = node.items.length > 0 || childKeys.length > 0;

    return (
      <div key={path}>
        {depth > 0 && (
          <button onClick={() => toggle(path)}
            className="w-full flex items-center gap-1.5 px-2 py-1 text-xs hover:bg-gray-50 rounded"
            style={{ paddingLeft: 8 + depth * 12 }}>
            {childKeys.length > 0 || node.items.length > 0
              ? (isOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />)
              : <span className="w-3" />}
            {isOpen
              ? <FolderOpen className="w-3.5 h-3.5" style={{ color: "var(--eb-primary)" }} />
              : <Folder className="w-3.5 h-3.5" style={{ color: "var(--eb-neutral)" }} />}
            <span className="font-medium" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{node.name}</span>
            <span className="text-[10px] opacity-60 ml-auto">
              {node.items.length + Object.values(node.children).reduce((s: number, c: any) => s + countItems(c), 0)}
            </span>
          </button>
        )}
        {(isOpen || depth === 0) && (
          <>
            {childKeys.map(k => renderTree(node.children[k], `${path}/${k}`, depth + 1))}
            {node.items.filter(item =>
              !search || item.title.toLowerCase().includes(search.toLowerCase()) ||
              item.content?.toLowerCase().includes(search.toLowerCase())
            ).map(item => (
              <button key={item.id} onClick={() => setSelected(item)}
                className="w-full flex items-center gap-1.5 py-1 text-xs hover:bg-gray-50 rounded"
                style={{
                  paddingLeft: 8 + (depth + 1) * 12,
                  background: selected?.id === item.id ? "var(--eb-primary-container)" : "transparent",
                }}>
                <FileText className="w-3 h-3 shrink-0" style={{ color: "var(--eb-neutral)" }} />
                <span className="truncate flex-1 text-left" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{item.title}</span>
              </button>
            ))}
          </>
        )}
      </div>
    );
  };

  const countItems = (n: TreeNode): number =>
    n.items.length + Object.values(n.children).reduce((s, c: any) => s + countItems(c), 0);

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "var(--eb-surface-variant)" }}>
      {/* 左ペイン: ツリー */}
      <div className="w-80 shrink-0 flex flex-col bg-white" style={{ borderRight: "1px solid var(--eb-border)" }}>
        <div className="p-3" style={{ borderBottom: "1px solid var(--eb-border)" }}>
          <div className="flex items-center justify-between mb-2">
            <h1 className="font-bold text-sm" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>ナレッジ</h1>
            <div className="flex gap-1">
              <button onClick={() => setShowAdd(true)} title="新規追加"
                className="p-1.5 rounded hover:bg-gray-100" style={{ color: "var(--eb-primary)" }}>
                <Plus className="w-3.5 h-3.5" />
              </button>
              <button onClick={() => setShowCleanup(true)} title="クリーンアップ"
                className="p-1.5 rounded hover:bg-gray-100">
                <Sparkles className="w-3.5 h-3.5" style={{ color: "var(--eb-neutral)" }} />
              </button>
              <button onClick={() => sync.mutate()} disabled={sync.isPending} title="Obsidian同期"
                className="p-1.5 rounded hover:bg-gray-100">
                <RefreshCw className={`w-3.5 h-3.5 ${sync.isPending ? "animate-spin" : ""}`}
                  style={{ color: "var(--eb-neutral)" }} />
              </button>
            </div>
          </div>
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3" style={{ color: "var(--eb-neutral)" }} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="検索..."
              className="w-full pl-7 pr-2 py-1.5 rounded text-xs"
              style={{ border: "1px solid var(--eb-border)", outline: "none", fontFamily: "var(--font-noto-sans-jp)" }} />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto py-2">
          {tree ? renderTree(tree, "root", 0) : <p className="text-xs px-3 py-4" style={{ color: "var(--eb-neutral)" }}>読み込み中...</p>}
        </div>
      </div>

      {/* 右ペイン: 詳細・編集 */}
      <div className="flex-1 overflow-y-auto p-6">
        {selected ? (
          <KnowledgeDetail
            item={selected}
            onUpdate={() => {
              qc.invalidateQueries({ queryKey: ["knowledge-tree"] });
            }}
            onDelete={() => {
              setSelected(null);
              qc.invalidateQueries({ queryKey: ["knowledge-tree"] });
            }}
          />
        ) : (
          <div className="h-full flex flex-col items-center justify-center">
            <FileText className="w-12 h-12 mb-3 opacity-30" />
            <p className="text-sm" style={{ color: "var(--eb-neutral)" }}>左のツリーから選択</p>
          </div>
        )}
      </div>

      {/* 新規追加モーダル */}
      {showAdd && <AddKnowledgeModal onClose={() => { setShowAdd(false); qc.invalidateQueries({ queryKey: ["knowledge-tree"] }); }} />}

      {/* クリーンアップモーダル */}
      {showCleanup && (
        <CleanupModal
          onClose={() => { setShowCleanup(false); qc.invalidateQueries({ queryKey: ["knowledge-tree"] }); }}
        />
      )}
    </div>
  );
}

// ── Cleanup Modal ──────────────────────────────────────────
function CleanupModal({ onClose }: { onClose: () => void }) {
  const [useCountLte, setUseCountLte] = useState(0);
  const [notUsedDays, setNotUsedDays] = useState<number | "">(30);
  const [olderDays, setOlderDays] = useState<number | "">("");
  const [source, setSource] = useState("");
  const [confirmedFilter, setConfirmedFilter] = useState<"any" | "0" | "1">("0");
  const [excludeObsidian, setExcludeObsidian] = useState(true);
  const [items, setItems] = useState<any[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const fetchPreview = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        use_count_lte: String(useCountLte),
        exclude_obsidian: String(excludeObsidian),
        limit: "500",
      });
      if (notUsedDays !== "") params.append("not_used_for_days", String(notUsedDays));
      if (olderDays !== "") params.append("older_than_days", String(olderDays));
      if (source) params.append("source", source);
      if (confirmedFilter !== "any") params.append("confirmed_by_user", confirmedFilter);

      const res = await fetch(`${API}/api/knowledge/cleanup/preview?${params}`);
      const data = await res.json();
      setItems(data.items || []);
      setSelectedIds(new Set((data.items || []).map((i: any) => i.id)));
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchPreview(); /* eslint-disable-next-line */ }, []);

  const toggleAll = () => {
    if (selectedIds.size === items.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(items.map(i => i.id)));
  };
  const toggleOne = (id: number) => {
    const ns = new Set(selectedIds);
    ns.has(id) ? ns.delete(id) : ns.add(id);
    setSelectedIds(ns);
  };

  const bulkDelete = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    if (!confirm(`選択した ${ids.length} 件のナレッジを削除します。よろしいですか？\nObsidian Vault 由来は削除されません。`)) return;
    setDeleting(true);
    try {
      const res = await fetch(`${API}/api/knowledge/cleanup/bulk-delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      const data = await res.json();
      alert(`${data.deleted}件削除しました。`);
      await fetchPreview();
    } finally { setDeleting(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="bg-white rounded-lg w-full max-w-5xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5" style={{ color: "var(--eb-primary)" }} />
            <h2 className="font-bold text-base" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
              ナレッジクリーンアップ
            </h2>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Filters */}
        <div className="p-4 border-b grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
          <label className="flex flex-col gap-1">
            <span className="font-medium" style={{ color: "var(--eb-neutral)" }}>利用回数（以下）</span>
            <input type="number" value={useCountLte} onChange={e => setUseCountLte(parseInt(e.target.value) || 0)}
              className="px-2 py-1.5 rounded border" min={0} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-medium" style={{ color: "var(--eb-neutral)" }}>最終更新から（日以上）</span>
            <input type="number" value={notUsedDays} onChange={e => setNotUsedDays(e.target.value === "" ? "" : parseInt(e.target.value))}
              className="px-2 py-1.5 rounded border" min={0} placeholder="制限なし" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-medium" style={{ color: "var(--eb-neutral)" }}>作成から（日以上）</span>
            <input type="number" value={olderDays} onChange={e => setOlderDays(e.target.value === "" ? "" : parseInt(e.target.value))}
              className="px-2 py-1.5 rounded border" min={0} placeholder="制限なし" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-medium" style={{ color: "var(--eb-neutral)" }}>ソース</span>
            <select value={source} onChange={e => setSource(e.target.value)}
              className="px-2 py-1.5 rounded border">
              <option value="">すべて</option>
              <option value="manual">手動</option>
              <option value="approval">承認</option>
              <option value="task_curate">タスク</option>
              <option value="slack_manual">Slack覚えて</option>
              <option value="slack_feedback">肯定FB</option>
              <option value="document">資料</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-medium" style={{ color: "var(--eb-neutral)" }}>確認状態</span>
            <select value={confirmedFilter} onChange={e => setConfirmedFilter(e.target.value as any)}
              className="px-2 py-1.5 rounded border">
              <option value="any">すべて</option>
              <option value="0">未確認のみ</option>
              <option value="1">確認済のみ</option>
            </select>
          </label>
          <label className="flex items-center gap-2 mt-5">
            <input type="checkbox" checked={excludeObsidian} onChange={e => setExcludeObsidian(e.target.checked)} />
            <span style={{ color: "var(--eb-neutral)" }}>Obsidian Vault由来は除外（推奨）</span>
          </label>
          <div className="col-span-2 md:col-span-3 flex justify-end">
            <button onClick={fetchPreview} disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-white text-xs font-medium"
              style={{ background: "var(--eb-primary)" }}>
              <Filter className="w-3.5 h-3.5" />
              {loading ? "読込中..." : "フィルタ適用"}
            </button>
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          <div className="px-4 py-2 border-b sticky top-0 bg-white flex items-center justify-between text-xs">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={items.length > 0 && selectedIds.size === items.length} onChange={toggleAll} />
              <span>{selectedIds.size}/{items.length} 件選択中</span>
            </label>
            <button onClick={bulkDelete} disabled={selectedIds.size === 0 || deleting}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-white text-xs font-medium disabled:opacity-40"
              style={{ background: "#dc2626" }}>
              <Trash2 className="w-3.5 h-3.5" />
              {deleting ? "削除中..." : `選択した${selectedIds.size}件を削除`}
            </button>
          </div>
          <table className="w-full text-xs">
            <thead className="bg-gray-50">
              <tr className="text-left" style={{ color: "var(--eb-neutral)" }}>
                <th className="px-3 py-2 w-8"></th>
                <th className="px-3 py-2">タイトル</th>
                <th className="px-3 py-2 w-20">ソース</th>
                <th className="px-3 py-2 w-12 text-right">利用</th>
                <th className="px-3 py-2 w-24">最終更新</th>
                <th className="px-3 py-2 w-24">作成日</th>
              </tr>
            </thead>
            <tbody>
              {items.map(it => (
                <tr key={it.id} className="border-t hover:bg-gray-50">
                  <td className="px-3 py-2">
                    <input type="checkbox" checked={selectedIds.has(it.id)} onChange={() => toggleOne(it.id)} />
                  </td>
                  <td className="px-3 py-2">
                    <div className="font-medium truncate max-w-md" title={it.title}>{it.title}</div>
                    {it.preview && <div className="text-[10px] opacity-60 truncate max-w-md">{it.preview}</div>}
                  </td>
                  <td className="px-3 py-2"><span className="px-1.5 py-0.5 rounded text-[10px] bg-gray-100">{it.source || "-"}</span></td>
                  <td className="px-3 py-2 text-right">{it.use_count ?? 0}</td>
                  <td className="px-3 py-2 text-[10px]" style={{ color: "var(--eb-neutral)" }}>{it.last_updated || "-"}</td>
                  <td className="px-3 py-2 text-[10px]" style={{ color: "var(--eb-neutral)" }}>{it.created_at?.slice(0, 10) || "-"}</td>
                </tr>
              ))}
              {!loading && items.length === 0 && (
                <tr><td colSpan={6} className="px-3 py-8 text-center text-xs" style={{ color: "var(--eb-neutral)" }}>
                  該当ナレッジなし
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function KnowledgeDetail({ item, onUpdate, onDelete }: {
  item: KnowledgeItem;
  onUpdate: () => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    title: item.title,
    content: item.content || item.summary || "",
    category: item.category || "",
    skill_tags: item.skill_tags || "",
    tags: item.tags || "",
  });
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  // selected が変わったらフォームを再初期化
  useEffect(() => {
    setForm({
      title: item.title,
      content: item.content || item.summary || "",
      category: item.category || "",
      skill_tags: item.skill_tags || "",
      tags: item.tags || "",
    });
    setEditing(false);
    setSaved(false);
  }, [item.id]);

  const save = async () => {
    setBusy(true);
    try {
      await fetch(`${API}/api/knowledge/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      setSaved(true);
      setEditing(false);
      onUpdate();
      setTimeout(() => setSaved(false), 2000);
    } finally { setBusy(false); }
  };

  const remove = async () => {
    if (!confirm(`「${item.title}」を削除しますか？\nObsidian Vault のファイルも削除されます。`)) return;
    setBusy(true);
    try {
      await fetch(`${API}/api/knowledge/${item.id}`, { method: "DELETE" });
      onDelete();
    } finally { setBusy(false); }
  };

  const conf = SOURCE_BADGES[item.source] ?? { label: item.source, color: "#6B7280" };

  return (
    <div className="max-w-3xl mx-auto">
      <div className="rounded-xl p-6 bg-white" style={{ border: "1px solid var(--eb-border)" }}>
        <div className="flex items-start justify-between mb-3">
          {editing ? (
            <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
              className="text-lg font-bold flex-1 px-2 py-1 rounded mr-2"
              style={{ border: "1px solid var(--eb-border)", outline: "none", fontFamily: "var(--font-noto-sans-jp)" }} />
          ) : (
            <h2 className="text-lg font-bold" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{item.title}</h2>
          )}
          <div className="flex items-center gap-1">
            <span className="px-2 py-0.5 rounded text-[10px] font-bold"
              style={{ background: conf.color + "22", color: conf.color, fontFamily: "var(--font-inter)" }}>
              {conf.label}
            </span>
            {editing ? (
              <>
                <button onClick={save} disabled={busy}
                  className="ml-2 flex items-center gap-1 px-3 py-1 rounded text-xs font-semibold text-white"
                  style={{ background: "var(--eb-primary)" }}>
                  {busy ? <Loader className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                  保存
                </button>
                <button onClick={() => setEditing(false)}
                  className="px-3 py-1 rounded text-xs"
                  style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)" }}>
                  キャンセル
                </button>
              </>
            ) : (
              <>
                <button onClick={() => setEditing(true)} title="編集"
                  className="ml-2 p-1.5 rounded hover:bg-gray-100">
                  <Edit2 className="w-3.5 h-3.5" style={{ color: "var(--eb-neutral)" }} />
                </button>
                <button onClick={remove} disabled={busy} title="削除"
                  className="p-1.5 rounded hover:bg-red-50">
                  <Trash2 className="w-3.5 h-3.5" style={{ color: "var(--eb-error)" }} />
                </button>
              </>
            )}
          </div>
        </div>

        {saved && (
          <p className="text-xs mb-3 px-2 py-1 rounded inline-flex items-center gap-1"
            style={{ background: "#DCFCE7", color: "#16A34A" }}>
            <CheckIcon className="w-3 h-3" aria-label="saved" /> 保存しました
          </p>
        )}

        {/* メタ情報 */}
        <div className="flex flex-wrap gap-1.5 mb-3">
          {editing ? (
            <>
              <input value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                placeholder="カテゴリ"
                className="text-xs px-2 py-0.5 rounded"
                style={{ border: "1px solid var(--eb-border)", outline: "none" }} />
              <input value={form.skill_tags} onChange={e => setForm(f => ({ ...f, skill_tags: e.target.value }))}
                placeholder="skill_tags (カンマ区切り)"
                className="text-xs px-2 py-0.5 rounded"
                style={{ border: "1px solid var(--eb-border)", outline: "none" }} />
              <input value={form.tags} onChange={e => setForm(f => ({ ...f, tags: e.target.value }))}
                placeholder="tags (カンマ区切り)"
                className="text-xs px-2 py-0.5 rounded"
                style={{ border: "1px solid var(--eb-border)", outline: "none" }} />
            </>
          ) : (
            <>
              {item.category && (
                <span className="text-xs px-2 py-0.5 rounded"
                  style={{ background: "var(--eb-primary-container)", color: "var(--eb-on-primary-container)" }}>
                  {item.category}
                </span>
              )}
              {item.skill_tags && (
                <span className="text-xs px-2 py-0.5 rounded inline-flex items-center gap-1"
                  style={{ background: "#FEF3C7", color: "#92400E" }}>
                  <BookmarkIcon className="w-3 h-3" aria-label="skill tags" /> {item.skill_tags}
                </span>
              )}
              {item.tags && (
                <span className="text-xs px-2 py-0.5 rounded"
                  style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)" }}>
                  {item.tags}
                </span>
              )}
              <span className="text-xs px-2 py-0.5 rounded"
                style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)" }}>
                使用 {item.use_count}回
              </span>
            </>
          )}
        </div>

        {item.md_path && (
          <p className="text-[11px] mb-3 inline-flex items-center gap-1" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
            <FolderPathIcon className="w-3 h-3" aria-label="folder" /> {item.md_path?.replace(/^.*Obsidian\//, "")}
          </p>
        )}

        {editing ? (
          <textarea value={form.content} onChange={e => setForm(f => ({ ...f, content: e.target.value }))}
            rows={20}
            className="w-full p-3 rounded text-sm resize-none"
            style={{ border: "1px solid var(--eb-border)", outline: "none",
                     fontFamily: "var(--font-noto-sans-jp)", lineHeight: 1.6 }} />
        ) : (
          <div className="text-sm leading-relaxed whitespace-pre-wrap"
            style={{ fontFamily: "var(--font-noto-sans-jp)", color: "#374151" }}>
            {item.content || item.summary}
          </div>
        )}
      </div>
    </div>
  );
}

function AddKnowledgeModal({ onClose }: { onClose: () => void }) {
  const [content, setContent] = useState("");
  const [memo, setMemo] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!content.trim()) return;
    setBusy(true);
    try {
      await fetch(`${API}/api/knowledge-actions/curate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content,
          masato_memo: memo || null,
          source: "manual",
          full_content: !memo,  // メモがあれば部分抽出
        }),
      });
      onClose();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: "rgba(0,0,0,0.4)" }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white rounded-xl p-6 w-full max-w-2xl mx-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-bold" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>ナレッジを手動追加</h2>
          <button onClick={onClose} className="p-1 hover:opacity-70"><X className="w-4 h-4" /></button>
        </div>
        <textarea value={content} onChange={e => setContent(e.target.value)}
          placeholder="ナレッジ内容..."
          rows={6} className="w-full p-3 rounded text-sm mb-2 resize-none"
          style={{ border: "1px solid var(--eb-border)", outline: "none", fontFamily: "var(--font-noto-sans-jp)" }} />
        <input value={memo} onChange={e => setMemo(e.target.value)}
          placeholder="どの部分が重要か（任意・指定すると秘書が抽出）"
          className="w-full px-3 py-2 rounded text-xs mb-3"
          style={{ border: "1px solid var(--eb-border)", outline: "none", fontFamily: "var(--font-noto-sans-jp)" }} />
        <div className="flex justify-end gap-2">
          <button onClick={onClose}
            className="px-4 py-2 rounded text-xs font-semibold"
            style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
            キャンセル
          </button>
          <button onClick={submit} disabled={busy || !content.trim()}
            className="px-4 py-2 rounded text-xs font-semibold text-white disabled:opacity-50"
            style={{ background: "var(--eb-primary)", fontFamily: "var(--font-inter)" }}>
            {busy ? "整理中..." : "秘書に整理してもらう"}
          </button>
        </div>
      </div>
    </div>
  );
}
