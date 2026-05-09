"use client";

import { useEffect, useState } from "react";
import { X, Copy, Download, Bot, FileText, Palette, Sparkles, ListChecks } from "lucide-react";
import type { Task } from "./TaskKanban";

const API = "http://localhost:8001";

interface SpecBundle {
  task: Task;
  workspace: { id: number; name: string; design_system_ref: string | null };
  design_md_excerpt?: string;
  related_artifacts?: Array<{ id: number; type: string; title: string; data: unknown }>;
  related_skills?: Array<{ name: string; description: string }>;
  acceptance_criteria?: string[];
}

type DrawerTab = "spec" | "design" | "skills" | "handoff";

interface Props {
  task: Task | null;
  onClose: () => void;
  onStatusChange?: (taskId: number, newStatus: string) => void;
}

export function TaskDetailDrawer({ task, onClose, onStatusChange }: Props) {
  const [tab, setTab] = useState<DrawerTab>("spec");
  const [bundle, setBundle] = useState<SpecBundle | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!task) {
      setBundle(null);
      return;
    }
    setTab("spec");
    setLoading(true);
    fetch(`${API}/api/tasks/${task.id}/handoff`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setBundle(data))
      .catch(() => setBundle(null))
      .finally(() => setLoading(false));
  }, [task]);

  if (!task) return null;

  const handoffMd = bundle ? buildHandoffMarkdown(bundle) : "";

  const copyHandoff = async () => {
    if (!handoffMd) return;
    await navigator.clipboard.writeText(handoffMd);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const downloadHandoff = () => {
    if (!handoffMd) return;
    const blob = new Blob([handoffMd], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `task-${task.id}-handoff.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />

      <aside
        className="fixed right-0 top-0 z-50 h-full w-[480px] bg-white shadow-2xl flex flex-col"
        style={{ borderLeft: "1px solid var(--eb-border)" }}
      >
        <div className="px-5 py-4 flex items-start gap-3" style={{ borderBottom: "1px solid var(--eb-border)" }}>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span
                className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)" }}
              >
                #{task.id}
              </span>
              <StatusBadge status={task.status} onChange={(s) => onStatusChange?.(task.id, s)} />
            </div>
            <h2
              className="text-base font-bold leading-tight"
              style={{ fontFamily: "var(--font-noto-sans-jp)" }}
            >
              {task.title}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-gray-100 shrink-0"
            aria-label="閉じる"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex gap-1 px-3 pt-2" style={{ borderBottom: "1px solid var(--eb-border)" }}>
          <DrawerTabBtn id="spec"     current={tab} onClick={setTab} icon={<FileText className="w-3.5 h-3.5" />}>仕様</DrawerTabBtn>
          <DrawerTabBtn id="design"   current={tab} onClick={setTab} icon={<Palette  className="w-3.5 h-3.5" />}>デザイン</DrawerTabBtn>
          <DrawerTabBtn id="skills"   current={tab} onClick={setTab} icon={<Sparkles className="w-3.5 h-3.5" />}>スキル</DrawerTabBtn>
          <DrawerTabBtn id="handoff"  current={tab} onClick={setTab} icon={<ListChecks className="w-3.5 h-3.5" />}>引き継ぎ</DrawerTabBtn>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {loading && <p className="text-xs text-gray-500">読み込み中…</p>}

          {!loading && tab === "spec" && (
            <SpecTab task={task} bundle={bundle} />
          )}
          {!loading && tab === "design" && (
            <DesignTab bundle={bundle} />
          )}
          {!loading && tab === "skills" && (
            <SkillsTab task={task} />
          )}
          {!loading && tab === "handoff" && (
            <HandoffTab
              md={handoffMd}
              onCopy={copyHandoff}
              onDownload={downloadHandoff}
              copied={copied}
            />
          )}
        </div>

        {task.assignee_name && (
          <div
            className="px-5 py-3 flex items-center gap-2 text-xs"
            style={{ borderTop: "1px solid var(--eb-border)", background: "var(--eb-surface-variant)" }}
          >
            <Bot className="w-3.5 h-3.5" style={{ color: "var(--eb-neutral)" }} />
            <span style={{ color: "var(--eb-neutral)" }}>担当: {task.assignee_name}</span>
          </div>
        )}
      </aside>
    </>
  );
}

function DrawerTabBtn({
  id, current, onClick, icon, children,
}: {
  id: DrawerTab; current: DrawerTab; onClick: (t: DrawerTab) => void;
  icon: React.ReactNode; children: React.ReactNode;
}) {
  const active = current === id;
  return (
    <button
      onClick={() => onClick(id)}
      className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t -mb-px"
      style={{
        color: active ? "var(--eb-primary)" : "var(--eb-neutral)",
        borderBottom: active ? "2px solid var(--eb-primary)" : "2px solid transparent",
        fontFamily: "var(--font-noto-sans-jp)",
      }}
    >
      {icon}
      {children}
    </button>
  );
}

function StatusBadge({ status, onChange }: { status: string; onChange: (s: string) => void }) {
  const conf: Record<string, { label: string; bg: string; color: string }> = {
    pending:           { label: "未着手",   bg: "#F3F4F6", color: "#6B7280" },
    in_progress:       { label: "進行中",   bg: "#DBEAFE", color: "#1E40AF" },
    blocked_question:  { label: "質問待ち", bg: "#FEF3C7", color: "#92400E" },
    blocked_dependency:{ label: "依存待ち", bg: "#FEF3C7", color: "#92400E" },
    review_needed:     { label: "確認待ち", bg: "#E0F2FE", color: "#0369A1" },
    completed:         { label: "完了",     bg: "#DCFCE7", color: "#16A34A" },
    failed:            { label: "失敗",     bg: "#FEE2E2", color: "#DC2626" },
    cancelled:         { label: "中止",     bg: "#F3F4F6", color: "#6B7280" },
  };
  const c = conf[status] ?? conf.pending;
  return (
    <select
      value={status}
      onChange={(e) => onChange(e.target.value)}
      className="text-[10px] font-semibold px-1.5 py-0.5 rounded border-0 cursor-pointer"
      style={{ background: c.bg, color: c.color, fontFamily: "var(--font-inter)" }}
    >
      {Object.entries(conf).map(([k, v]) => (
        <option key={k} value={k}>{v.label}</option>
      ))}
    </select>
  );
}

function SpecTab({ task, bundle }: { task: Task; bundle: SpecBundle | null }) {
  const ac = bundle?.acceptance_criteria ?? extractAcceptanceCriteria(task.description);
  return (
    <div className="space-y-5">
      <Section title="説明">
        <p
          className="text-sm whitespace-pre-wrap leading-relaxed"
          style={{ fontFamily: "var(--font-noto-sans-jp)", color: "#1F2937" }}
        >
          {task.description || "(説明なし)"}
        </p>
      </Section>

      {ac.length > 0 && (
        <Section title="受入条件">
          <ul className="space-y-1.5">
            {ac.map((c, i) => (
              <li key={i} className="flex items-start gap-2 text-sm" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
                <span className="mt-1.5 w-1 h-1 rounded-full shrink-0" style={{ background: "var(--eb-primary)" }} />
                <span>{c}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {task.result && (
        <Section title="結果">
          <pre
            className="text-[11px] p-3 rounded max-h-60 overflow-auto whitespace-pre-wrap"
            style={{ background: "var(--eb-surface-variant)", fontFamily: "var(--font-inter)" }}
          >
            {task.result.slice(0, 2000)}
          </pre>
        </Section>
      )}
    </div>
  );
}

function DesignTab({ bundle }: { bundle: SpecBundle | null }) {
  const ws = bundle?.workspace;
  const designRef = ws?.design_system_ref;
  return (
    <div className="space-y-5">
      <Section title="デザインシステム">
        {designRef ? (
          <div
            className="rounded p-3 text-sm"
            style={{ background: "var(--eb-surface-variant)" }}
          >
            <code className="text-xs">{designRef}</code>
          </div>
        ) : (
          <p className="text-xs" style={{ color: "var(--eb-neutral)" }}>
            未設定 (workspace.design_system_ref をセットすると DESIGN.md がここに表示されます)
          </p>
        )}
      </Section>

      {bundle?.design_md_excerpt && (
        <Section title="DESIGN.md 抜粋">
          <pre
            className="text-[11px] p-3 rounded max-h-80 overflow-auto whitespace-pre-wrap"
            style={{ background: "var(--eb-surface-variant)", fontFamily: "var(--font-inter)" }}
          >
            {bundle.design_md_excerpt.slice(0, 3000)}
          </pre>
        </Section>
      )}

      {bundle?.related_artifacts && bundle.related_artifacts.length > 0 && (
        <Section title={`関連 Artifact (${bundle.related_artifacts.length})`}>
          <div className="space-y-1.5">
            {bundle.related_artifacts.map((a) => (
              <div
                key={a.id}
                className="text-xs p-2 rounded"
                style={{ background: "var(--eb-surface-variant)", border: "1px solid var(--eb-border)" }}
              >
                <span
                  className="font-mono text-[10px] mr-2 px-1 py-0.5 rounded"
                  style={{ background: "#fff", color: "var(--eb-neutral)" }}
                >
                  {a.type}
                </span>
                {a.title}
              </div>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}

function SkillsTab({ task }: { task: Task }) {
  return (
    <div className="space-y-5">
      <Section title="このタスクで使うスキル">
        {task.skill_name ? (
          <div
            className="rounded p-3"
            style={{ background: "var(--eb-tertiary-container)" }}
          >
            <code
              className="text-sm font-semibold"
              style={{ color: "var(--eb-on-tertiary-container)" }}
            >
              {task.skill_name}
            </code>
            <p
              className="text-[11px] mt-1.5"
              style={{ color: "var(--eb-on-tertiary-container)", opacity: 0.8 }}
            >
              Claude Code で <code>bf_load_skill(&quot;{task.skill_name}&quot;)</code> を呼ぶと SKILL.md 全文を取得できます。
            </p>
          </div>
        ) : (
          <p className="text-xs" style={{ color: "var(--eb-neutral)" }}>
            スキル未指定。task.skill_name をセットすると Claude Code が自動的に該当スキルをロードします。
          </p>
        )}
      </Section>
    </div>
  );
}

function HandoffTab({
  md, onCopy, onDownload, copied,
}: {
  md: string; onCopy: () => void; onDownload: () => void; copied: boolean;
}) {
  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <button
          onClick={onCopy}
          className="flex items-center gap-1.5 px-3 py-2 rounded text-xs font-semibold text-white"
          style={{ background: "var(--eb-primary)", fontFamily: "var(--font-noto-sans-jp)" }}
        >
          <Copy className="w-3.5 h-3.5" />
          {copied ? "コピー済" : "Markdown コピー"}
        </button>
        <button
          onClick={onDownload}
          className="flex items-center gap-1.5 px-3 py-2 rounded text-xs font-semibold"
          style={{
            background: "#fff",
            border: "1px solid var(--eb-border)",
            color: "#1F2937",
            fontFamily: "var(--font-noto-sans-jp)",
          }}
        >
          <Download className="w-3.5 h-3.5" />
          .md ダウンロード
        </button>
      </div>

      <div
        className="rounded p-3 text-[11px] overflow-auto max-h-[60vh]"
        style={{
          background: "#0F172A",
          color: "#E2E8F0",
          fontFamily: "var(--font-inter), monospace",
        }}
      >
        <pre className="whitespace-pre-wrap">{md || "(bundle 未取得)"}</pre>
      </div>

      <p className="text-[11px]" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-noto-sans-jp)" }}>
        この Markdown を Claude Code に貼り付け、または <code>.md</code> としてプロジェクトに置けば、
        MCP <code>bf_*</code> ツール経由でこのタスクの全文脈を取得した状態で実装を開始できます。
      </p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3
        className="text-[10px] font-bold uppercase tracking-wider mb-2"
        style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}
      >
        {title}
      </h3>
      {children}
    </div>
  );
}

function extractAcceptanceCriteria(description: string): string[] {
  if (!description) return [];
  const lines = description.split(/\r?\n/);
  const out: string[] = [];
  let inAC = false;
  for (const raw of lines) {
    const line = raw.trim();
    if (/^(##?\s*)?(受入条件|受け入れ条件|Acceptance Criteria|AC)\s*:?$/i.test(line)) {
      inAC = true;
      continue;
    }
    if (inAC) {
      if (line.startsWith("##") || line === "") {
        if (out.length > 0) break;
        continue;
      }
      const m = line.match(/^[-*•]\s*(.+)$/);
      if (m) out.push(m[1]);
    }
  }
  return out;
}

function buildHandoffMarkdown(b: SpecBundle): string {
  const t = b.task;
  const ac = b.acceptance_criteria ?? extractAcceptanceCriteria(t.description);
  const lines: string[] = [];
  lines.push(`# Task #${t.id}: ${t.title}`);
  lines.push("");
  lines.push(`> **Workspace**: ${b.workspace?.name ?? "?"} (id=${b.workspace?.id ?? "?"})`);
  lines.push(`> **Status**: \`${t.status}\``);
  if (t.skill_name) lines.push(`> **Skill**: \`${t.skill_name}\``);
  if (t.assignee_name) lines.push(`> **Assignee**: ${t.assignee_name}`);
  lines.push("");
  lines.push("## 説明");
  lines.push("");
  lines.push(t.description || "(説明なし)");
  lines.push("");
  if (ac.length > 0) {
    lines.push("## 受入条件");
    lines.push("");
    for (const c of ac) lines.push(`- [ ] ${c}`);
    lines.push("");
  }
  if (b.workspace?.design_system_ref) {
    lines.push("## デザイン参照");
    lines.push("");
    lines.push(`- design_system_ref: \`${b.workspace.design_system_ref}\``);
    lines.push("");
  }
  if (b.related_artifacts && b.related_artifacts.length > 0) {
    lines.push("## 関連 Artifact");
    lines.push("");
    for (const a of b.related_artifacts) {
      lines.push(`- **${a.type}**: ${a.title} (id=${a.id})`);
    }
    lines.push("");
  }
  lines.push("## Claude Code 連携");
  lines.push("");
  lines.push("以下の MCP ツールでこのタスクの全文脈にアクセスできます:");
  lines.push("");
  lines.push("```");
  lines.push(`bf_get_spec(task_id=${t.id})              # このタスクの完全な仕様パッケージ`);
  if (t.skill_name) lines.push(`bf_load_skill("${t.skill_name}")           # 該当スキルの SKILL.md 全文`);
  lines.push(`bf_post_progress(task_id=${t.id}, ...)    # 進捗報告`);
  lines.push(`bf_attach_artifact(task_id=${t.id}, ...)  # 成果物登録`);
  lines.push(`bf_request_review(task_id=${t.id}, ...)   # レビュー依頼`);
  lines.push("```");
  lines.push("");
  return lines.join("\n");
}
