"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileText, ChevronRight, FolderOpen } from "lucide-react";
import Link from "next/link";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

const FOLDER_LABELS: Record<string, { label: string; color: string }> = {
  "01_営業": { label: "営業", color: "bg-blue-100 text-blue-700" },
  "02_CRM": { label: "CRM", color: "bg-indigo-100 text-indigo-700" },
  "03_財務": { label: "財務", color: "bg-emerald-100 text-emerald-700" },
  "04_法務": { label: "法務", color: "bg-red-100 text-red-700" },
  "05_経営戦略": { label: "経営戦略", color: "bg-purple-100 text-purple-700" },
  "06_ブランディング": { label: "ブランド", color: "bg-pink-100 text-pink-700" },
  "07_外注": { label: "外注", color: "bg-orange-100 text-orange-700" },
  "08_CS": { label: "CS", color: "bg-cyan-100 text-cyan-700" },
  "09_情報": { label: "情報", color: "bg-yellow-100 text-yellow-700" },
  "10_Web": { label: "Web", color: "bg-teal-100 text-teal-700" },
};

interface Record {
  path: string;
  name: string;
  folder: string;
  size: number;
  modified: number;
}

function getTopFolder(folder: string) {
  return folder.split("/")[0];
}

function fmtDate(ts: number) {
  const d = new Date(ts * 1000);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function SkillActivity() {
  const { data: records = [] } = useQuery<Record[]>({
    queryKey: ["records-recent"],
    queryFn: () => fetch(`${BASE_URL}/api/records`).then(r => r.json()),
    refetchInterval: 15_000,
  });

  const { data: folders = [] } = useQuery<string[]>({
    queryKey: ["folders"],
    queryFn: () => fetch(`${BASE_URL}/api/records/folders`).then(r => r.json()),
  });

  const recent = records.slice(0, 8);

  // Count by top-level folder
  const folderCounts = records.reduce<Record<string, number>>((acc, r) => {
    const top = getTopFolder(r.folder);
    acc[top] = (acc[top] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* Recent outputs */}
      <Card className="lg:col-span-2">
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle className="text-sm font-medium">最新スキル出力</CardTitle>
          <Link href="/records" className="text-xs text-muted-foreground hover:text-primary flex items-center gap-0.5">
            すべて見る <ChevronRight className="w-3 h-3" />
          </Link>
        </CardHeader>
        <CardContent className="p-0">
          {recent.length === 0 ? (
            <div className="flex flex-col items-center py-10 text-muted-foreground text-sm gap-2">
              <FileText className="w-8 h-8 opacity-30" />
              <p>スキルを実行すると出力がここに表示されます</p>
              <p className="text-xs">90のスキルが ~/Documents/会社運営DB/records/ に保存</p>
            </div>
          ) : (
            <div className="divide-y">
              {recent.map((r) => {
                const top = getTopFolder(r.folder);
                const tag = FOLDER_LABELS[top];
                return (
                  <Link
                    key={r.path}
                    href={`/records?path=${encodeURIComponent(r.path)}`}
                    className="flex items-start gap-3 px-4 py-3 hover:bg-muted/40 transition-colors group"
                  >
                    <FileText className="w-4 h-4 text-muted-foreground shrink-0 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate group-hover:text-primary">{r.name}</p>
                      <p className="text-[11px] text-muted-foreground">{fmtDate(r.modified)}</p>
                    </div>
                    {tag && (
                      <span className={`shrink-0 text-[10px] px-2 py-0.5 rounded-full font-medium ${tag.color}`}>
                        {tag.label}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Folder stats */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">カテゴリ別出力数</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {Object.entries(FOLDER_LABELS).map(([key, { label, color }]) => {
            const count = folderCounts[key] || 0;
            return (
              <Link
                key={key}
                href={`/records?folder=${encodeURIComponent(key)}`}
                className="flex items-center justify-between py-1 hover:opacity-80 transition-opacity"
              >
                <div className="flex items-center gap-2">
                  <FolderOpen className="w-3.5 h-3.5 text-muted-foreground" />
                  <span className="text-sm">{label}</span>
                </div>
                <Badge variant={count > 0 ? "default" : "secondary"} className="text-[10px] min-w-[28px] justify-center">
                  {count}
                </Badge>
              </Link>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
