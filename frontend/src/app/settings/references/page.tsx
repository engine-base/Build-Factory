"use client";

import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  uploadReference,
  listReferences,
  type DocType,
  type ReferenceItem,
} from "@/lib/references-api";
import {
  FileText,
  Upload,
  Trash2,
  FileType2,
  Calendar,
  Tag,
  Search,
} from "lucide-react";

const ACCOUNT_ID = 1; // TODO: post-auth

const DOC_TYPE_OPTIONS: { value: DocType; label: string; desc: string }[] = [
  { value: "generic", label: "汎用 (全フェーズ参照可)", desc: "どのフェーズの AI からも参照される" },
  { value: "hearing_reference", label: "ヒアリング参考", desc: "ヒアリング AI が優先参照" },
  { value: "requirements_reference", label: "要件定義参考", desc: "要件定義 AI が優先参照" },
  { value: "pricing_reference", label: "価格設計参考", desc: "価格設計 AI が優先参照" },
  { value: "proposal_reference", label: "提案書参考", desc: "提案書 AI が優先参照" },
  { value: "estimate_reference", label: "見積書参考", desc: "見積書 AI が優先参照" },
  { value: "template_reference", label: "テンプレート参考", desc: "template-builder AI が優先参照" },
];

export default function ReferencesPage() {
  const qc = useQueryClient();
  const [filterDocType, setFilterDocType] = useState<DocType | "">("");
  const [search, setSearch] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["references", ACCOUNT_ID, filterDocType],
    queryFn: () =>
      listReferences({
        account_id: ACCOUNT_ID,
        doc_type: filterDocType || undefined,
        limit: 200,
      }),
  });

  const items: ReferenceItem[] = (data?.items ?? []).filter((r) => {
    if (!search.trim()) return true;
    const s = search.toLowerCase();
    return (
      (r.title || "").toLowerCase().includes(s) ||
      (r.preview || "").toLowerCase().includes(s) ||
      (r.filename || "").toLowerCase().includes(s)
    );
  });

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">参考資料</h1>
        <p className="mt-1 text-sm text-neutral-600">
          過去の提案書・要件定義書・見積書などをアップロードすると、各フェーズの AI
          がトーン・粒度・構成の参考として参照します。 PDF / DOCX / HTML / Markdown / TXT に対応。
        </p>
      </header>

      <UploadBlock
        onUploaded={() => qc.invalidateQueries({ queryKey: ["references"] })}
      />

      <div className="mt-8 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 rounded-md border border-neutral-300 bg-white px-3 py-2">
          <Search className="h-4 w-4 text-neutral-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="タイトル・本文・ファイル名で検索"
            className="w-64 bg-transparent text-sm outline-none"
          />
        </div>
        <select
          value={filterDocType}
          onChange={(e) => setFilterDocType(e.target.value as DocType | "")}
          className="rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm"
        >
          <option value="">すべての種別</option>
          {DOC_TYPE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <span className="ml-auto text-sm text-neutral-500">
          {isLoading ? "読み込み中…" : `${items.length} 件`}
        </span>
      </div>

      <div className="mt-4 grid gap-3">
        {items.length === 0 && !isLoading && (
          <div className="rounded-md border border-dashed border-neutral-300 p-10 text-center text-sm text-neutral-500">
            参考資料がまだありません。上のフォームからアップロードしてください。
          </div>
        )}
        {items.map((r) => (
          <ReferenceCard key={r.id} item={r} />
        ))}
      </div>
    </div>
  );
}

