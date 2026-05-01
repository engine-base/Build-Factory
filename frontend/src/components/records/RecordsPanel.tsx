"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchFolders, fetchRecords, fetchRecord } from "@/lib/api";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FileText, FolderOpen, ChevronRight, ArrowLeft, ExternalLink, Inbox } from "lucide-react";
import ReactMarkdown from "react-markdown";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

// 数字プレフィックスを除いたフォルダ表示名
function folderLabel(f: string) {
  return f.replace(/^\d+_/, "");
}

function fmtSize(b: number) {
  return b > 1024 ? `${(b / 1024).toFixed(1)}KB` : `${b}B`;
}
function fmtDate(ts: number) {
  const d = new Date(ts * 1000);
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`;
}

interface RecordFile {
  path: string;
  name: string;
  folder: string;
  size: number;
  modified: number;
}

export function RecordsPanel() {
  // 最初のフォルダを初期選択（nullなら未選択）
  const [folder, setFolder] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  const { data: folders = [] } = useQuery<string[]>({
    queryKey: ["folders"],
    queryFn: fetchFolders,
    onSuccess: (data) => {
      // 初回ロード時に最初のフォルダを選択
      if (folder === null && data.length > 0) setFolder(data[0]);
    },
  } as any);

  const currentFolder = folder ?? (folders[0] ?? "");

  const { data: records = [] } = useQuery<RecordFile[]>({
    queryKey: ["records", currentFolder],
    queryFn: () => fetchRecords(currentFolder),
    enabled: !!currentFolder,
  });

  const { data: file } = useQuery({
    queryKey: ["record", selectedPath],
    queryFn: () => selectedPath ? fetchRecord(selectedPath) : null,
    enabled: !!selectedPath,
  });

  // ── ファイル詳細表示 ──────────────────────────────────────────────────
  if (selectedPath && file) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center gap-2 p-3 border-b bg-muted/30">
          <Button variant="ghost" size="sm" onClick={() => setSelectedPath(null)}>
            <ArrowLeft className="w-4 h-4 mr-1" /> 戻る
          </Button>
          <span className="text-xs text-muted-foreground truncate flex-1">{selectedPath}</span>
          <a
            href={`${BASE_URL}/api/records/html-preview?path=${encodeURIComponent(selectedPath)}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            <Button variant="outline" size="sm" className="text-xs gap-1 shrink-0">
              <ExternalLink className="w-3 h-3" /> HTMLプレビュー
            </Button>
          </a>
        </div>

        {file.metadata && Object.keys(file.metadata).length > 0 && (
          <div className="flex gap-2 flex-wrap p-3 border-b bg-muted/20">
            {Object.entries(file.metadata).slice(0, 8).map(([k, v]) => (
              <Badge key={k} variant="secondary" className="text-[10px]">
                {k}: {String(v)}
              </Badge>
            ))}
          </div>
        )}

        <ScrollArea className="flex-1 p-5">
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown>{file.content}</ReactMarkdown>
          </div>
        </ScrollArea>
      </div>
    );
  }

  // ── フォルダ + ファイル一覧 ───────────────────────────────────────────
  return (
    <div className="flex h-full">
      {/* カテゴリサイドバー（すべてなし） */}
      <div className="w-44 border-r bg-muted/20 shrink-0 flex flex-col">
        <div className="px-3 pt-3 pb-1 text-[11px] font-semibold text-muted-foreground tracking-wide uppercase">
          カテゴリ
        </div>
        <ScrollArea className="flex-1">
          <div className="p-2 space-y-0.5">
            {folders.map((f: string) => (
              <button
                key={f}
                onClick={() => { setFolder(f); setSelectedPath(null); }}
                className={`w-full text-left px-2.5 py-2 rounded-lg text-xs flex items-center gap-2 transition-colors ${
                  currentFolder === f
                    ? "bg-primary text-primary-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted"
                }`}
              >
                <FolderOpen className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">{folderLabel(f)}</span>
              </button>
            ))}
          </div>
        </ScrollArea>
      </div>

      {/* ファイル一覧 */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* ヘッダー */}
        <div className="px-4 py-2.5 border-b bg-muted/10 flex items-center gap-2">
          <FolderOpen className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm font-medium">{currentFolder ? folderLabel(currentFolder) : ""}</span>
          <Badge variant="secondary" className="text-[10px] ml-auto">
            {records.length} 件
          </Badge>
        </div>

        <ScrollArea className="flex-1">
          {records.length === 0 ? (
            // 空フォルダの状態
            <div className="flex flex-col items-center justify-center h-64 text-muted-foreground gap-3">
              <Inbox className="w-10 h-10 opacity-20" />
              <div className="text-center">
                <p className="text-sm font-medium">出力ファイルがありません</p>
                <p className="text-xs mt-1 opacity-70">
                  /{folderLabel(currentFolder)} に関連するスキルを実行すると<br />ここに出力が表示されます
                </p>
              </div>
            </div>
          ) : (
            <div className="p-3 space-y-1">
              {records.map((r) => (
                <button
                  key={r.path}
                  onClick={() => setSelectedPath(r.path)}
                  className="w-full text-left p-3 rounded-xl hover:bg-muted/60 flex items-start gap-3 group border border-transparent hover:border-border transition-all"
                >
                  <FileText className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate group-hover:text-primary">{r.name}</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      {fmtDate(r.modified)} · {fmtSize(r.size)}
                    </p>
                  </div>
                  <ChevronRight className="w-3.5 h-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 shrink-0 mt-1 transition-opacity" />
                </button>
              ))}
            </div>
          )}
        </ScrollArea>
      </div>
    </div>
  );
}
