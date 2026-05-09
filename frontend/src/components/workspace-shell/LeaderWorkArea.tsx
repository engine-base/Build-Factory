"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import {
  Play, PenLine, RotateCcw, SettingsIcon, Send, MoreHorizontal,
  Check, FolderOpen, FileText, ArrowRight, MessageSquare, UserCog,
} from "lucide-react";
import { Settings2 } from "lucide-react";
import { LeaderAvatar } from "./LeaderAvatar";
import type { LeaderId, LeaderDef } from "./types";

export type PhaseStatus = "done" | "in-progress" | "pending" | "locked";

export type StepDef = {
  num: number;
  title: string;
  desc: string;
  status: "done" | "in-progress" | "pending";
  meta?: string;
};

export type ArtifactRef = {
  id: string | number;
  title: string;
  meta: string;
  latest?: boolean;
  icon?: any;
  href?: string;        // 指定時はそのリンクへ遷移 (Penpot キャンバス等)
  external?: boolean;   // 外部リンク (新タブ)
};

export type ChatMsg = {
  id: number;
  role: "user" | "ai";
  body: string;
  time?: string;
};

export type PhaseCta = {
  label: string;
  href: string;
  external?: boolean;
  icon?: any;
  description?: string;
};

interface Props {
  workspaceId: number;
  leader: LeaderDef;
  activePhaseId: string;            // current phase
  phaseStatuses?: Record<string, PhaseStatus>;
  phaseTitle?: string;
  phaseSkill?: string;
  phaseStatus?: "done" | "in-progress" | "pending";
  steps?: StepDef[];
  outputPreview?: string;           // pre-completion output
  phaseCta?: PhaseCta;              // 大型 CTA (Penpot 等)
  artifacts?: ArtifactRef[];
  initialChat?: ChatMsg[];
  suggestionChips?: string[];
}

/**
 * AI 大分類リーダーの作業エリア。
 * - 上部 Hero (リーダー情報 + スキルチップ)
 * - フェーズタブ (各フェーズの状態を表示)
 * - 左: 作業エリア (STEP リスト + 中間出力 + アクションボタン + 成果物履歴)
 * - 右: チャットパネル (リーダーと対話)
 */
