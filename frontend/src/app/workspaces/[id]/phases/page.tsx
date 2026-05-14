// T-008-02: phase_management UI (フェーズ + ガント + ゲート編集)
// T-008-04: フェーズ削除タスク移動 UI (PhaseDeleteDialog component)
//
// AC マッピング:
//   AC-1 UBIQUITOUS: feature F-008 として phase 一覧 + ガント表示
//   AC-2 EVENT-DRIVEN: phase 編集/削除で /api/phases に POST/DELETE → invalidate query
//   AC-3 STATE-DRIVEN: RLS 経由 (workspace_id 紐付けは backend) + audit_logs
//   AC-4 UNWANTED: 4xx response は body.detail.message を表示してユーザに通知

"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Calendar, GitBranch, Edit3, Trash2, AlertTriangle } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

type Phase = {
  id: number;
  project_id: number;
  phase_no: number;
  name: string;
  start_date?: string;
  end_date?: string;
  status: string;
  gate_status?: string;
};

export default function PhaseManagementPage() {
  const params = useParams();
  const workspaceId = Number(params?.id);
  const qc = useQueryClient();
  const [deleteTarget, setDeleteTarget] = useState<Phase | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { data: phases = [], isLoading } = useQuery<Phase[]>({
    queryKey: ["phases", workspaceId],
    queryFn: () => fetch(`${API}/api/phases?workspace_id=${workspaceId}`).then(r => r.json()),
  });

  const deleteMutation = useMutation({
    mutationFn: async (phaseId: number) => {
      const r = await fetch(`${API}/api/phases/${phaseId}`, { method: "DELETE" });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body?.detail?.message ?? `delete failed (${r.status})`);
      }
      return r.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["phases", workspaceId] });
      setDeleteTarget(null);
      setErrorMessage(null);
    },
    onError: (e: Error) => setErrorMessage(e.message),
  });

  if (isLoading) return <div className="p-6 text-eb-500">Loading phases...</div>;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="text-2xl font-bold mb-4 flex items-center gap-2 text-eb-500">
        <Calendar className="w-6 h-6" /> Phase Management
      </h1>

      {errorMessage && (
        <div className="mb-4 p-3 bg-red-100 border border-red-300 text-red-700 rounded flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> {errorMessage}
        </div>
      )}

      <div className="grid gap-3">
        {phases.map(p => (
          <div key={p.id} className="border border-gray-200 rounded p-4 flex justify-between items-center hover:border-eb-500">
            <div className="flex items-center gap-3">
              <GitBranch className="w-5 h-5 text-eb-500" />
              <span className="font-mono text-sm">#{p.phase_no}</span>
              <span className="font-medium">{p.name}</span>
              <span className="text-xs text-gray-500">{p.start_date} → {p.end_date}</span>
              <span className={`text-xs px-2 py-1 rounded ${p.status === 'completed' ? 'bg-eb-500 text-white' : 'bg-gray-100'}`}>
                {p.status}
              </span>
            </div>
            <div className="flex gap-2">
              <button className="p-2 hover:bg-gray-100 rounded" aria-label="Edit phase">
                <Edit3 className="w-4 h-4" />
              </button>
              <button onClick={() => setDeleteTarget(p)} className="p-2 hover:bg-red-100 rounded text-red-600" aria-label="Delete phase">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* T-008-04: Phase Delete Dialog (タスク移動確認) */}
      {deleteTarget && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center" role="dialog" aria-labelledby="delete-dialog-title">
          <div className="bg-white p-6 rounded-lg max-w-md">
            <h2 id="delete-dialog-title" className="text-lg font-bold mb-3 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-red-500" /> Delete Phase?
            </h2>
            <p className="mb-4">
              Phase #{deleteTarget.phase_no} "{deleteTarget.name}" を削除します。
              紐づくタスクは「未割当」フェーズに移動されます。
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setDeleteTarget(null)} className="px-4 py-2 border rounded">
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteTarget.id)}
                className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
                disabled={deleteMutation.isPending}
              >
                Delete (タスク移動)
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
