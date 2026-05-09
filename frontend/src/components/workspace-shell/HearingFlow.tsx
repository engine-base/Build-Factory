"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchHearingState, startStep, replyHearing, completeStep, patchCenter,
  type HearingState, type StepState, type CenterState, type ChatMsg,
} from "@/lib/hearing-api";
import { LeaderAvatar } from "./LeaderAvatar";
import {
  Send, Play, Check, ChevronDown, ChevronRight, Loader2,
  PenLine, MessageSquare, Sparkles, History,
} from "lucide-react";

interface Props {
  workspaceId: number;
}

/**
 * Phase 1 ヒアリング 対話駆動 UI。
 * - 中央: 累積 STEP リスト (折りたたみ可、リアルタイム更新)
 * - 右: チャットパネル (タイプライター風)
 *
 * 設計: Build-Factory/docs/IA-DESIGN-BRIEF.md / DESIGN-SYSTEM.md
 */
export function HearingFlow({ workspaceId }: Props) {
  const qc = useQueryClient();
  const [activeStep, setActiveStep] = useState<number | null>(null);
  const [collapsed, setCollapsed] = useState<Record<number, boolean>>({});
  const [highlightItems, setHighlightItems] = useState<Set<string>>(new Set());

  const { data: state, isLoading, error } = useQuery<HearingState>({
    queryKey: ["hearing-state", workspaceId],
    queryFn: () => fetchHearingState(workspaceId),
    enabled: !!workspaceId,
    refetchInterval: false,
  });

  const steps = state?.steps ?? [];

  // 初回 active 設定: 進行中があればそれ、なければ未着手の最初
  useEffect(() => {
    if (steps.length === 0 || activeStep != null) return;
    const inProg = steps.find((s) => s.status === "draft");
    if (inProg) { setActiveStep(inProg.step); return; }
    const next = steps.find((s) => s.status === "not_started");
    if (next) { setActiveStep(next.step); return; }
    setActiveStep(steps[0]?.step ?? 1);
  }, [steps, activeStep]);

  const startMut = useMutation({
    mutationFn: (step: number) => startStep(workspaceId, step),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["hearing-state", workspaceId] }),
  });

  const completeMut = useMutation({
    mutationFn: (step: number) => completeStep(workspaceId, step),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["hearing-state", workspaceId] });
      if (data.next_step) setActiveStep(data.next_step);
    },
  });

  const replyMut = useMutation({
    mutationFn: ({ step, message }: { step: number; message: string }) =>
      replyHearing(workspaceId, step, message),
    onSuccess: (data, vars) => {
      // 新規追加項目をハイライト
      const added = new Set<string>();
      for (const op of data.patch ?? []) {
        if (op.operation !== "remove") {
          for (const it of (op.items ?? [])) {
            added.add(`${vars.step}:${op.section_key}:${it}`);
          }
        }
      }
      setHighlightItems(added);
      setTimeout(() => setHighlightItems(new Set()), 2000);
      qc.invalidateQueries({ queryKey: ["hearing-state", workspaceId] });
    },
  });

  if (isLoading) {
    return <div style={{ padding: 40, color: "var(--bf-text-3)" }}>ヒアリング状態を読み込み中…</div>;
  }
  if (error || !state) {
    return (
      <div style={{
        padding: "var(--bf-space-6)",
        background: "var(--bf-danger-bg)",
        border: "1px solid var(--bf-danger)",
        borderRadius: "var(--bf-radius-lg)",
        color: "var(--bf-danger)",
        fontSize: 13,
      }}>
        ヒアリング API に接続できません。バックエンドが起動しているか、`chat_messages` テーブルが作成済みか確認してください。
      </div>
    );
  }
  if (steps.length === 0) {
    return (
      <div style={{
        padding: "var(--bf-space-12)",
        background: "var(--bf-bg-elev)",
        border: "1px dashed var(--bf-border)",
        borderRadius: "var(--bf-radius-lg)",
        textAlign: "center",
        color: "var(--bf-text-3)",
        fontSize: 13,
      }}>
        STEP 構成が取得できませんでした。
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 380px", gap: "var(--bf-space-5)", height: "calc(100vh - var(--bf-header-h) - 200px)" }}>
      {/* 中央エリア: 累積 STEP リスト */}
      <div style={{ overflowY: "auto" }}>
        {steps.map((s) => (
          <StepBlock
            key={s.step}
            workspaceId={workspaceId}
            stepState={s}
            isActive={activeStep === s.step}
            isCollapsed={collapsed[s.step] ?? (s.status === "confirmed" && activeStep !== s.step)}
            onToggle={() => setCollapsed((c) => ({ ...c, [s.step]: !c[s.step] }))}
            onActivate={() => setActiveStep(s.step)}
            onStart={() => { setActiveStep(s.step); startMut.mutate(s.step); }}
            onComplete={() => completeMut.mutate(s.step)}
            isStarting={startMut.isPending && startMut.variables === s.step}
            isCompleting={completeMut.isPending && completeMut.variables === s.step}
            highlightItems={highlightItems}
          />
        ))}
      </div>

      {/* 右側: チャットパネル */}
      <ChatPanel
        steps={steps}
        activeStep={activeStep ?? 1}
        onSubmit={(msg) => activeStep != null && replyMut.mutate({ step: activeStep, message: msg })}
        isReplying={replyMut.isPending}
      />
    </div>
  );
}