export function LeaderWorkArea({
  workspaceId, leader, activePhaseId, phaseStatuses = {},
  phaseTitle, phaseSkill, phaseStatus = "in-progress",
  steps, outputPreview, phaseCta, artifacts = [],
  initialChat = [], suggestionChips = [],
}: Props) {
  const [chat, setChat] = useState<ChatMsg[]>(initialChat);
  const [input, setInput] = useState("");
  const chatBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat]);

  const send = () => {
    if (!input.trim()) return;
    const user: ChatMsg = { id: Date.now(), role: "user", body: input, time: "今" };
    setChat((c) => [...c, user]);
    setInput("");
    // モック AI レスポンス
    setTimeout(() => {
      setChat((c) => [...c, {
        id: Date.now() + 1, role: "ai",
        body: "了解しました。次の STEP に反映します。実装ロジックは Claude Code MCP 経由で実行されます。",
        time: "今",
      }]);
    }, 600);
  };

  const phaseStatusInferred = (phaseId: string): PhaseStatus => {
    if (phaseStatuses[phaseId]) return phaseStatuses[phaseId];
    return phaseId === activePhaseId ? "in-progress" : "pending";
  };

  return (
    <>
      {/* Hero */}
      <div
        className="flex items-center gap-4"
        style={{
          padding: "var(--bf-space-5) var(--bf-space-6)",
          background: "linear-gradient(135deg, var(--bf-primary-soft) 0%, var(--bf-primary-bg) 100%)",
          border: "1px solid var(--bf-border)",
          borderRadius: "var(--bf-radius-lg)",
          marginBottom: "var(--bf-space-6)",
        }}
      >
        <LeaderAvatar id={leader.id} size={56} />
        <div className="flex-1">
          <h1 style={{ fontSize: 20, fontWeight: 700, letterSpacing: "-0.01em", color: "var(--bf-text-1)", marginBottom: 4 }}>
            {leader.label} ライン
          </h1>
          <div style={{ fontSize: 13, color: "var(--bf-text-3)" }}>
            このラインで担当するスキル: {leader.phases.length} フェーズ
          </div>
          <div className="flex items-center gap-1.5 flex-wrap" style={{ marginTop: 8 }}>
            {leader.phases.map((p) => {
              const st = phaseStatusInferred(p.id);
              return (
                <span key={p.id} className="inline-flex items-center gap-1" style={chipStyle(st)}>
                  <PhaseDot status={st} />
                  {p.label}
                </span>
              );
            })}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 11, color: "var(--bf-text-3)", marginBottom: 4 }}>担当 AI 設定</div>
          <button className="inline-flex items-center gap-1" style={btnSm}>
            <UserCog className="w-3.5 h-3.5" />
            編集
          </button>
        </div>
      </div>

      {/* Phase tabs */}
      <div className="inline-flex" style={{ gap: 4, marginBottom: "var(--bf-space-5)", background: "var(--bf-bg-elev)", border: "1px solid var(--bf-border)", borderRadius: "var(--bf-radius-md)", padding: 4 }}>
        {leader.phases.map((p) => {
          const isActive = p.id === activePhaseId;
          const st = phaseStatusInferred(p.id);
          return (
            <Link
              key={p.id}
              href={`/workspaces/${workspaceId}/leader/${leader.id}/${p.id}`}
              className="inline-flex items-center gap-1.5 transition-colors"
              style={{
                padding: "8px 14px",
                borderRadius: "var(--bf-radius-sm)",
                fontSize: 13,
                fontWeight: isActive ? 600 : 500,
                background: isActive ? "var(--bf-primary-bg)" : "transparent",
                color: isActive ? "var(--bf-primary)"
                  : st === "done" ? "var(--bf-success)"
                  : "var(--bf-text-3)",
              }}
            >
              <PhaseDot status={st} />
              {p.label}
            </Link>
          );
        })}
      </div>

      {/* Body: work area + chat */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 380px", gap: "var(--bf-space-5)" }}>
        {/* Work area */}
        <div>
          <div style={{
            background: "var(--bf-bg-elev)",
            border: "1px solid var(--bf-border)",
            borderRadius: "var(--bf-radius-lg)",
            overflow: "hidden",
            marginBottom: "var(--bf-space-5)",
          }}>
            <div className="flex items-center gap-3" style={{ padding: "var(--bf-space-4) var(--bf-space-5)", borderBottom: "1px solid var(--bf-divider)" }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: "var(--bf-text-1)", flex: 1 }}>
                {phaseTitle ?? leader.phases.find((p) => p.id === activePhaseId)?.label}{" "}
                {phaseSkill && <span style={{ fontSize: 12, fontWeight: 500, color: "var(--bf-text-3)" }}>({phaseSkill} スキル)</span>}
              </div>
              <PhaseStatusBadge status={phaseStatus} />
              <button className="inline-flex items-center gap-1" style={btnSm}>
                <Settings2 className="w-3.5 h-3.5" />
                スキル設定
              </button>
            </div>

            <div style={{ padding: "var(--bf-space-5)" }}>
              {/* Step list */}
              {steps && steps.length > 0 && (
                <div style={{ marginBottom: "var(--bf-space-6)" }}>
                  {steps.map((s) => <StepRow key={s.num} step={s} />)}
                </div>
              )}

              {/* Output preview */}
              {outputPreview && (
                <div style={{
                  background: "var(--bf-bg-soft)",
                  border: "1px solid var(--bf-border)",
                  borderRadius: "var(--bf-radius-md)",
                  padding: "var(--bf-space-4)",
                  marginBottom: "var(--bf-space-4)",
                }}>
                  <div className="flex items-center justify-between" style={{ marginBottom: "var(--bf-space-3)" }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "var(--bf-text-2)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                      中間出力 (AI 生成中)
                    </span>
                    <span className="badge parallel" style={{
                      padding: "1px 7px",
                      borderRadius: 999,
                      fontSize: 11, fontWeight: 600,
                      background: "var(--bf-info-bg)",
                      color: "var(--bf-info)",
                    }}>
                      最終出力前
                    </span>
                  </div>
                  <pre style={{
                    fontSize: 13, lineHeight: 1.7, color: "var(--bf-text-1)",
                    whiteSpace: "pre-wrap",
                    fontFamily: "Inter, 'Noto Sans JP', sans-serif",
                  }}>
                    {outputPreview}
                  </pre>
                </div>
              )}

              {phaseCta && (
                <a
                  href={phaseCta.href}
                  target={phaseCta.external ? "_blank" : undefined}
                  rel={phaseCta.external ? "noopener noreferrer" : undefined}
                  className="flex items-center gap-3 transition-colors"
                  style={{
                    padding: "var(--bf-space-4)",
                    background: "var(--bf-primary-soft)",
                    border: "1px solid var(--bf-primary)",
                    borderRadius: "var(--bf-radius-md)",
                    marginBottom: "var(--bf-space-4)",
                    color: "var(--bf-text-1)",
                  }}
                >
                  <div className="flex items-center justify-center" style={{
                    width: 40, height: 40,
                    background: "var(--bf-primary)",
                    borderRadius: "var(--bf-radius-md)",
                    color: "#fff",
                    flexShrink: 0,
                  }}>
                    {phaseCta.icon ? <phaseCta.icon className="w-5 h-5" /> : <Play className="w-5 h-5" />}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "var(--bf-primary)" }}>
                      {phaseCta.label}
                    </div>
                    {phaseCta.description && (
                      <div style={{ fontSize: 12, color: "var(--bf-text-2)", marginTop: 2 }}>
                        {phaseCta.description}
                      </div>
                    )}
                  </div>
                  <ArrowRight className="w-4 h-4" style={{ color: "var(--bf-primary)" }} />
                </a>
              )}

              <div className="flex gap-2">
                <button className="inline-flex items-center gap-1.5" style={btnPrimary}>
                  <Play className="w-3.5 h-3.5" />
                  STEP を完了させる
                </button>
                <button className="inline-flex items-center gap-1.5" style={btnSecondary}>
                  <PenLine className="w-3.5 h-3.5" />
                  出力を編集
                </button>
                <button className="inline-flex items-center gap-1.5" style={btnGhost}>
                  <RotateCcw className="w-3.5 h-3.5" />
                  やり直す
                </button>
              </div>
            </div>
          </div>

          {/* Artifacts */}
          {artifacts.length > 0 && (
            <div style={{
              background: "var(--bf-bg-elev)",
              border: "1px solid var(--bf-border)",
              borderRadius: "var(--bf-radius-lg)",
              overflow: "hidden",
            }}>
              <div className="flex items-center justify-between" style={{ padding: "14px var(--bf-space-5)", borderBottom: "1px solid var(--bf-divider)" }}>
                <h2 className="flex items-center gap-2" style={{ fontSize: 13, fontWeight: 700, color: "var(--bf-text-1)" }}>
                  <FolderOpen className="w-3.5 h-3.5" />
                  成果物履歴 ({leader.label} ライン)
                </h2>
                <a href="#" className="flex items-center gap-1" style={{ color: "var(--bf-primary)", fontSize: 12, fontWeight: 600 }}>
                  全て <ArrowRight className="w-3.5 h-3.5" />
                </a>
              </div>
              {artifacts.map((a, i) => {
                const Icon = a.icon ?? FileText;
                return (
                  <a
                    key={a.id}
                    href={a.href ?? "#"}
                    target={a.external ? "_blank" : undefined}
                    rel={a.external ? "noopener noreferrer" : undefined}
                    className="flex items-center gap-3 transition-colors"
                    style={{
                      padding: "10px var(--bf-space-5)",
                      borderBottom: i < artifacts.length - 1 ? "1px solid var(--bf-divider)" : undefined,
                    }}
                  >
                    <div className="flex items-center justify-center" style={{
                      width: 32, height: 32,
                      background: "var(--bf-bg-soft)",
                      border: "1px solid var(--bf-border)",
                      borderRadius: "var(--bf-radius-md)",
                      color: "var(--bf-text-2)",
                      flexShrink: 0,
                    }}>
                      <Icon className="w-3.5 h-3.5" />
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 500, color: "var(--bf-text-1)" }}>
                        {a.title}
                      </div>
                      <div style={{ fontSize: 11.5, color: "var(--bf-text-3)" }}>
                        {a.meta}
                      </div>
                    </div>
                    {a.latest && (
                      <span style={{ padding: "1px 7px", borderRadius: 999, fontSize: 11, fontWeight: 600, background: "var(--bf-success-bg)", color: "var(--bf-success)" }}>
                        最新
                      </span>
                    )}
                    {a.href && (
                      <ArrowRight className="w-3.5 h-3.5" style={{ color: "var(--bf-text-4)" }} />
                    )}
                  </a>
                );
              })}
            </div>
          )}
        </div>

        {/* Chat panel */}
        <div style={{
          background: "var(--bf-bg-elev)",
          border: "1px solid var(--bf-border)",
          borderRadius: "var(--bf-radius-lg)",
          overflow: "hidden",
          display: "flex", flexDirection: "column",
          height: "calc(100vh - var(--bf-header-h) - 280px)",
          minHeight: 500,
        }}>
          <div className="flex items-center gap-3" style={{ padding: "var(--bf-space-4) var(--bf-space-5)", borderBottom: "1px solid var(--bf-divider)" }}>
            <LeaderAvatar id={leader.id} size={32} />
            <div className="flex-1">
              <div style={{ fontSize: 14, fontWeight: 700 }}>{leader.label}</div>
              <div className="flex items-center gap-1" style={{ fontSize: 11, color: "var(--bf-success)" }}>
                <span style={{ width: 6, height: 6, background: "var(--bf-success)", borderRadius: "50%" }} />
                {phaseTitle ?? "作業中"}を進行中
              </div>
            </div>
            <button style={iconBtn}><MoreHorizontal className="w-4 h-4" /></button>
          </div>

          <div style={{ flex: 1, padding: "var(--bf-space-4) var(--bf-space-5)", overflowY: "auto", background: "var(--bf-bg-soft)" }}>
            {chat.length === 0 && (
              <div className="flex flex-col items-center justify-center text-center" style={{ height: "100%", padding: "var(--bf-space-6)" }}>
                <MessageSquare className="w-8 h-8" style={{ color: "var(--bf-text-4)", marginBottom: 12 }} />
                <div style={{ fontSize: 13, color: "var(--bf-text-3)" }}>
                  {leader.label} と対話を始めましょう
                </div>
              </div>
            )}
            {chat.map((m) => <ChatBubble key={m.id} msg={m} leaderId={leader.id} />)}
            <div ref={chatBottomRef} />
          </div>

          {suggestionChips.length > 0 && (
            <div className="flex gap-1.5 flex-wrap" style={{ padding: "0 var(--bf-space-4) var(--bf-space-3)", background: "var(--bf-bg-elev)" }}>
              {suggestionChips.map((c, i) => (
                <button
                  key={i}
                  onClick={() => setInput(c)}
                  style={{
                    padding: "4px 10px",
                    background: "var(--bf-bg-soft)",
                    border: "1px solid var(--bf-border)",
                    borderRadius: 999,
                    fontSize: 11.5,
                    color: "var(--bf-text-2)",
                  }}
                >
                  {c}
                </button>
              ))}
            </div>
          )}

          <div className="flex gap-2" style={{ padding: "var(--bf-space-3) var(--bf-space-4)", borderTop: "1px solid var(--bf-border)", background: "var(--bf-bg-elev)" }}>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder={`${leader.label} に話しかける…`}
              style={{
                flex: 1,
                padding: "10px 12px",
                background: "var(--bf-bg-input)",
                border: "1px solid var(--bf-border)",
                borderRadius: "var(--bf-radius-md)",
                fontSize: 13,
                resize: "none",
                height: 60,
                outline: "none",
              }}
            />
            <button
              onClick={send}
              className="inline-flex items-center gap-1"
              style={{
                ...btnPrimary,
                height: 60, padding: "0 14px",
                alignSelf: "stretch",
              }}
            >
              <Send className="w-3.5 h-3.5" />
              送信
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

