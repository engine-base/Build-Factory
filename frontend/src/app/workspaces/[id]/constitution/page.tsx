// T-026-02: Constitution editor UI (content_md + version diff)
//
// AC マッピング:
//   AC-1 UBIQUITOUS: feature F-026 として Constitution の content_md 編集 + version 履歴
//   AC-2 EVENT-DRIVEN: 保存で /api/constitutions に POST → revision 作成 + invalidate
//   AC-3 STATE-DRIVEN: RLS 経由 + audit_logs 記録
//   AC-4 UNWANTED: invalid markdown / unauthorized → 4xx body.detail.message 表示

"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Save, GitCompare, AlertTriangle, Clock } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

type Constitution = {
  id: number;
  workspace_id: number;
  version: number;
  content_md: string;
  is_current: boolean;
  created_at: string;
};

type Revision = {
  id: number;
  constitution_id: number;
  version: number;
  diff: string;
  created_at: string;
};

export default function ConstitutionEditorPage() {
  const params = useParams();
  const workspaceId = Number(params?.id);
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");
  const [showDiff, setShowDiff] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { data: current } = useQuery<Constitution>({
    queryKey: ["constitution", workspaceId, "current"],
    queryFn: async () => {
      const r = await fetch(`${API}/api/constitutions?workspace_id=${workspaceId}&is_current=true`);
      if (!r.ok) throw new Error("not found");
      const list = await r.json();
      const c = list[0];
      setDraft(c?.content_md ?? "");
      return c;
    },
  });

  const { data: revisions = [] } = useQuery<Revision[]>({
    queryKey: ["constitution-revisions", current?.id],
    queryFn: () => current ? fetch(`${API}/api/constitutions/${current.id}/revisions`).then(r => r.json()) : Promise.resolve([]),
    enabled: !!current?.id,
  });

  const saveMutation = useMutation({
    mutationFn: async (content_md: string) => {
      const r = await fetch(`${API}/api/constitutions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: workspaceId, content_md }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body?.detail?.message ?? `save failed (${r.status})`);
      }
      return r.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["constitution", workspaceId] });
      qc.invalidateQueries({ queryKey: ["constitution-revisions"] });
      setErrorMessage(null);
    },
    onError: (e: Error) => setErrorMessage(e.message),
  });

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-4 flex items-center gap-2 text-eb-500">
        <BookOpen className="w-6 h-6" /> Constitution Editor
      </h1>

      {errorMessage && (
        <div className="mb-4 p-3 bg-red-100 border border-red-300 text-red-700 rounded flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> {errorMessage}
        </div>
      )}

      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2">
          <textarea
            value={draft}
            onChange={e => setDraft(e.target.value)}
            className="w-full h-96 p-3 border border-gray-300 rounded font-mono text-sm focus:border-eb-500 focus:outline-none"
            placeholder="# Constitution Section 1: Mission..."
          />
          <div className="mt-2 flex justify-between">
            <button
              onClick={() => setShowDiff(!showDiff)}
              className="px-4 py-2 border rounded flex items-center gap-2"
            >
              <GitCompare className="w-4 h-4" /> {showDiff ? "Hide" : "Show"} Diff
            </button>
            <button
              onClick={() => saveMutation.mutate(draft)}
              disabled={saveMutation.isPending || draft === (current?.content_md ?? "")}
              className="px-4 py-2 bg-eb-500 text-white rounded hover:bg-eb-700 disabled:opacity-50 flex items-center gap-2"
            >
              <Save className="w-4 h-4" /> Save (v{(current?.version ?? 0) + 1})
            </button>
          </div>
          {showDiff && (
            <pre className="mt-3 p-3 bg-gray-50 border rounded text-xs overflow-auto max-h-48">
              {/* Simple diff hint - real diff via library in full impl */}
              {`Current v${current?.version}: ${(current?.content_md ?? "").length} chars\nDraft: ${draft.length} chars`}
            </pre>
          )}
        </div>

        <div>
          <h2 className="font-bold mb-2 flex items-center gap-2">
            <Clock className="w-4 h-4" /> Versions ({revisions.length})
          </h2>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {revisions.map(r => (
              <div key={r.id} className="p-2 border rounded text-xs hover:border-eb-500">
                <div className="font-mono">v{r.version}</div>
                <div className="text-gray-500">{r.created_at}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
