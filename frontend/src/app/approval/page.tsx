"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, XCircle, MessageSquare, Clock } from "lucide-react";

const API = "http://localhost:8001";

type ApprovalItem = {
  id: number;
  skill_name: string;
  action_type: string;
  payload: Record<string, unknown>;
  status: string;
  requested_at: string;
  notes?: string;
};

export default function ApprovalPage() {
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [revisionText, setRevisionText] = useState("");
  const [modal, setModal] = useState<"approve" | "reject" | "revise" | null>(null);

  const { data: items = [], isLoading } = useQuery<ApprovalItem[]>({
    queryKey: ["approval-pending"],
    queryFn: () => fetch(`${API}/api/approval?status=pending`).then(r => r.json()),
    refetchInterval: 15000,
  });

  const act = useMutation({
    mutationFn: ({ id, action, notes }: { id: number; action: string; notes?: string }) =>
      fetch(`${API}/api/approval/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: action === "approve" ? "approved" : action === "reject" ? "rejected" : "revision_requested", notes }),
      }).then(r => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approval-pending"] });
      qc.invalidateQueries({ queryKey: ["approval-count"] });
      closeModal();
    },
  });

  const closeModal = () => {
    setModal(null);
    setSelectedId(null);
    setRevisionText("");
  };

  const openModal = (id: number, type: "approve" | "reject" | "revise") => {
    setSelectedId(id);
    setModal(type);
  };

  const handleConfirm = () => {
    if (!selectedId) return;
    if (modal === "approve") act.mutate({ id: selectedId, action: "approve" });
    else if (modal === "reject") act.mutate({ id: selectedId, action: "reject" });
    else if (modal === "revise") act.mutate({ id: selectedId, action: "revise", notes: revisionText });
  };

  const formatPayload = (payload: Record<string, unknown>) => {
    if (payload.subject) return `件名: ${payload.subject}`;
    if (payload.title) return `${payload.title}`;
    return JSON.stringify(payload).slice(0, 80) + "…";
  };

  return (
    <div className="p-8 max-w-4xl">
      <h1 className="text-2xl font-bold mb-2" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>承認待ちキュー</h1>
      <p className="text-sm mb-6" style={{ color: "var(--eb-neutral)" }}>15秒ごとに自動更新</p>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm" style={{ color: "var(--eb-neutral)" }}>
          <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
          読み込み中...
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl p-12 text-center" style={{ border: "1px solid var(--eb-border)", background: "#fff" }}>
          <CheckCircle className="w-10 h-10 mx-auto mb-3" style={{ color: "var(--eb-success)" }} />
          <p className="text-sm font-medium">承認待ちの項目はありません</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <div key={item.id} className="rounded-xl p-5 bg-white"
              style={{ border: "1px solid var(--eb-border)", borderLeft: "3px solid var(--eb-tertiary)", boxShadow: "0 1px 3px rgba(0,0,0,0.06)" }}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-bold px-2 py-0.5 rounded"
                      style={{ background: "var(--eb-tertiary-container)", color: "var(--eb-on-tertiary-container)", fontFamily: "var(--font-inter)" }}>
                      {item.skill_name}
                    </span>
                    <span className="text-xs" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                      #{item.id}
                    </span>
                  </div>
                  <p className="text-sm font-medium mb-1" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
                    {item.action_type}
                  </p>
                  <p className="text-xs truncate" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                    {formatPayload(item.payload)}
                  </p>
                  <div className="flex items-center gap-1 mt-2" style={{ color: "var(--eb-neutral)" }}>
                    <Clock className="w-3 h-3" />
                    <span className="text-[11px]" style={{ fontFamily: "var(--font-inter)" }}>
                      {new Date(item.requested_at).toLocaleString("ja-JP")}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => openModal(item.id, "revise")}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-semibold transition-opacity hover:opacity-80"
                    style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}
                  >
                    <MessageSquare className="w-3 h-3" />
                    修正
                  </button>
                  <button
                    onClick={() => openModal(item.id, "reject")}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-semibold transition-opacity hover:opacity-80"
                    style={{ background: "#FEE2E2", color: "var(--eb-error)", fontFamily: "var(--font-inter)" }}
                  >
                    <XCircle className="w-3 h-3" />
                    却下
                  </button>
                  <button
                    onClick={() => openModal(item.id, "approve")}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-semibold text-white transition-opacity hover:opacity-80"
                    style={{ background: "var(--eb-success)", fontFamily: "var(--font-inter)" }}
                  >
                    <CheckCircle className="w-3 h-3" />
                    承認
                  </button>
                </div>
              </div>

              {item.payload && (
                <details className="mt-3">
                  <summary className="text-xs cursor-pointer select-none" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                    詳細を表示
                  </summary>
                  <pre className="mt-2 text-[11px] p-3 rounded overflow-auto max-h-40"
                    style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                    {JSON.stringify(item.payload, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Modal */}
      {modal && (
        <div className="fixed inset-0 flex items-center justify-center z-50"
          style={{ background: "rgba(0,0,0,0.4)" }}
          onClick={(e) => { if (e.target === e.currentTarget) closeModal(); }}>
          <div className="rounded-xl p-6 w-full max-w-md mx-4 bg-white" style={{ boxShadow: "0 8px 32px rgba(0,0,0,0.16)" }}>
            <h2 className="text-base font-bold mb-2" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
              {modal === "approve" ? "承認の確認" : modal === "reject" ? "却下の確認" : "修正依頼"}
            </h2>
            <p className="text-sm mb-4" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-noto-sans-jp)" }}>
              {modal === "approve"
                ? "この項目を承認しますか？承認後、AIが実行を開始します。"
                : modal === "reject"
                ? "この項目を却下しますか？この操作は取り消せません。"
                : "修正内容を入力してください。AIが内容を修正して再度提出します。"}
            </p>

            {modal === "revise" && (
              <textarea
                value={revisionText}
                onChange={e => setRevisionText(e.target.value)}
                placeholder="修正内容を入力..."
                rows={3}
                className="w-full p-3 rounded-lg text-sm resize-none mb-4"
                style={{ border: "1px solid var(--eb-border)", fontFamily: "var(--font-noto-sans-jp)", outline: "none" }}
              />
            )}

            <div className="flex gap-2 justify-end">
              <button onClick={closeModal}
                className="px-4 py-2 rounded-md text-sm font-semibold transition-opacity hover:opacity-80"
                style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
                キャンセル
              </button>
              <button
                onClick={handleConfirm}
                disabled={act.isPending || (modal === "revise" && !revisionText.trim())}
                className="px-4 py-2 rounded-md text-sm font-semibold text-white transition-opacity hover:opacity-80 disabled:opacity-50"
                style={{
                  background: modal === "approve" ? "var(--eb-success)" : modal === "reject" ? "var(--eb-error)" : "var(--eb-primary)",
                  fontFamily: "var(--font-inter)"
                }}>
                {act.isPending ? "処理中..." : modal === "approve" ? "承認する" : modal === "reject" ? "却下する" : "修正依頼を送る"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