function StepRow({ step }: { step: StepDef }) {
  const numStyle: Record<StepDef["status"], React.CSSProperties> = {
    done:        { background: "var(--bf-success)", borderColor: "var(--bf-success)", color: "#fff" },
    "in-progress": { background: "var(--bf-primary)", borderColor: "var(--bf-primary)", color: "#fff" },
    pending:     { background: "transparent", borderColor: "var(--bf-border)", color: "var(--bf-text-3)" },
  };

  return (
    <div className="flex items-start gap-3" style={{ padding: "var(--bf-space-3) 0", borderBottom: "1px solid var(--bf-divider)" }}>
      <div className="flex items-center justify-center flex-shrink-0" style={{
        width: 24, height: 24, borderRadius: "50%",
        border: "1.5px solid",
        fontSize: 11, fontWeight: 700,
        ...numStyle[step.status],
      }}>
        {step.status === "done" ? <Check className="w-3.5 h-3.5" /> : step.num}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--bf-text-1)", marginBottom: 2 }}>
          {step.title}
        </div>
        <div style={{ fontSize: 12, color: "var(--bf-text-3)", marginBottom: 6 }}>{step.desc}</div>
        {step.meta && <div style={{ fontSize: 11, color: "var(--bf-text-4)" }}>{step.meta}</div>}
      </div>
    </div>
  );
}