function UploadBlock({ onUploaded }: { onUploaded: () => void }) {
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [docType, setDocType] = useState<DocType>("generic");
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);

  const upload = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("ファイルを選択してください");
      return uploadReference({
        account_id: ACCOUNT_ID,
        file,
        doc_type: docType,
        title: title || undefined,
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      });
    },
    onSuccess: () => {
      setFile(null);
      setTitle("");
      setTags("");
      if (fileRef.current) fileRef.current.value = "";
      onUploaded();
    },
  });

  return (
    <section className="rounded-lg border border-neutral-200 bg-white p-5">
      <h2 className="text-sm font-semibold text-neutral-800">資料をアップロード</h2>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          const f = e.dataTransfer.files?.[0];
          if (f) setFile(f);
        }}
        className={`mt-3 cursor-pointer rounded-md border-2 border-dashed p-8 text-center text-sm transition ${
          drag
            ? "border-neutral-900 bg-neutral-50"
            : "border-neutral-300 hover:border-neutral-500"
        }`}
        onClick={() => fileRef.current?.click()}
      >
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx,.doc,.html,.htm,.md,.markdown,.txt"
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        {file ? (
          <div className="flex items-center justify-center gap-2 text-neutral-800">
            <FileText className="h-4 w-4" />
            <span className="font-medium">{file.name}</span>
            <span className="text-neutral-500">
              ({Math.round(file.size / 1024)} KB)
            </span>
          </div>
        ) : (
          <div className="text-neutral-500">
            <Upload className="mx-auto mb-2 h-6 w-6" />
            ここにドラッグ&ドロップ、またはクリックして選択
            <div className="mt-1 text-xs">
              PDF / DOCX / HTML / Markdown / TXT (最大 30MB)
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div>
          <label className="block text-xs font-medium text-neutral-600">
            参照種別
          </label>
          <select
            value={docType}
            onChange={(e) => setDocType(e.target.value as DocType)}
            className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm"
          >
            {DOC_TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value} title={o.desc}>
                {o.label}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-neutral-500">
            {DOC_TYPE_OPTIONS.find((o) => o.value === docType)?.desc}
          </p>
        </div>
        <div>
          <label className="block text-xs font-medium text-neutral-600">
            タイトル (任意)
          </label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="省略時はファイル名"
            className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm"
          />
        </div>
        <div className="sm:col-span-2">
          <label className="block text-xs font-medium text-neutral-600">
            タグ (カンマ区切り・任意)
          </label>
          <input
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="例: ec, btob, モバイルアプリ"
            className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm"
          />
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between">
        {upload.isError && (
          <div className="text-sm text-red-600">
            {(upload.error as Error)?.message ?? "アップロード失敗"}
          </div>
        )}
        {upload.isSuccess && (
          <div className="text-sm text-green-700">登録しました。</div>
        )}
        <button
          disabled={!file || upload.isPending}
          onClick={() => upload.mutate()}
          className="ml-auto inline-flex items-center gap-2 rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:bg-neutral-300"
        >
          <Upload className="h-4 w-4" />
          {upload.isPending ? "アップロード中…" : "アップロードしてナレッジ化"}
        </button>
      </div>
    </section>
  );
}

function ReferenceCard({ item }: { item: ReferenceItem }) {
  return (
    <div className="rounded-md border border-neutral-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-sm font-semibold text-neutral-900">
            <FileText className="h-4 w-4 shrink-0 text-neutral-500" />
            <span className="truncate">{item.title}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-neutral-500">
            {item.kind && (
              <span className="inline-flex items-center gap-1">
                <FileType2 className="h-3 w-3" />
                {item.kind.toUpperCase()}
              </span>
            )}
            {item.uploaded_at && (
              <span className="inline-flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {item.uploaded_at.slice(0, 10)}
              </span>
            )}
            {item.char_count != null && (
              <span>{item.char_count.toLocaleString()} 文字</span>
            )}
            {item.doc_type && (
              <span className="rounded bg-neutral-100 px-2 py-0.5">
                {item.doc_type}
              </span>
            )}
          </div>
          {item.preview && (
            <p className="mt-2 line-clamp-3 text-xs text-neutral-600">
              {item.preview}
            </p>
          )}
          {item.tags && item.tags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {item.tags
                .filter((t) => !["knowledge", "reference"].includes(t))
                .map((t) => (
                  <span
                    key={t}
                    className="inline-flex items-center gap-1 rounded bg-neutral-50 px-2 py-0.5 text-[11px] text-neutral-600"
                  >
                    <Tag className="h-3 w-3" />
                    {t}
                  </span>
                ))}
            </div>
          )}
        </div>
        {item.stored_url && (
          <a
            href={item.stored_url}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 rounded border border-neutral-300 bg-white px-3 py-1.5 text-xs font-medium text-neutral-700 hover:bg-neutral-50"
          >
            原本を開く
          </a>
        )}
      </div>
    </div>
  );
}
