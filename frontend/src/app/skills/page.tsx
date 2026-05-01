"use client";

import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Search, Plus, Edit2, Play, ChevronDown, ChevronUp, Tag, Save, X, Trash2 } from "lucide-react";

const API = "http://localhost:8001";

type Skill = {
  id: number;
  skill_name: string;
  display_name: string;
  description: string;
  category: string;
  tags: string;
  is_active: number;
  updated_at: string;
  content?: string;
};

type Category = { category: string; count: number };

const CATEGORY_LABEL: Record<string, string> = {
  finance:   "財務・経理",
  sales:     "営業・集客",
  marketing: "マーケティング",
  content:   "Web・コンテンツ",
  cs:        "顧客・CS",
  hr:        "人事・採用",
  admin:     "総務・法務",
  strategy:  "経営戦略",
  design:    "設計",
  tech:      "開発・技術",
  ops:       "品質・運用",
  project:   "プロジェクト",
  analytics: "分析・調査",
  knowledge: "情報・ナレッジ",
  general:   "その他",
};

export default function SkillsPage() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);
  const [selected, setSelected] = useState<Skill | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState("");
  const [editMeta, setEditMeta] = useState({ display_name: "", description: "", category: "", tags: "" });
  const [showNew, setShowNew] = useState(false);
  const [newSkill, setNewSkill] = useState({ skill_name: "", display_name: "", category: "general", tags: "", content: "" });
  const [runInput, setRunInput] = useState("");
  const [runResult, setRunResult] = useState("");
  const [showRun, setShowRun] = useState(false);

  const { data: skills = [] } = useQuery<Skill[]>({
    queryKey: ["skills", categoryFilter, search],
    queryFn: () => {
      const params = new URLSearchParams();
      if (categoryFilter) params.set("category", categoryFilter);
      if (search) params.set("search", search);
      return fetch(`${API}/api/skills?${params}`).then(r => r.json());
    },
  });

  const { data: categories = [] } = useQuery<Category[]>({
    queryKey: ["skill-categories"],
    queryFn: () => fetch(`${API}/api/skills/categories`).then(r => r.json()),
  });

  const loadDetail = useMutation({
    mutationFn: (name: string) => fetch(`${API}/api/skills/${name}`).then(r => r.json()),
    onSuccess: (data: Skill) => {
      setSelected(data);
      setEditContent(data.content || "");
      setEditMeta({ display_name: data.display_name, description: data.description || "", category: data.category, tags: data.tags || "" });
      setIsEditing(false);
      setShowRun(false);
      setRunResult("");
    },
  });

  const saveSkill = useMutation({
    mutationFn: () => fetch(`${API}/api/skills/${selected!.skill_name}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: editContent, ...editMeta }),
    }).then(r => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["skills"] });
      setIsEditing(false);
      setSelected(s => s ? { ...s, content: editContent, ...editMeta } : s);
    },
  });

  const createSkill = useMutation({
    mutationFn: () => fetch(`${API}/api/skills`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newSkill),
    }).then(r => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["skills"] });
      qc.invalidateQueries({ queryKey: ["skill-categories"] });
      setShowNew(false);
      setNewSkill({ skill_name: "", display_name: "", category: "general", tags: "", content: "" });
    },
  });

  const deleteSkill = useMutation({
    mutationFn: (name: string) => fetch(`${API}/api/skills/${name}`, { method: "DELETE" }).then(r => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["skills"] });
      setSelected(null);
    },
  });

  const runSkill = useMutation({
    mutationFn: () => fetch(`${API}/api/skills/${selected!.skill_name}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input: runInput }),
    }).then(r => r.json()),
    onSuccess: (data) => setRunResult(data.result || ""),
  });

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: "var(--eb-surface-variant)" }}>
      {/* 左ペイン: 一覧 */}
      <div className="w-72 shrink-0 flex flex-col bg-white" style={{ borderRight: "1px solid var(--eb-border)" }}>
        {/* ヘッダー */}
        <div className="p-4" style={{ borderBottom: "1px solid var(--eb-border)" }}>
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-base font-bold" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>スキル管理</h1>
            <button onClick={() => setShowNew(true)}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs font-semibold text-white"
              style={{ background: "var(--eb-primary)", fontFamily: "var(--font-inter)" }}>
              <Plus className="w-3 h-3" /> 新規
            </button>
          </div>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5" style={{ color: "var(--eb-neutral)" }} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="スキルを検索..."
              className="w-full pl-8 pr-3 py-1.5 rounded text-xs"
              style={{ border: "1px solid var(--eb-border)", fontFamily: "var(--font-inter)", outline: "none" }} />
          </div>
        </div>

        {/* カテゴリフィルタ */}
        <div className="px-3 py-2 flex flex-wrap gap-1" style={{ borderBottom: "1px solid var(--eb-border)" }}>
          <button onClick={() => setCategoryFilter(null)}
            className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
            style={{ background: !categoryFilter ? "var(--eb-primary)" : "var(--eb-surface-variant)", color: !categoryFilter ? "#fff" : "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
            すべて ({skills.length})
          </button>
          {categories.map(c => (
            <button key={c.category} onClick={() => setCategoryFilter(c.category === categoryFilter ? null : c.category)}
              className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
              style={{ background: categoryFilter === c.category ? "var(--eb-primary)" : "var(--eb-surface-variant)", color: categoryFilter === c.category ? "#fff" : "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
              {CATEGORY_LABEL[c.category] ?? c.category} ({c.count})
            </button>
          ))}
        </div>

        {/* スキルリスト */}
        <div className="flex-1 overflow-y-auto">
          {skills.map(skill => (
            <button key={skill.skill_name}
              onClick={() => loadDetail.mutate(skill.skill_name)}
              className="w-full text-left px-4 py-3 transition-colors"
              style={{
                background: selected?.skill_name === skill.skill_name ? "var(--eb-primary-container)" : "transparent",
                borderBottom: "1px solid var(--eb-border)",
                borderLeft: selected?.skill_name === skill.skill_name ? "3px solid var(--eb-primary)" : "3px solid transparent",
              }}>
              <p className="text-xs font-semibold truncate" style={{ fontFamily: "var(--font-inter)" }}>{skill.display_name || skill.skill_name}</p>
              <p className="text-[10px] truncate mt-0.5" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                {skill.description?.slice(0, 60) || skill.skill_name}
              </p>
              <div className="flex items-center gap-1 mt-1">
                <span className="text-[9px] px-1.5 py-0.5 rounded"
                  style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                  {CATEGORY_LABEL[skill.category] ?? skill.category}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* 右ペイン: 詳細・編集 */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {selected ? (
          <>
            {/* ツールバー */}
            <div className="flex items-center justify-between px-6 py-3 bg-white" style={{ borderBottom: "1px solid var(--eb-border)" }}>
              <div>
                <h2 className="font-bold text-sm" style={{ fontFamily: "var(--font-inter)" }}>{selected.display_name || selected.skill_name}</h2>
                <p className="text-[10px]" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>{selected.skill_name}</p>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => setShowRun(!showRun)}
                  className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-semibold"
                  style={{ background: "var(--eb-tertiary-container)", color: "var(--eb-on-tertiary-container)", fontFamily: "var(--font-inter)" }}>
                  <Play className="w-3 h-3" /> テスト実行
                </button>
                {isEditing ? (
                  <>
                    <button onClick={() => setIsEditing(false)}
                      className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-semibold"
                      style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                      <X className="w-3 h-3" /> キャンセル
                    </button>
                    <button onClick={() => saveSkill.mutate()} disabled={saveSkill.isPending}
                      className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-semibold text-white"
                      style={{ background: "var(--eb-primary)", fontFamily: "var(--font-inter)" }}>
                      <Save className="w-3 h-3" /> {saveSkill.isPending ? "保存中..." : "保存"}
                    </button>
                  </>
                ) : (
                  <>
                    <button onClick={() => setIsEditing(true)}
                      className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-semibold"
                      style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                      <Edit2 className="w-3 h-3" /> 編集
                    </button>
                    <button onClick={() => { if (confirm(`「${selected.skill_name}」を削除しますか？`)) deleteSkill.mutate(selected.skill_name); }}
                      className="p-1.5 rounded transition-opacity hover:opacity-70"
                      style={{ color: "var(--eb-error)" }}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* テスト実行パネル */}
            {showRun && (
              <div className="px-6 py-4 bg-white" style={{ borderBottom: "1px solid var(--eb-border)" }}>
                <div className="flex gap-2 mb-2">
                  <input value={runInput} onChange={e => setRunInput(e.target.value)}
                    placeholder="スキルへの入力テキスト..."
                    className="flex-1 px-3 py-2 rounded text-xs"
                    style={{ border: "1px solid var(--eb-border)", fontFamily: "var(--font-noto-sans-jp)", outline: "none" }} />
                  <button onClick={() => runSkill.mutate()} disabled={runSkill.isPending || !runInput.trim()}
                    className="px-3 py-2 rounded text-xs font-semibold text-white disabled:opacity-50"
                    style={{ background: "var(--eb-tertiary)", fontFamily: "var(--font-inter)" }}>
                    {runSkill.isPending ? "実行中..." : "実行"}
                  </button>
                </div>
                {runResult && (
                  <pre className="text-[11px] p-3 rounded overflow-auto max-h-40 whitespace-pre-wrap"
                    style={{ background: "var(--eb-surface-variant)", fontFamily: "var(--font-inter)", color: "#374151" }}>
                    {runResult}
                  </pre>
                )}
              </div>
            )}

            {/* メタデータ編集 or 表示 */}
            {isEditing && (
              <div className="px-6 py-4 bg-white" style={{ borderBottom: "1px solid var(--eb-border)" }}>
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { key: "display_name", label: "表示名" },
                    { key: "category", label: "カテゴリ" },
                    { key: "tags", label: "タグ" },
                    { key: "description", label: "説明" },
                  ].map(({ key, label }) => (
                    <div key={key} className={key === "description" ? "col-span-2" : ""}>
                      <label className="block text-[10px] font-semibold mb-1" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>{label}</label>
                      <input value={(editMeta as any)[key]} onChange={e => setEditMeta(m => ({ ...m, [key]: e.target.value }))}
                        className="w-full px-2 py-1.5 rounded text-xs"
                        style={{ border: "1px solid var(--eb-border)", fontFamily: "var(--font-inter)", outline: "none" }} />
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* SKILL.md 表示・編集 */}
            <div className="flex-1 overflow-hidden flex flex-col">
              {isEditing ? (
                <textarea
                  value={editContent}
                  onChange={e => setEditContent(e.target.value)}
                  className="flex-1 p-6 text-xs resize-none focus:outline-none"
                  style={{ fontFamily: "var(--font-inter)", lineHeight: 1.6, color: "#1f2937", background: "#fff" }}
                />
              ) : (
                <pre className="flex-1 overflow-auto p-6 text-xs whitespace-pre-wrap"
                  style={{ fontFamily: "var(--font-inter)", lineHeight: 1.7, color: "#1f2937", background: "#fff" }}>
                  {selected.content}
                </pre>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-3"
                style={{ background: "var(--eb-primary-container)" }}>
                <Tag className="w-6 h-6" style={{ color: "var(--eb-primary)" }} />
              </div>
              <p className="text-sm font-medium mb-1" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>スキルを選択してください</p>
              <p className="text-xs" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-noto-sans-jp)" }}>
                左のリストからスキルを選ぶか、新規作成してください
              </p>
            </div>
          </div>
        )}
      </div>

      {/* 新規作成モーダル */}
      {showNew && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: "rgba(0,0,0,0.4)" }}
          onClick={e => { if (e.target === e.currentTarget) setShowNew(false); }}>
          <div className="bg-white rounded-xl p-6 w-full max-w-2xl mx-4" style={{ boxShadow: "0 8px 32px rgba(0,0,0,0.16)" }}>
            <h2 className="font-bold text-base mb-4" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>新しいスキルを作成</h2>
            <div className="grid grid-cols-2 gap-3 mb-3">
              {[
                { key: "skill_name", label: "スキル名 (英数字・ハイフン)", placeholder: "例: my-skill" },
                { key: "display_name", label: "表示名", placeholder: "例: 営業フォローアップ" },
                { key: "category", label: "カテゴリ", placeholder: "sales / finance / marketing ..." },
                { key: "tags", label: "タグ", placeholder: "#営業, #メール" },
              ].map(({ key, label, placeholder }) => (
                <div key={key}>
                  <label className="block text-[10px] font-semibold mb-1" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>{label}</label>
                  <input value={(newSkill as any)[key]} onChange={e => setNewSkill(s => ({ ...s, [key]: e.target.value }))}
                    placeholder={placeholder}
                    className="w-full px-2 py-1.5 rounded text-xs"
                    style={{ border: "1px solid var(--eb-border)", fontFamily: "var(--font-inter)", outline: "none" }} />
                </div>
              ))}
            </div>
            <div className="mb-4">
              <label className="block text-[10px] font-semibold mb-1" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>SKILL.md 本文</label>
              <textarea value={newSkill.content} onChange={e => setNewSkill(s => ({ ...s, content: e.target.value }))}
                placeholder="# スキル名&#10;&#10;## ロール定義&#10;&#10;あなたは..."
                rows={8}
                className="w-full px-3 py-2 rounded text-xs resize-none"
                style={{ border: "1px solid var(--eb-border)", fontFamily: "var(--font-inter)", outline: "none", lineHeight: 1.6 }} />
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowNew(false)}
                className="px-4 py-2 rounded text-xs font-semibold"
                style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                キャンセル
              </button>
              <button onClick={() => createSkill.mutate()}
                disabled={!newSkill.skill_name || !newSkill.content || createSkill.isPending}
                className="px-4 py-2 rounded text-xs font-semibold text-white disabled:opacity-50"
                style={{ background: "var(--eb-primary)", fontFamily: "var(--font-inter)" }}>
                {createSkill.isPending ? "作成中..." : "作成"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
