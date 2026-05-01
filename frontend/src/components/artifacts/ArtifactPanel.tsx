"use client";

import { useEffect, useState } from "react";
import {
  Artifact,
  ArtifactWS,
  ArtifactWSEvent,
  fetchArtifacts,
  pinArtifact,
  unpinArtifact,
  archiveArtifact,
  updateArtifact,
  exportArtifact,
  exportDownloadUrl,
} from "@/lib/artifacts";
import { ListView } from "./views/ListView";
import { TableView } from "./views/TableView";
import { KanbanView } from "./views/KanbanView";
import { KpiCardView } from "./views/KpiCardView";
import { MarkdownView } from "./views/MarkdownView";
import { ChartView } from "./views/ChartView";
import { GanttView } from "./views/GanttView";
import { CalendarView } from "./views/CalendarView";
import { CompareView } from "./views/CompareView";
import { WorkflowView } from "./views/WorkflowView";
import { GalleryView } from "./views/GalleryView";
import { MatrixView } from "./views/MatrixView";
import { FormView } from "./views/FormView";
import { SlideView } from "./views/SlideView";
import { MindmapView } from "./views/MindmapView";

interface Props {
  threadId?: number;
  onClose?: () => void;
}

export function ArtifactPanel({ threadId, onClose }: Props) {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // 初回ロード + WS 購読
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      const { artifacts: items } = await fetchArtifacts({
        thread_id: threadId,
        limit: 30,
      });
      if (!cancelled) {
        setArtifacts(items);
        if (items[0] && !activeId) setActiveId(items[0].id);
        setLoading(false);
      }
    })();

    const ws = new ArtifactWS("masato");
    ws.connect();
    const off = ws.on((evt: ArtifactWSEvent) => {
      if (!evt.artifact && !evt.artifact_id) return;
      setArtifacts((prev) => {
        if (evt.event === "artifact.deleted") {
          return prev.filter((a) => a.id !== evt.artifact_id);
        }
        if (!evt.artifact) return prev;
        const idx = prev.findIndex((a) => a.id === evt.artifact!.id);
        if (idx >= 0) {
          const copy = [...prev];
          copy[idx] = evt.artifact!;
          return copy;
        }
        // 新規 + 同じスレッドなら追加
        if (!threadId || evt.artifact.thread_id === threadId) {
          return [evt.artifact, ...prev];
        }
        return prev;
      });
      if (evt.event === "artifact.created" && evt.artifact) {
        setActiveId(evt.artifact.id);
      }
    });

    return () => {
      cancelled = true;
      off();
      ws.disconnect();
    };
  }, [threadId]);

  const active = artifacts.find((a) => a.id === activeId) || null;

  const handlePinToggle = async (a: Artifact) => {
    const isPinned = a.pinned_by.includes("masato");
    const updated = isPinned ? await unpinArtifact(a.id) : await pinArtifact(a.id);
    setArtifacts((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
  };

  const handleDataChange = async (newData: Record<string, unknown>) => {
    if (!active) return;
    const updated = await updateArtifact(active.id, { data: newData });
    setArtifacts((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
  };

  const handleArchive = async (id: string) => {
    await archiveArtifact(id);
    setArtifacts((prev) => prev.filter((a) => a.id !== id));
    if (activeId === id) setActiveId(null);
  };

  return (
    <div className="flex h-full w-full flex-col border-l bg-white">
      {/* ヘッダ */}
      <div className="flex items-center gap-2 border-b px-4 py-2">
        <span className="font-semibold">Artifacts</span>
        <span className="text-xs text-gray-500">{artifacts.length} 件</span>
        <div className="ml-auto flex gap-1">
          {onClose && (
            <button
              className="rounded px-2 py-1 text-xs hover:bg-gray-100"
              onClick={onClose}
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* タブ風リスト */}
      <div className="flex gap-1 overflow-x-auto border-b bg-gray-50 px-2 py-1.5">
        {loading && <span className="text-xs text-gray-500">読込中…</span>}
        {!loading && artifacts.length === 0 && (
          <span className="text-xs text-gray-500">まだ artifact がありません</span>
        )}
        {artifacts.map((a) => (
          <button
            key={a.id}
            onClick={() => setActiveId(a.id)}
            className={`flex shrink-0 items-center gap-1 rounded px-2 py-1 text-xs transition ${
              activeId === a.id
                ? "bg-blue-100 text-blue-800"
                : "bg-white text-gray-700 hover:bg-gray-100"
            }`}
            title={a.title}
          >
            <span>{typeIcon(a.type)}</span>
            <span className="max-w-[12rem] truncate">{a.title || a.type}</span>
            {a.pinned_by.includes("masato") && <span>📌</span>}
          </button>
        ))}
      </div>

      {/* アクションバー */}
      {active && (
        <div className="flex items-center gap-2 border-b px-3 py-1.5 text-xs">
          <span className="rounded bg-gray-100 px-2 py-0.5">{active.type}</span>
          {active.category_tags.map((t) => (
            <span key={t} className="rounded bg-gray-100 px-2 py-0.5">
              {t}
            </span>
          ))}
          <button
            className="ml-auto rounded px-2 py-1 hover:bg-gray-100"
            onClick={() => handlePinToggle(active)}
          >
            {active.pinned_by.includes("masato") ? "📌 ピン解除" : "📌 ピン留め"}
          </button>
          <ExportMenu artifact={active} />
          <button
            className="rounded px-2 py-1 hover:bg-gray-100"
            onClick={() => handleArchive(active.id)}
          >
            アーカイブ
          </button>
        </div>
      )}

      {/* レンダラー */}
      <div className="flex-1 overflow-auto p-4">
        {active && (
          <ArtifactRenderer artifact={active} onChange={handleDataChange} />
        )}
        {!active && !loading && (
          <div className="flex h-full items-center justify-center text-sm text-gray-400">
            artifact を選択してください
          </div>
        )}
      </div>
    </div>
  );
}

function ArtifactRenderer({
  artifact,
  onChange,
}: {
  artifact: Artifact;
  onChange: (data: Record<string, unknown>) => void;
}) {
  switch (artifact.type) {
    case "list":
      return <ListView data={artifact.data} onChange={onChange} />;
    case "table":
      return <TableView data={artifact.data} onChange={onChange} />;
    case "kanban":
      return <KanbanView data={artifact.data} onChange={onChange} />;
    case "kpi-card":
      return <KpiCardView data={artifact.data} />;
    case "markdown":
      return <MarkdownView data={artifact.data} />;
    case "chart":
      return <ChartView data={artifact.data} onChange={onChange} />;
    case "gantt":
      return <GanttView data={artifact.data} onChange={onChange} />;
    case "calendar":
      return <CalendarView data={artifact.data} onChange={onChange} />;
    case "compare":
      return <CompareView data={artifact.data} onChange={onChange} />;
    case "workflow":
      return <WorkflowView data={artifact.data} onChange={onChange} />;
    case "gallery":
      return <GalleryView data={artifact.data} onChange={onChange} />;
    case "matrix":
      return <MatrixView data={artifact.data} onChange={onChange} />;
    case "form":
      return <FormView data={artifact.data} onChange={onChange} />;
    case "slide":
      return <SlideView data={artifact.data} onChange={onChange} />;
    case "mindmap":
      return <MindmapView data={artifact.data} onChange={onChange} />;
    default:
      return (
        <pre className="whitespace-pre-wrap text-xs text-gray-700">
          {JSON.stringify(artifact.data, null, 2)}
        </pre>
      );
  }
}

function ExportMenu({ artifact }: { artifact: Artifact }) {
  const [busy, setBusy] = useState<string | null>(null);

  const doExport = async (fmt: "pdf" | "xlsx" | "pptx") => {
    setBusy(fmt);
    try {
      const r = await exportArtifact(artifact.id, fmt);
      const a = document.createElement("a");
      a.href = exportDownloadUrl(r.url);
      a.download = r.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e) {
      alert(`export 失敗: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex items-center gap-1">
      {(["pdf", "xlsx", "pptx"] as const).map((f) => (
        <button
          key={f}
          onClick={() => doExport(f)}
          disabled={busy !== null}
          className={`rounded px-2 py-1 text-[10px] uppercase hover:bg-gray-100 ${
            busy === f ? "opacity-50" : ""
          }`}
          title={`${f.toUpperCase()} で書き出し`}
        >
          {busy === f ? "..." : f}
        </button>
      ))}
    </div>
  );
}

function typeIcon(t: string): string {
  switch (t) {
    case "list":     return "✅";
    case "kanban":   return "🗂";
    case "table":    return "📋";
    case "kpi-card": return "📊";
    case "markdown": return "📄";
    case "chart":    return "📈";
    case "gantt":    return "📅";
    case "calendar": return "📅";
    case "compare":  return "⚖️";
    case "workflow": return "🔁";
    case "gallery":  return "🖼";
    case "matrix":   return "🎯";
    case "form":     return "📝";
    case "slide":    return "🎞";
    case "mindmap":  return "🧠";
    default:         return "•";
  }
}