function ChatBubble({ msg, leaderId }: { msg: ChatMsg; leaderId: LeaderId }) {
  const isUser = msg.role === "user";
  return (
    <div className="flex gap-2" style={{ flexDirection: isUser ? "row-reverse" : "row", marginBottom: "var(--bf-space-4)" }}>
      {isUser ? (
        <div style={{
          width: 28, height: 28, borderRadius: "50%",
          background: "linear-gradient(135deg, #2563EB, #06B6D4)",
          color: "#fff",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontWeight: 700, fontSize: 10,
          flexShrink: 0,
        }}>
          MA
        </div>
      ) : (
        <LeaderAvatar id={leaderId} size={28} />
      )}
      <div>
        <div style={{
          maxWidth: "80%",
          padding: "10px 14px",
          background: isUser ? "var(--bf-primary)" : "var(--bf-bg-elev)",
          color: isUser ? "#fff" : "var(--bf-text-1)",
          border: isUser ? "1px solid var(--bf-primary)" : "1px solid var(--bf-border)",
          borderRadius: "var(--bf-radius-md)",
          fontSize: 13, lineHeight: 1.55,
          whiteSpace: "pre-wrap",
        }}>
          {msg.body}
        </div>
        {msg.time && (
          <div style={{ fontSize: 10.5, color: "var(--bf-text-4)", marginTop: 4 }}>{msg.time}</div>
        )}
      </div>
    </div>
  );
}