/* ───────── STEP ブロック ───────── */

function StepBlock({
  workspaceId,
  stepState, isActive, isCollapsed, onToggle, onActivate,
  onStart, onComplete, isStarting, isCompleting, highlightItems,
}: {
  workspaceId: number;
  stepState: StepState;
  isActive: boolean;
  isCollapsed: boolean;
  onToggle: () => void;
  onActivate: () => void;
  onStart: () => void;
  onComplete: () => void;
  isStarting: boolean;
  isCompleting: boolean;
  highlightItems: Set<string>;
}) {
  const { step, title, status, center } = stepState;

  const statusBadge = (() => {
    if (status === "confirmed") return { label: `確定 v1`, bg: "var(--bf-success-bg)", color: "var(--bf-success)" };
    if (status === "draft")     return { label: "進行中 / 下書き", bg: "var(--bf-primary-bg)", color: "var(--bf-primary)" };
    return                          { label: "未着手", bg: "var(--bf-neutral-bg)", color: "var(--bf-neutral)" };
  })();

  const allSections = [...(center?.sections ?? []), ...(center?.free_sections ?? [])];
  const totalItems = allSections.reduce((acc, s) => acc + (s.items?.length ?? 0), 0);

  return (
    <div
      style={{
        background: "var(--bf-bg-elev)",
        border: `1px solid ${isActive ? "var(--bf-primary)" : "var(--bf-border)"}`,
        borderRadius: "var(--bf-radius-lg)",
        marginBottom: "var(--bf-space-4)",
        overflow: "hidden",
        transition: "border-color 200ms",
      }}
      onClick={() => !isActive && onActivate()}
    >
      {/* ヘッダー */}
      <div
        className="flex items-center gap-3"
        style={{
          padding: "var(--bf-space-4) var(--bf-space-5)",
          borderBottom: isCollapsed ? undefined : "1px solid var(--bf-divider)",
          cursor: "pointer",
        }}
        onClick={(e) => { e.stopPropagation(); onToggle(); }}
      >
        <span style={{ color: "var(--bf-text-4)" }}>
          {isCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </span>
        <div style={{ flex: 1 }}>
          <div className="flex items-center gap-2" style={{ fontSize: 14, fontWeight: 700, color: "var(--bf-text-1)" }}>
            STEP {step}: {title}
          </div>
          {isCollapsed && totalItems > 0 && (
            <div style={{ fontSize: 11.5, color: "var(--bf-text-3)", marginTop: 2 }}>
              {totalItems} 項目記録
            </div>
          )}
        </div>
        <span style={{
          padding: "2px 8px", borderRadius: 999,
          fontSize: 11, fontWeight: 600,
          background: statusBadge.bg, color: statusBadge.color,
        }}>
          {statusBadge.label}
        </span>
      </div>

      {/* 中身 */}
      {!isCollapsed && (
        <div style={{ padding: "var(--bf-space-5)" }}>
          {status === "not_started" && (
            <div className="flex flex-col items-center text-center" style={{ padding: "var(--bf-space-8) 0", color: "var(--bf-text-3)" }}>
              <MessageSquare className="w-7 h-7" style={{ color: "var(--bf-text-4)", marginBottom: 12 }} />
              <div style={{ fontSize: 13, marginBottom: 14 }}>
                この STEP を始めると、PM AI が質問を投げかけてきます。<br />
                対話を進めると、ここに整理結果が即時反映されます。
              </div>
              <button
                disabled={isStarting}
                onClick={(e) => { e.stopPropagation(); onStart(); }}
                className="inline-flex items-center gap-1.5"
                style={{
                  height: 36, padding: "0 16px",
                  background: "var(--bf-primary)", color: "#fff",
                  borderRadius: "var(--bf-radius-md)",
                  fontSize: 13, fontWeight: 600,
                  opacity: isStarting ? 0.6 : 1,
                }}
              >
                {isStarting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                STEP {step} を始める
              </button>
            </div>
          )}

          {(status === "draft" || status === "confirmed") && (
            <>
              {allSections.length === 0 || totalItems === 0 ? (
                <div style={{ color: "var(--bf-text-3)", fontSize: 13, padding: "var(--bf-space-4) 0" }}>
                  対話を進めると、ここに整理結果が表示されます。
                </div>
              ) : (
                allSections.map((sec) => sec.items.length > 0 && (
                  <SectionView
                    key={sec.key}
                    workspaceId={workspaceId}
                    centerState={stepState.center}
                    section={sec}
                    step={step}
                    highlightItems={highlightItems}
                  />
                ))
              )}

              {status === "draft" && (
                <div className="flex gap-2" style={{ marginTop: "var(--bf-space-4)", paddingTop: "var(--bf-space-4)", borderTop: "1px solid var(--bf-divider)" }}>
                  <button
                    disabled={isCompleting || totalItems === 0}
                    onClick={(e) => { e.stopPropagation(); onComplete(); }}
                    className="inline-flex items-center gap-1.5"
                    style={{
                      height: 32, padding: "0 14px",
                      background: "var(--bf-success)", color: "#fff",
                      borderRadius: "var(--bf-radius-md)",
                      fontSize: 12.5, fontWeight: 600,
                      opacity: (isCompleting || totalItems === 0) ? 0.6 : 1,
                    }}
                  >
                    {isCompleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                    STEP {step} を完了
                  </button>
                  <button
                    onClick={(e) => e.stopPropagation()}
                    className="inline-flex items-center gap-1.5"
                    style={{
                      height: 32, padding: "0 14px",
                      background: "var(--bf-bg-elev)", color: "var(--bf-text-2)",
                      border: "1px solid var(--bf-border)",
                      borderRadius: "var(--bf-radius-md)",
                      fontSize: 12.5, fontWeight: 600,
                    }}
                  >
                    <PenLine className="w-3.5 h-3.5" />
                    直接編集
                  </button>
                  <button
                    onClick={(e) => e.stopPropagation()}
                    className="inline-flex items-center gap-1.5"
                    style={{
                      height: 32, padding: "0 14px",
                      background: "transparent", color: "var(--bf-text-3)",
                      borderRadius: "var(--bf-radius-md)",
                      fontSize: 12.5, fontWeight: 500,
                    }}
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    整理し直す
                  </button>
                </div>
              )}

              {status === "confirmed" && (
                <div className="flex items-center gap-2" style={{ marginTop: "var(--bf-space-4)", paddingTop: "var(--bf-space-4)", borderTop: "1px solid var(--bf-divider)" }}>
                  <button
                    onClick={(e) => e.stopPropagation()}
                    className="inline-flex items-center gap-1.5"
                    style={{
                      height: 28, padding: "0 12px",
                      background: "var(--bf-bg-elev)", color: "var(--bf-text-2)",
                      border: "1px solid var(--bf-border)",
                      borderRadius: "var(--bf-radius-md)",
                      fontSize: 12, fontWeight: 600,
                    }}
                  >
                    <History className="w-3.5 h-3.5" />
                    履歴: v1
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

/* ───────── セクションビュー (1 つのセクションの 箇条書き) ───────── */

function SectionView({
  section, step, highlightItems,
}: {
  workspaceId?: number;
  centerState?: CenterState;
  section: { key: string; label: string; items: string[] };
  step: number;
  highlightItems: Set<string>;
}) {
  return (
    <div style={{ marginBottom: "var(--bf-space-4)" }}>
      <div style={{
        fontSize: 11, fontWeight: 700,
        color: "var(--bf-text-3)",
        textTransform: "uppercase", letterSpacing: "0.05em",
        marginBottom: 6,
      }}>
        {section.label}
      </div>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {section.items.map((item, i) => {
          const key = `${step}:${section.key}:${item}`;
          const isHighlighted = highlightItems.has(key);
          return (
            <li
              key={i}
              style={{
                fontSize: 13.5, lineHeight: 1.7,
                color: "var(--bf-text-1)",
                padding: "6px 10px 6px 18px",
                marginLeft: -8,
                borderRadius: "var(--bf-radius-sm)",
                background: isHighlighted ? "var(--bf-primary-soft)" : "transparent",
                animation: isHighlighted ? "bf-fadein 250ms ease-out" : undefined,
                transition: "background 1.5s ease-out",
                position: "relative",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              <span style={{
                position: "absolute", left: 6, top: 13,
                width: 4, height: 4, borderRadius: "50%",
                background: "var(--bf-text-4)",
              }} />
              {item}
            </li>
          );
        })}
      </ul>
      <style jsx>{`
        @keyframes bf-fadein {
          from { opacity: 0; transform: translateY(-4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

/* ───────── チャットパネル ───────── */

function ChatPanel({
  steps, activeStep, onSubmit, isReplying,
}: {
  steps: StepState[];
  activeStep: number;
  onSubmit: (msg: string) => void;
  isReplying: boolean;
}) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const stepState = steps.find((s) => s.step === activeStep);
  const history = stepState?.history ?? [];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history.length, isReplying]);

  const send = () => {
    if (!input.trim()) return;
    onSubmit(input.trim());
    setInput("");
  };

  return (
    <div style={{
      background: "var(--bf-bg-elev)",
      border: "1px solid var(--bf-border)",
      borderRadius: "var(--bf-radius-lg)",
      overflow: "hidden",
      display: "flex", flexDirection: "column",
    }}>
      <div className="flex items-center gap-3" style={{ padding: "var(--bf-space-4) var(--bf-space-5)", borderBottom: "1px solid var(--bf-divider)" }}>
        <LeaderAvatar id="pm" size={32} />
        <div className="flex-1">
          <div style={{ fontSize: 14, fontWeight: 700, color: "var(--bf-text-1)" }}>PM AI</div>
          <div className="flex items-center gap-1" style={{ fontSize: 11, color: stepState?.status === "draft" ? "var(--bf-success)" : "var(--bf-text-3)" }}>
            {stepState?.status === "draft" ? (
              <>
                <span style={{ width: 6, height: 6, background: "var(--bf-success)", borderRadius: "50%" }} />
                STEP {activeStep} 進行中
              </>
            ) : (
              <span>STEP {activeStep}</span>
            )}
          </div>
        </div>
      </div>

      <div style={{ flex: 1, padding: "var(--bf-space-4) var(--bf-space-5)", overflowY: "auto", background: "var(--bf-bg-soft)" }}>
        {history.length === 0 && (
          <div className="flex flex-col items-center justify-center text-center" style={{ height: "100%", padding: "var(--bf-space-6)", color: "var(--bf-text-3)" }}>
            <MessageSquare className="w-8 h-8" style={{ color: "var(--bf-text-4)", marginBottom: 12 }} />
            <div style={{ fontSize: 13 }}>左の「STEP {activeStep} を始める」を押すと対話が始まります</div>
          </div>
        )}
        {history.filter((m) => m.role !== "system").map((m) => (
          <ChatBubble key={m.id} msg={m} />
        ))}
        {isReplying && (
          <div className="flex gap-2" style={{ marginBottom: "var(--bf-space-4)" }}>
            <LeaderAvatar id="pm" size={28} />
            <div style={{
              padding: "10px 14px",
              background: "var(--bf-bg-elev)",
              border: "1px solid var(--bf-border)",
              borderRadius: "var(--bf-radius-md)",
              fontSize: 13, color: "var(--bf-text-3)",
            }}>
              <Loader2 className="w-3.5 h-3.5 animate-spin inline mr-1" />
              考え中…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="flex gap-2" style={{ padding: "var(--bf-space-3) var(--bf-space-4)", borderTop: "1px solid var(--bf-border)" }}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder={stepState?.status === "not_started" ? "STEP を開始してから話せます" : "PM AI に話す…"}
          disabled={stepState?.status === "not_started" || isReplying}
          style={{
            flex: 1,
            padding: "10px 12px",
            background: "var(--bf-bg-input)",
            border: "1px solid var(--bf-border)",
            borderRadius: "var(--bf-radius-md)",
            fontSize: 13, resize: "none", height: 60, outline: "none",
            opacity: stepState?.status === "not_started" ? 0.5 : 1,
          }}
        />
        <button
          onClick={send}
          disabled={!input.trim() || isReplying || stepState?.status === "not_started"}
          className="inline-flex items-center gap-1"
          style={{
            height: 60, padding: "0 14px",
            background: "var(--bf-primary)", color: "#fff",
            borderRadius: "var(--bf-radius-md)",
            fontSize: 13, fontWeight: 600,
            opacity: !input.trim() || isReplying ? 0.5 : 1,
          }}
        >
          <Send className="w-3.5 h-3.5" />
          送信
        </button>
      </div>
    </div>
  );
}

function ChatBubble({ msg }: { msg: ChatMsg }) {
  const isUser = msg.role === "user";
  return (
    <div className="flex gap-2" style={{ flexDirection: isUser ? "row-reverse" : "row", marginBottom: "var(--bf-space-4)" }}>
      {isUser ? (
        <div style={{
          width: 28, height: 28, borderRadius: "50%",
          background: "linear-gradient(135deg, #2563EB, #06B6D4)",
          color: "#fff", display: "flex", alignItems: "center", justifyContent: "center",
          fontWeight: 700, fontSize: 10, flexShrink: 0,
        }}>
          MA
        </div>
      ) : (
        <LeaderAvatar id="pm" size={28} />
      )}
      <div>
        <div style={{
          maxWidth: "100%",
          padding: "10px 14px",
          background: isUser ? "var(--bf-primary)" : "var(--bf-bg-elev)",
          color: isUser ? "#fff" : "var(--bf-text-1)",
          border: isUser ? "1px solid var(--bf-primary)" : "1px solid var(--bf-border)",
          borderRadius: "var(--bf-radius-md)",
          fontSize: 13, lineHeight: 1.55,
          whiteSpace: "pre-wrap",
        }}>
          {msg.content}
        </div>
      </div>
    </div>
  );
}
