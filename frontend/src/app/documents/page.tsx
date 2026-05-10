"use client";

import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload, FileText, Loader, FolderOpen, Tag, FolderIcon as FolderPathIcon, FileTextIcon } from "lucide-react";

const API = "http://localhost:8001";

type Doc = {
  id: number;
  title: string;
  category: string;
  skill_tags: string | null;
  md_path: string;
  summary: string;
  use_count: number;
  created_at: string;
};

const CATEGORY_LABEL: Record<string, { label: string; color: string }> = {
  invoice:  { label: "請求書", color: "#16A34A" },
  contract: { label: "契約書", color: "#DC2626" },
  proposal: { label: "提案書", color: "#7E3AED" },
  other:    { label: "その他", color: "#6B7280" },
};

export default function DocumentsPage() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [filter, setFilter] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [form, setForm] = useState({
    title: "", category: "other", skill_tags: "", related: ""
  });
  const [file, setFile] = useState<File | null>(null);

  const { data: docs = [] } = useQuery<Doc[]>({
    queryKey: ["documents", filter],
    queryFn: () => {
      const p = new URLSearchParams();
      if (filter) p.set("category", filter);
      return fetch(`${API}/api/documents?${p}`).then(r => r.json());
    },
  });

  const upload = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("ファイルを選択してください");
      const fd = new FormData();
      fd.append("file", file);
      if (form.title)      fd.append("title", form.title);
      fd.append("category", form.category);
      if (form.skill_tags) fd.append("skill_tags", form.skill_tags);
      if (form.related)    fd.append("related", form.related);
      const r = await fetch(`${API}/api/documents/upload`, { method: "POST", body: fd });
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["knowledge"] });
      setShowUpload(false);
      setFile(null);
      setForm({ title: "", category: "other", skill_tags: "", related: "" });
    },
  });

  const counts: Record<string, number> = docs.reduce((acc, d) => ({ ...acc, [d.category]: (acc[d.category] || 0) + 1 }), {} as Record<string, number>);

  return (
    <div className="p-8 max-w-5xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>資料・添付ファイル</h1>
        <button onClick={() => setShowUpload(true)}
          className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-semibold text-white"
          style={{ background: "var(--eb-primary)", fontFamily: "var(--font-inter)" }}>
          <Upload className="w-4 h-4" />
          PDFをアップロード
        </button>
      </div>

      {/* フィルタ */}
      <div className="flex gap-2 mb-6">
        <button onClick={() => setFilter(null)}
          className="px-3 py-1 rounded-full text-xs font-semibold"
          style={{ background: !filter ? "var(--eb-primary)" : "var(--eb-surface-variant)",
                   color: !filter ? "#fff" : "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
          すべて ({docs.length})
        </button>
        {Object.entries(CATEGORY_LABEL).map(([key, conf]) => (
          <button key={key} onClick={() => setFilter(key === filter ? null : key)}
            className="px-3 py-1 rounded-full text-xs font-semibold"
            style={{ background: filter === key ? conf.color : "var(--eb-surface-variant)",
                     color: filter === key ? "#fff" : "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
            {conf.label} ({counts[key] || 0})
          </button>
        ))}
      </div>

      {/* リスト */}
      {docs.length === 0 ? (
        <div className="rounded-xl p-12 text-center bg-white" style={{ border: "1px solid var(--eb-border)" }}>
          <FileText className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p className="text-sm font-medium mb-1" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>資料がありません</p>
          <p className="text-xs" style={{ color: "var(--eb-neutral)" }}>右上の「PDFをアップロード」から追加できます</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {docs.map(d => {
            const conf = CATEGORY_LABEL[d.category] ?? CATEGORY_LABEL.other;
            return (
              <div key={d.id} className="rounded-xl p-4 bg-white"
                style={{ border: "1px solid var(--eb-border)", boxShadow: "0 1px 3px rgba(0,0,0,0.06)" }}>
                <div className="flex items-start gap-3">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
                    style={{ background: conf.color + "22" }}>
                    <FileText className="w-5 h-5" style={{ color: conf.color }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-sm truncate" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{d.title}</p>
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
                        style={{ background: conf.color + "22", color: conf.color, fontFamily: "var(--font-inter)" }}>
                        {conf.label}
                      </span>
                      {d.skill_tags ? (
                        <span className="text-[10px] px-2 py-0.5 rounded"
                          style={{ background: "#FEF3C7", color: "#92400E", fontFamily: "var(--font-inter)" }}>
                          {d.skill_tags.split(",")[0].trim()}
                        </span>
                      ) : (
                        <span className="text-[10px] px-2 py-0.5 rounded"
                          style={{ background: "#DBEAFE", color: "#1E40AF", fontFamily: "var(--font-inter)" }}>
                          全体共有
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] mt-2 line-clamp-2" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-noto-sans-jp)" }}>
                      {d.summary}
                    </p>
                    <p className="text-[10px] mt-1.5 truncate inline-flex items-center gap-1" style={{ color: "var(--eb-neutral)" }}>
                      <FolderPathIcon className="w-3 h-3" aria-label="folder" />
                      <span className="truncate">{d.md_path?.replace(/^.*Obsidian\//, "")}</span>
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* アップロードモーダル */}
      {showUpload && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: "rgba(0,0,0,0.4)" }}
          onClick={e => { if (e.target === e.currentTarget) setShowUpload(false); }}>
          <div className="bg-white rounded-xl p-6 w-full max-w-lg mx-4" style={{ boxShadow: "0 8px 32px rgba(0,0,0,0.16)" }}>
            <h2 className="font-bold text-base mb-4" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>PDFをアップロード</h2>

            {/* ファイル選択 */}
            <div className="mb-3">
              <label className="block text-[10px] font-semibold mb-1" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>PDFファイル</label>
              <button type="button" onClick={() => fileRef.current?.click()}
                className="w-full p-3 rounded text-xs text-left border-dashed inline-flex items-center gap-1"
                style={{ border: "2px dashed var(--eb-border)", color: file ? "#1f2937" : "var(--eb-neutral)" }}>
                {file ? (
                  <>
                    <FileTextIcon className="w-3 h-3 shrink-0" aria-label="pdf file" />
                    <span>{file.name} ({(file.size/1024).toFixed(0)}KB)</span>
                  </>
                ) : "クリックしてPDFを選択..."}
              </button>
              <input ref={fileRef} type="file" accept=".pdf" className="hidden"
                onChange={e => setFile(e.target.files?.[0] ?? null)} />
            </div>

            {/* メタデータ */}
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div className="col-span-2">
                <label className="block text-[10px] font-semibold mb-1" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>タイトル（省略時はファイル名）</label>
                <input value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
                  className="w-full px-2 py-1.5 rounded text-xs"
                  style={{ border: "1px solid var(--eb-border)", outline: "none", fontFamily: "var(--font-inter)" }} />
              </div>
              <div>
                <label className="block text-[10px] font-semibold mb-1" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>カテゴリ</label>
                <select value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
                  className="w-full px-2 py-1.5 rounded text-xs"
                  style={{ border: "1px solid var(--eb-border)", outline: "none", fontFamily: "var(--font-inter)" }}>
                  <option value="invoice">請求書</option>
                  <option value="contract">契約書</option>
                  <option value="proposal">提案書</option>
                  <option value="other">その他</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-semibold mb-1" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>スキル限定（空なら全体共有）</label>
                <input value={form.skill_tags} onChange={e => setForm(f => ({ ...f, skill_tags: e.target.value }))}
                  placeholder="例: invoice-create,finance"
                  className="w-full px-2 py-1.5 rounded text-xs"
                  style={{ border: "1px solid var(--eb-border)", outline: "none", fontFamily: "var(--font-inter)" }} />
              </div>
              <div className="col-span-2">
                <label className="block text-[10px] font-semibold mb-1" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>関連ナレッジ（[[リンク]]として埋め込み・カンマ区切り）</label>
                <input value={form.related} onChange={e => setForm(f => ({ ...f, related: e.target.value }))}
                  placeholder="例: 経理ルール, 振込先・経理情報"
                  className="w-full px-2 py-1.5 rounded text-xs"
                  style={{ border: "1px solid var(--eb-border)", outline: "none", fontFamily: "var(--font-inter)" }} />
              </div>
            </div>

            {upload.error && (
              <p className="text-xs p-2 rounded mb-3" style={{ background: "#FEE2E2", color: "#991B1B" }}>
                エラー: {String((upload.error as Error).message).slice(0, 200)}
              </p>
            )}

            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowUpload(false)}
                className="px-4 py-2 rounded text-xs font-semibold"
                style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                キャンセル
              </button>
              <button onClick={() => upload.mutate()} disabled={!file || upload.isPending}
                className="px-4 py-2 rounded text-xs font-semibold text-white disabled:opacity-50 flex items-center gap-1"
                style={{ background: "var(--eb-primary)", fontFamily: "var(--font-inter)" }}>
                {upload.isPending && <Loader className="w-3 h-3 animate-spin" />}
                {upload.isPending ? "取り込み中..." : "アップロード"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