function PhaseStatusBadge({ status }: { status: "done" | "in-progress" | "pending" }) {
  const map = {
    done:        { label: "完了",   bg: "var(--bf-success-bg)", color: "var(--bf-success)" },
    "in-progress": { label: "進行中", bg: "var(--bf-primary-bg)", color: "var(--bf-primary)" },
    pending:     { label: "未着手", bg: "var(--bf-neutral-bg)", color: "var(--bf-neutral)" },
  };
  const c = map[status];
  return (
    <span style={{
      padding: "1px 7px", borderRadius: 999,
      fontSize: 11, fontWeight: 600,
      background: c.bg, color: c.color,
    }}>
      {c.label}
    </span>
  );
}

function PhaseDot({ status }: { status: PhaseStatus }) {
  const color = status === "done" ? "var(--bf-success)"
    : status === "in-progress" ? "var(--bf-primary)"
    : status === "locked" ? "var(--bf-text-4)"
    : "var(--bf-text-4)";
  return (
    <span style={{ width: 6, height: 6, borderRadius: "50%", background: color }} />
  );
}

function chipStyle(status: PhaseStatus): React.CSSProperties {
  return {
    padding: "2px 8px",
    background: "#fff",
    border: "1px solid var(--bf-border)",
    borderRadius: 999,
    fontSize: 11, fontWeight: 500,
    color: status === "done" ? "var(--bf-success)" : status === "in-progress" ? "var(--bf-primary)" : "var(--bf-text-2)",
  };
}

const btnPrimary:   React.CSSProperties = { height: 34, padding: "0 14px", background: "var(--bf-primary)", color: "#fff", borderRadius: "var(--bf-radius-md)", fontSize: 13, fontWeight: 600, border: "1px solid transparent" };
const btnSecondary: React.CSSProperties = { height: 34, padding: "0 14px", background: "var(--bf-bg-elev)", color: "var(--bf-text-1)", border: "1px solid var(--bf-border)", borderRadius: "var(--bf-radius-md)", fontSize: 13, fontWeight: 600 };
const btnGhost:     React.CSSProperties = { height: 34, padding: "0 14px", background: "transparent", color: "var(--bf-text-2)", borderRadius: "var(--bf-radius-md)", fontSize: 13, fontWeight: 600, border: "1px solid transparent" };
const btnSm:        React.CSSProperties = { height: 28, padding: "0 10px", background: "var(--bf-bg-elev)", color: "var(--bf-text-1)", border: "1px solid var(--bf-border)", borderRadius: "var(--bf-radius-md)", fontSize: 12, fontWeight: 600 };
const iconBtn:      React.CSSProperties = { width: 32, height: 32, display: "inline-flex", alignItems: "center", justifyContent: "center", color: "var(--bf-text-3)", borderRadius: "var(--bf-radius-md)" };
