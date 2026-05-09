"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Workspace, fetchWorkspace } from "@/lib/workspaces";
import { WorkspaceShell } from "@/components/workspace-shell";
import {
  listMinutes, getMinutes, createMinutes, updateMinutes,
  type MinutesArtifact,
} from "@/lib/minutes-api";
import {
  Upload, Plus, Users, Bot, MessageSquare, User, MapPin, Calendar,
  PenLine, Share2, Download, Archive, CheckCircle2, Circle, Loader2,
} from "lucide-react";

const MinutesEditor = dynamic(
  () => import("@/components/workspace-shell/MinutesEditor").then((m) => m.MinutesEditor),
  { ssr: false, loading: () => <div style={{ padding: 40, color: "var(--bf-text-3)" }}>エディタを読み込み中…</div> }
);

type SaveStatus = "idle" | "dirty" | "saving" | "saved" | "error";

export default function MinutesPage() {
  const params = useParams();
  const id = Number(params?.id);
  const qc = useQueryClient();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "client" | "internal">("all");
  const [search, setSearch] = useState("");
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const saveTimer = useRef<NodeJS.Timeout | null>(null);
  const lastSavedHash = useRef<string>("");

  useEffect(() => {
    if (!id) return;
    fetchWorkspace(id).then(setWorkspace).catch(() => setWorkspace(null));
  }, [id]);

  // 一覧取得
  const { data: minutes = [], isLoading } = useQuery({
    queryKey: ["minutes", id],
    queryFn: () => listMinutes(id),
    enabled: !!id,
    refetchInterval: 10000,
  });

  // 初回 active 設定
  useEffect(() => {
    if (!activeId && minutes.length > 0) setActiveId(minutes[0].id);
  }, [minutes, activeId]);

  // 詳細取得 (アクティブな議事録のフルデータ)
  const { data: activeMinutes } = useQuery({
    queryKey: ["minutes-detail", activeId],
    queryFn: () => activeId ? getMinutes(activeId) : null,
    enabled: !!activeId,
  });

  const filtered = useMemo(() => {
    return minutes.filter((m) => {
      const cat = m.data?.meta?.category ?? "client";
      if (filter !== "all" && cat !== filter) return false;
      if (search && !m.title.includes(search)) return false;
      return true;
    });
  }, [minutes, filter, search]);

  const createMut = useMutation({
    mutationFn: async () => {
      const created = await createMinutes({
        workspaceId: id,
        title: "新規議事録",
        meta: { category: "client", date: new Date().toISOString().slice(0, 10) },
        blocks: [],
      });
      return created;
    },
    onSuccess: (m) => {
      if (m) {
        qc.invalidateQueries({ queryKey: ["minutes", id] });
        setActiveId(m.id);
      }
    },
  });

  const onEditorChange = (blocks: any[]) => {
    if (!activeId) return;
    const hash = JSON.stringify(blocks).slice(0, 200);
    if (hash === lastSavedHash.current) return;
    setSaveStatus("dirty");
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      setSaveStatus("saving");
      const ok = await updateMinutes({ artifactId: activeId, blocks });
      if (ok) {
        lastSavedHash.current = hash;
        setSaveStatus("saved");
        qc.invalidateQueries({ queryKey: ["minutes-detail", activeId] });
      } else {
        setSaveStatus("error");
      }
    }, 1000);
  };

  if (!workspace) {
    return <div className="p-6" style={{ color: "var(--bf-text-3)" }}>読み込み中…</div>;
  }

  return (
    <WorkspaceShell
      workspaceId={id}
      workspaceName={workspace.name}
      progressPercent={45}
      daysLeft={23}
      active="minutes"
      breadcrumbs={[
        { label: "Workspaces", href: "/workspaces" },
        { label: workspace.name, href: `/workspaces/${id}` },
        { label: "議事録" },
      ]}
    >
      <div style={{ marginBottom: "var(--bf-space-6)" }}>
        <div className="flex items-start gap-6 flex-wrap">
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.01em", color: "var(--bf-text-1)", marginBottom: 4 }}>
              議事録
            </h1>
            <div style={{ color: "var(--bf-text-3)", fontSize: 13 }}>
              クライアント MTG / 内部レビュー / AI 出力レビューの記録 (BlockNote エディタ・自動保存)
            </div>
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            <button className="inline-flex items-center gap-1.5" style={btnSecondary}>
              <Upload className="w-3.5 h-3.5" /> 音声から作成
            </button>
            <button
              onClick={() => createMut.mutate()}
              disabled={createMut.isPending}
              className="inline-flex items-center gap-1.5"
              style={{ ...btnPrimary, opacity: createMut.isPending ? 0.6 : 1 }}
            >
              <Plus className="w-3.5 h-3.5" /> 新規議事録
            </button>
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: "var(--bf-space-5)", height: "calc(100vh - var(--bf-header-h) - 200px)" }}>
        {/* List */}
        <div style={{ background: "var(--bf-bg-elev)", border: "1px solid var(--bf-border)", borderRadius: "var(--bf-radius-lg)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{ padding: "12px var(--bf-space-4)", borderBottom: "1px solid var(--bf-divider)", display: "flex", flexDirection: "column", gap: 8 }}>
            <input
              placeholder="議事録を検索..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                fontSize: 12.5, height: 34,
                background: "var(--bf-bg-input)",
                border: "1px solid var(--bf-border)",
                borderRadius: "var(--bf-radius-md)",
                padding: "0 10px",
                outline: "none",
              }}
            />
            <div className="flex gap-1">
              {(["all", "client", "internal"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className="flex-1 inline-flex items-center justify-center"
                  style={{
                    height: 28, padding: "0 10px",
                    background: filter === f ? "var(--bf-primary-bg)" : "transparent",
                    color: filter === f ? "var(--bf-primary)" : "var(--bf-text-2)",
                    border: filter === f ? "none" : "1px solid var(--bf-border)",
                    borderRadius: "var(--bf-radius-md)",
                    fontSize: 12, fontWeight: 600,
                  }}
                >
                  {f === "all" ? "全て" : f === "client" ? "クライアント" : "内部"}
                </button>
              ))}
            </div>
          </div>
          <div style={{ flex: 1, overflowY: "auto" }}>
            {isLoading && (
              <div style={{ padding: "var(--bf-space-6)", textAlign: "center", color: "var(--bf-text-3)", fontSize: 12 }}>
                読み込み中…
              </div>
            )}
            {!isLoading && filtered.length === 0 && (
              <EmptyMinutes onCreate={() => createMut.mutate()} />
            )}
            {filtered.map((m) => {
              const isActive = activeId === m.id;
              const meta = m.data?.meta ?? {};
              const cat = meta.category ?? "client";
              const Icon = cat === "client" ? Users : Bot;
              return (
                <button
                  key={m.id}
                  onClick={() => setActiveId(m.id)}
                  className="w-full text-left transition-colors"
                  style={{
                    padding: "var(--bf-space-4)",
                    borderBottom: "1px solid var(--bf-divider)",
                    background: isActive ? "var(--bf-primary-bg)" : "transparent",
                    borderLeft: isActive ? "3px solid var(--bf-primary)" : "3px solid transparent",
                  }}
                >
                  <div className="flex items-center gap-1.5" style={{ fontSize: 13.5, fontWeight: 600, color: "var(--bf-text-1)", marginBottom: 4 }}>
                    <Icon className="w-3.5 h-3.5" />
                    {m.title || "(無題)"}
                  </div>
                  <div className="flex items-center gap-2" style={{ fontSize: 11.5, color: "var(--bf-text-3)" }}>
                    <span>{new Date(m.updated_at).toLocaleDateString("ja-JP")}</span>
                    {meta.participants && meta.participants.length > 0 && (
                      <span className="inline-flex items-center gap-1"><User className="w-3 h-3" />{meta.participants[0]}</span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Detail with BlockNote */}
        <div style={{ background: "var(--bf-bg-elev)", border: "1px solid var(--bf-border)", borderRadius: "var(--bf-radius-lg)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
          {!activeId && (
            <div className="flex flex-col items-center justify-center" style={{ flex: 1, padding: "var(--bf-space-12)", color: "var(--bf-text-3)" }}>
              <MessageSquare className="w-10 h-10" style={{ color: "var(--bf-text-4)", marginBottom: 12 }} />
              <div style={{ fontSize: 13.5, marginBottom: 12 }}>議事録を選択するか、新規作成してください</div>
              <button onClick={() => createMut.mutate()} className="inline-flex items-center gap-1.5" style={btnPrimary}>
                <Plus className="w-3.5 h-3.5" /> 新規議事録を作成
              </button>
            </div>
          )}
          {activeId && (
            <DetailArea
              key={activeId}
              minutes={activeMinutes ?? null}
              saveStatus={saveStatus}
              onChange={onEditorChange}
            />
          )}
        </div>
      </div>
    </WorkspaceShell>
  );
}

function EmptyMinutes({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center text-center" style={{ padding: "var(--bf-space-10) var(--bf-space-4)", color: "var(--bf-text-3)" }}>
      <MessageSquare className="w-8 h-8" style={{ color: "var(--bf-text-4)", marginBottom: 12 }} />
      <div style={{ fontSize: 13, marginBottom: 12 }}>まだ議事録がありません</div>
      <button onClick={onCreate} className="inline-flex items-center gap-1" style={{ ...btnSecondary, height: 28, fontSize: 12 }}>
        <Plus className="w-3.5 h-3.5" /> 最初の議事録を作成
      </button>
    </div>
  );
}

function DetailArea({
  minutes, saveStatus, onChange,
}: {
  minutes: MinutesArtifact | null;
  saveStatus: SaveStatus;
  onChange: (blocks: any[]) => void;
}) {
  if (!minutes) {
    return (
      <div className="flex items-center justify-center" style={{ flex: 1, color: "var(--bf-text-3)", fontSize: 13 }}>
        読み込み中…
      </div>
    );
  }
  const meta = minutes.data?.meta ?? {};
  const initialBlocks = (minutes.data?.blocks?.length ?? 0) > 0 ? minutes.data!.blocks : undefined;

  return (
    <>
      <div style={{ padding: "var(--bf-space-5) var(--bf-space-6)", borderBottom: "1px solid var(--bf-divider)" }}>
        <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: "var(--bf-text-1)", letterSpacing: "-0.01em" }}>
            {minutes.title || "(無題)"}
          </div>
          <SaveStatusIndicator status={saveStatus} />
        </div>
        <div className="flex items-center gap-3 flex-wrap" style={{ fontSize: 12.5, color: "var(--bf-text-3)" }}>
          {meta.date && <span className="inline-flex items-center gap-1"><Calendar className="w-3.5 h-3.5" />{meta.date}</span>}
          {meta.duration && <span className="inline-flex items-center gap-1">{meta.duration}</span>}
          <span className="inline-flex items-center gap-1"><MapPin className="w-3.5 h-3.5" />Online (Google Meet)</span>
          {meta.participants && meta.participants.length > 0 && (
            <span className="inline-flex items-center gap-1"><Users className="w-3.5 h-3.5" />{meta.participants.length} 名 / {meta.participants.join(", ")}</span>
          )}
          {meta.category && (
            <span style={{ padding: "1px 7px", borderRadius: 999, fontSize: 11, fontWeight: 600, background: "var(--bf-primary-bg)", color: "var(--bf-primary)" }}>
              {meta.category === "client" ? "クライアント" : "内部"}
            </span>
          )}
        </div>
        <div className="flex gap-1.5" style={{ marginTop: "var(--bf-space-3)" }}>
          <button className="inline-flex items-center gap-1" style={btnSm}><PenLine className="w-3.5 h-3.5" />タイトル編集</button>
          <button className="inline-flex items-center gap-1" style={btnSm}><Share2 className="w-3.5 h-3.5" />共有</button>
          <button className="inline-flex items-center gap-1" style={btnSm}><Download className="w-3.5 h-3.5" />PDF</button>
          <button className="inline-flex items-center gap-1" style={{ ...btnSm, border: "none" }}><Archive className="w-3.5 h-3.5" />アーカイブ</button>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "var(--bf-space-6)" }}>
        <MinutesEditor initialContent={initialBlocks} onChange={onChange} />
      </div>
    </>
  );
}

function SaveStatusIndicator({ status }: { status: SaveStatus }) {
  const map = {
    idle:   { label: "編集前",     color: "var(--bf-text-4)",    Icon: Circle },
    dirty:  { label: "未保存",     color: "var(--bf-warning)",   Icon: Circle },
    saving: { label: "保存中…",   color: "var(--bf-primary)",   Icon: Loader2 },
    saved:  { label: "保存済み",   color: "var(--bf-success)",   Icon: CheckCircle2 },
    error:  { label: "保存エラー", color: "var(--bf-danger)",    Icon: Circle },
  };
  const c = map[status];
  return (
    <span className="inline-flex items-center gap-1" style={{ fontSize: 11.5, color: c.color, fontWeight: 500 }}>
      <c.Icon className={`w-3.5 h-3.5 ${status === "saving" ? "animate-spin" : ""}`} />
      {c.label}
    </span>
  );
}

const btnSecondary: React.CSSProperties = { height: 34, padding: "0 14px", background: "var(--bf-bg-elev)", color: "var(--bf-text-1)", border: "1px solid var(--bf-border)", borderRadius: "var(--bf-radius-md)", fontSize: 13, fontWeight: 600 };
const btnPrimary:   React.CSSProperties = { height: 34, padding: "0 14px", background: "var(--bf-primary)", color: "#fff", borderRadius: "var(--bf-radius-md)", fontSize: 13, fontWeight: 600, border: "1px solid transparent" };
const btnSm:        React.CSSProperties = { height: 28, padding: "0 10px", background: "var(--bf-bg-elev)", color: "var(--bf-text-2)", border: "1px solid var(--bf-border)", borderRadius: "var(--bf-radius-md)", fontSize: 12, fontWeight: 600 };
