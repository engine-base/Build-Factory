"use client";

import "@assistant-ui/styles/index.css";
import { useState, useRef, useEffect, useMemo, useCallback, Fragment } from "react";
import {
  AssistantRuntimeProvider, ThreadPrimitive, MessagePrimitive,
  ComposerPrimitive, useLocalRuntime,
  type ThreadMessageLike,
  type ChatModelAdapter,
} from "@assistant-ui/react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Send, Mic, MicOff, Paperclip, FileText, Video, Music, Image as ImageIcon,
  X, Loader, Sparkles, Bot, ChevronUp, Check, Cpu, User as UserIcon,
  Plus, MessageSquare, Trash2,
} from "lucide-react";
import { ToolUIBlock, parseToolUIBlocks, ToolUIActionProvider } from "@/components/tool-ui";
import { MarkdownView } from "./MarkdownView";

const API = "http://localhost:8001";

type Attachment = {
  id: string; filename: string; size: number;
  kind: "image" | "video" | "audio" | "pdf" | "file";
  content_type: string; url: string;
};
type LLMModel = { id: string; name: string; tier?: string };
type LLMProvider = { id: string; name: string; description: string; available: boolean; models: LLMModel[] };
type Thread = {
  id: number; title: string; channel: string;
  with_employee: number | null; last_active_at: string;
  msg_count: number; first_msg: string | null;
};

const KIND_ICON: Record<string, any> = {
  image: ImageIcon, video: Video, audio: Music, pdf: FileText, file: FileText,
};

type ChatPanelProps = {
  mode: "secretary" | "employee";
  employeeId?: number;
  employeeName?: string;
  employeeColor?: string;
  showThreadList?: boolean;
  className?: string;
  headerExtra?: React.ReactNode;
  /** マウント時に1回だけ自動送信するメッセージ */
  autoSendOnce?: string;
  /** AI バブルに表示する絵文字アイコン */
  avatarEmoji?: string;
  /** 初期 LLM（localStorage に未保存の場合のみ） */
  defaultProvider?: string;
  defaultModel?: string;
};

// ─────────────────────────────────────────────
// 親: スレッド管理 + サイドバー
// ─────────────────────────────────────────────
export function ChatPanel(props: ChatPanelProps) {
  const qc = useQueryClient();
  const { mode, employeeId, showThreadList = true, className = "" } = props;
  const channel = mode === "secretary" ? "secretary" : "employee";
  const targetEmployee = mode === "secretary" ? 1 : employeeId!;

  const [activeThreadId, setActiveThreadId] = useState<number | null>(null);

  const { data: threads = [] } = useQuery<Thread[]>({
    queryKey: ["threads", channel, targetEmployee],
    queryFn: () => {
      const p = new URLSearchParams();
      p.set("channel", channel);
      p.set("with_employee", String(targetEmployee));
      return fetch(`${API}/api/threads?${p}`).then(r => r.json());
    },
    staleTime: 5_000,
    placeholderData: (prev) => prev,   // 切替時に旧データ表示し続ける（チラつき防止）
  });

  useEffect(() => {
    if (!activeThreadId && threads.length > 0) setActiveThreadId(threads[0].id);
  }, [threads.length]);

  const createThread = useMutation({
    mutationFn: () => fetch(`${API}/api/threads`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel, with_employee: targetEmployee }),
    }).then(r => r.json()),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["threads", channel, targetEmployee] });
      setActiveThreadId(data.id);
    },
  });

  const deleteThread = useMutation({
    mutationFn: (id: number) => fetch(`${API}/api/threads/${id}`, { method: "DELETE" }).then(r => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["threads", channel, targetEmployee] });
      setActiveThreadId(null);
    },
  });

  // 自動送信フローでは新スレッド強制
  const [autoSendKey, setAutoSendKey] = useState(0);
  useEffect(() => {
    if (props.autoSendOnce) {
      // autoSendOnce 起動時は新スレッド扱いで開始
      setActiveThreadId(null);
      setAutoSendKey(k => k + 1);
    }
  }, [props.autoSendOnce]);

  return (
    <div className={`flex h-full min-h-0 overflow-hidden ${className}`} style={{ background: "var(--eb-surface-variant)" }}>
      {showThreadList && (
        <ThreadSidebar
          threads={threads}
          activeId={activeThreadId}
          onSelect={setActiveThreadId}
          onCreate={() => createThread.mutate()}
          onDelete={(id) => { if (confirm("このスレッドを削除しますか？")) deleteThread.mutate(id); }}
          accentColor={props.employeeColor || "#7E3AED"}
        />
      )}
      <div className="flex-1 flex flex-col bg-white min-h-0 min-w-0">
        {props.headerExtra}
        <ChatThreadLoader
          key={`${activeThreadId ?? "new"}-${autoSendKey}`}
          chatProps={props}
          channel={channel}
          targetEmployee={targetEmployee}
          activeThreadId={activeThreadId}
          onThreadCreated={(id) => {
            setActiveThreadId(id);
            qc.invalidateQueries({ queryKey: ["threads", channel, targetEmployee] });
          }}
        />
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// ChatThreadLoader: 履歴ロード完了まで ChatBody を遅延マウント
// （useLocalRuntime の initialMessages は初回のみ反映されるため）
// ─────────────────────────────────────────────
function ChatThreadLoader({ chatProps, channel, targetEmployee, activeThreadId, onThreadCreated }: {
  chatProps: ChatPanelProps;
  channel: string;
  targetEmployee: number;
  activeThreadId: number | null;
  onThreadCreated: (id: number) => void;
}) {
  const { data: threadDetail, isLoading } = useQuery<{ thread: Thread; messages: any[] }>({
    queryKey: ["thread", activeThreadId],
    queryFn: () => fetch(`${API}/api/threads/${activeThreadId}`).then(r => r.json()),
    enabled: !!activeThreadId,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const initialMessages: ThreadMessageLike[] = useMemo(() => {
    if (!threadDetail?.messages) return [];
    return threadDetail.messages
      .filter(h => h.role === "user" || h.role === "assistant")
      .map((h: any) => ({
        id: `m-${h.id}`,
        role: h.role,
        content: [{ type: "text" as const, text: h.message }],
      }));
  }, [threadDetail?.messages?.length, activeThreadId]);

  // activeThreadId あるのにまだロード中なら何も描画せず待つ
  if (activeThreadId && isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader className="w-5 h-5 animate-spin opacity-40" />
      </div>
    );
  }

  return (
    <ChatBody
      {...chatProps}
      channel={channel}
      targetEmployee={targetEmployee}
      activeThreadId={activeThreadId}
      onThreadCreated={onThreadCreated}
      initialMessages={initialMessages}
    />
  );
}

// ─────────────────────────────────────────────
// スレッドサイドバー
// ─────────────────────────────────────────────
function ThreadSidebar({ threads, activeId, onSelect, onCreate, onDelete, accentColor }: {
  threads: Thread[];
  activeId: number | null;
  onSelect: (id: number | null) => void;
  onCreate: () => void;
  onDelete: (id: number) => void;
  accentColor: string;
}) {
  return (
    <div className="w-56 shrink-0 flex flex-col bg-white" style={{ borderRight: "1px solid var(--eb-border)" }}>
      <div className="p-2" style={{ borderBottom: "1px solid var(--eb-border)" }}>
        <button onClick={onCreate}
          className="w-full flex items-center justify-center gap-1 px-3 py-2 rounded-md text-xs font-semibold text-white"
          style={{ background: accentColor }}>
          <Plus className="w-3.5 h-3.5" />新しいチャット
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {threads.map(t => (
          <div key={t.id}
            role="button"
            tabIndex={0}
            onClick={() => onSelect(t.id)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onSelect(t.id); }}
            className="group rounded-md px-2 py-1.5 cursor-pointer flex items-start justify-between gap-1"
            style={{
              background: activeId === t.id ? "var(--eb-primary-container)" : "transparent",
              border: activeId === t.id ? `1px solid ${accentColor}` : "1px solid transparent",
            }}>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium truncate" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
                <MessageSquare className="w-3 h-3 inline mr-1 opacity-50" />
                {t.title || t.first_msg?.slice(0, 20) || "新しいチャット"}
              </p>
              <p className="text-[10px] opacity-60 truncate ml-4">
                {t.msg_count}件 · {new Date(t.last_active_at).toLocaleString("ja-JP", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}
              </p>
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(t.id); }}
              className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-50">
              <Trash2 className="w-3 h-3" style={{ color: "#dc2626" }} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// ChatBody: useLocalRuntime + UI
// ─────────────────────────────────────────────
type ChatBodyProps = ChatPanelProps & {
  channel: string;
  targetEmployee: number;
  activeThreadId: number | null;
  onThreadCreated: (id: number) => void;
  initialMessages: ThreadMessageLike[];
};

function ChatBody(props: ChatBodyProps) {
  const {
    activeThreadId, channel, targetEmployee, employeeColor = "#004CD9",
    avatarEmoji, defaultProvider, defaultModel, autoSendOnce, mode, employeeId,
    initialMessages,
  } = props;

  // ── LLM 選択（メイン + 補助LLM・hydration safe） ─────
  const llmStorageKey = `eb-llm-${mode}-${employeeId ?? "secretary"}`;
  const helperKey = `eb-llm-helper-${mode}-${employeeId ?? "secretary"}`;
  // 初期値は SSR と一致させるため defaultProvider/Model 固定
  const [llmSel, _setLlmSel] = useState({
    provider: defaultProvider || "ollama",
    model: defaultModel || "qwen2.5:7b",
  });
  // 補助LLM。null/undefined = メインと同じ
  const [helperSel, _setHelperSel] = useState<{ provider: string; model: string } | null>(null);
  // localStorage はマウント後に読む（hydration mismatch 回避）
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const helper = localStorage.getItem(helperKey);
      if (helper) {
        const p = JSON.parse(helper);
        if (p?.provider && p?.model) _setHelperSel(p);
      }
    } catch {}
  }, [helperKey]);
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const saved = localStorage.getItem(llmStorageKey);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed?.provider && parsed?.model) _setLlmSel(parsed);
      }
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [llmStorageKey]);
  const setLlmSel = (sel: { provider: string; model: string }) => {
    _setLlmSel(sel);
    if (typeof window !== "undefined") {
      try { localStorage.setItem(llmStorageKey, JSON.stringify(sel)); } catch {}
    }
  };
  const setHelperSel = (sel: { provider: string; model: string } | null) => {
    _setHelperSel(sel);
    if (typeof window !== "undefined") {
      try {
        if (sel) localStorage.setItem(helperKey, JSON.stringify(sel));
        else localStorage.removeItem(helperKey);
      } catch {}
    }
  };
  // 最新値を ref で参照（adapter の closure stale 対策）
  const llmSelRef = useRef(llmSel);
  llmSelRef.current = llmSel;
  const helperSelRef = useRef(helperSel);
  helperSelRef.current = helperSel;

  const { data: llmData } = useQuery<{ providers: LLMProvider[] }>({
    queryKey: ["llm-available"],
    queryFn: () => fetch(`${API}/api/llm/available`).then(r => r.json()),
  });

  // ── 添付・録音 ────────────────────────
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const [recording, setRecording] = useState(false);
  const recRef = useRef<any>(null);
  const attachmentsRef = useRef(attachments);
  attachmentsRef.current = attachments;

  const [lastToolName, setLastToolName] = useState<string | null>(null);
  const lastToolNameRef = useRef<string | null>(null);
  lastToolNameRef.current = lastToolName;

  // 履歴は ChatThreadLoader から initialMessages として渡される
  const historyReady = true;

  // ── スレッドID を ref で保持（adapter から最新値を参照） ──
  const threadIdRef = useRef<number | null>(activeThreadId);
  threadIdRef.current = activeThreadId;

  // ── ChatModelAdapter ──────────────────
  const adapter: ChatModelAdapter = useMemo(() => ({
    async *run({ messages, abortSignal }) {
      // 最新の user メッセージだけ送る（履歴は backend が thread_id から再構築）
      const lastUser = [...messages].reverse().find(m => m.role === "user");
      const text = lastUser?.content
        ?.filter((c: any) => c.type === "text")
        .map((c: any) => (c as any).text)
        .join("\n") || "";

      // 自動送信は新スレッドで開始
      const isAutoStart = !!autoSendOnce && text === autoSendOnce && !threadIdRef.current;

      let aText = "";
      let toolMeta: string | null = null;

      const resp = await fetch(`${API}/api/secretary/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          attachments: attachmentsRef.current,
          provider: llmSelRef.current.provider,
          model: llmSelRef.current.model,
          thread_id: threadIdRef.current,
          employee_id: targetEmployee,
          force_new_thread: isAutoStart,
          helper_provider: helperSelRef.current?.provider,
          helper_model: helperSelRef.current?.model,
        }),
        signal: abortSignal,
      });

      if (!resp.ok || !resp.body) {
        throw new Error(`HTTP ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() || "";
        for (const block of blocks) {
          if (!block.startsWith("data: ")) continue;
          let evt: any = null;
          try { evt = JSON.parse(block.slice(6).trim()); } catch { continue; }

          if (evt.type === "start" && evt.thread_id) {
            if (evt.thread_id !== threadIdRef.current) {
              threadIdRef.current = evt.thread_id;
              props.onThreadCreated(evt.thread_id);
            }
          }
          if (evt.type === "tool" && evt.name) {
            toolMeta = evt.name;
            setLastToolName(toolLabelOf(evt.name));
            // Yield with tool indicator metadata
            yield {
              content: [{ type: "text" as const, text: aText }],
              metadata: { custom: { tool: evt.name } },
            };
          }
          if (evt.type === "text" && evt.delta) {
            aText += evt.delta;
            yield {
              content: [{ type: "text" as const, text: aText }],
              metadata: { custom: { tool: toolMeta } },
            };
          }
          if (evt.type === "error" && evt.error) {
            throw new Error(evt.error);
          }
        }
      }

      // 終了後にツール表示クリア
      setLastToolName(null);

      // 応答が空のままならフォールバックメッセージ
      if (!aText) {
        yield {
          content: [{ type: "text" as const, text: "（応答がありませんでした。もう一度試してください）" }],
        };
      }

      setAttachments([]);
    },
  }), [autoSendOnce, targetEmployee, props]);

  // ── useLocalRuntime（assistant-ui がライフサイクル管理） ──
  const runtime = useLocalRuntime(adapter, {
    initialMessages,
  });

  // ── 自動送信（autoSendOnce） ─────────
  const autoSentRef = useRef<string | null>(null);
  useEffect(() => {
    if (!autoSendOnce || !historyReady) return;
    if (autoSentRef.current === autoSendOnce) return;
    autoSentRef.current = autoSendOnce;
    // assistant-ui ランタイム経由で append
    setTimeout(() => {
      try {
        runtime.thread.append({
          role: "user",
          content: [{ type: "text", text: autoSendOnce }],
        });
      } catch (e) {
        console.warn("[ChatBody] auto-send failed:", e);
      }
    }, 100);
  }, [autoSendOnce, historyReady, runtime]);

  // ── Tool-UI ボタンクリック → user メッセージ送信 ──
  const sendFromToolUI = useCallback((text: string) => {
    if (!text) return;
    runtime.thread.append({
      role: "user", content: [{ type: "text", text }],
    });
  }, [runtime]);

  // ── 添付ハンドリング ─────────────────
  const handleFile = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files; if (!files) return;
    for (const file of Array.from(files)) {
      const fd = new FormData();
      fd.append("file", file);
      try {
        const r = await fetch(`${API}/api/secretary/upload`, { method: "POST", body: fd });
        if (r.ok) {
          const data = await r.json();
          setAttachments(p => [...p, data]);
        }
      } catch {}
    }
    if (fileRef.current) fileRef.current.value = "";
  }, []);

  const removeAttachment = (id: string) => setAttachments(p => p.filter(a => a.id !== id));

  const toggleRecording = useCallback(async () => {
    if (recording) {
      recRef.current?.stop();
      setRecording(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      rec.ondataavailable = e => chunks.push(e.data);
      rec.onstop = async () => {
        const blob = new Blob(chunks, { type: "audio/webm" });
        const fd = new FormData();
        fd.append("audio", blob, "voice.webm");
        const r = await fetch(`${API}/api/secretary/transcribe`, { method: "POST", body: fd });
        if (r.ok) {
          const { text } = await r.json();
          if (text) {
            // composer の text を更新（assistant-ui API 経由）
            try {
              const cur = (runtime.thread.composer.getState?.() as any)?.text || "";
              runtime.thread.composer.setText(cur + text);
            } catch { /* fallback: ignore */ }
          }
        }
        stream.getTracks().forEach(t => t.stop());
      };
      rec.start();
      recRef.current = rec;
      setRecording(true);
    } catch (e: any) {
      alert("マイクへのアクセスが許可されていません: " + e.message);
    }
  }, [recording, runtime]);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
     <ToolUIActionProvider onAction={sendFromToolUI}>
      <ThreadPrimitive.Root className="flex-1 flex flex-col min-h-0 min-w-0">
        <ThreadPrimitive.Viewport className="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-3">
          <ThreadPrimitive.Empty>
            <div className="h-full flex flex-col items-center justify-center text-center px-6">
              <Sparkles className="w-8 h-8 mb-3" style={{ color: employeeColor }} />
              <p className="text-sm font-medium" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
                {avatarEmoji ? `${avatarEmoji} ` : ""}メッセージを送ってください
              </p>
              <p className="text-xs mt-1" style={{ color: "var(--eb-neutral)" }}>
                {mode === "secretary" ? "秘書AIに何でも依頼してください" : "AI社員に直接依頼できます"}
              </p>
            </div>
          </ThreadPrimitive.Empty>
          <ThreadPrimitive.Messages
            components={{
              UserMessage: UserMessageBubble,
              AssistantMessage: () => (
                <AssistantMessageBubble
                  avatarEmoji={avatarEmoji}
                  employeeColor={employeeColor}
                />
              ),
              SystemMessage: () => null,
            }} />
          <ThreadPrimitive.If running>
            <ThinkingIndicator
              color={employeeColor}
              avatarEmoji={avatarEmoji}
              label={lastToolName ? toolLabelOf(lastToolName) : pickThinkingVerb()}
            />
          </ThreadPrimitive.If>
        </ThreadPrimitive.Viewport>

        {attachments.length > 0 && (
          <div className="px-4 py-2 bg-white" style={{ borderTop: "1px solid var(--eb-border)" }}>
            <div className="flex gap-2 flex-wrap">
              {attachments.map(a => {
                const Icon = KIND_ICON[a.kind] || FileText;
                return (
                  <div key={a.id} className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs"
                    style={{ background: "var(--eb-surface-variant)" }}>
                    <Icon className="w-3 h-3" />
                    <span>{a.filename}</span>
                    <button onClick={() => removeAttachment(a.id)}>
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <NativeComposer
          runtime={runtime}
          recording={recording}
          attachments={attachments}
          fileRef={fileRef}
          handleFile={handleFile}
          toggleRecording={toggleRecording}
          llmProviders={llmData?.providers || []}
          llmSel={llmSel}
          setLlmSel={setLlmSel}
          helperSel={helperSel}
          setHelperSel={setHelperSel}
          employeeColor={employeeColor}
        />
      </ThreadPrimitive.Root>
     </ToolUIActionProvider>
    </AssistantRuntimeProvider>
  );
}

// ─────────────────────────────────────────────
// Helper: tool label
// ─────────────────────────────────────────────
function toolLabelOf(name: string): string {
  const labels: Record<string, string> = {
    search_web: "Web検索中",
    fetch_url: "ページ取得中",
    search_knowledge: "ナレッジ検索中",
    search_knowledge_scoped: "ナレッジ検索中",
    add_knowledge: "ナレッジ保存中",
    add_knowledge_smart: "ナレッジ分類中",
    staff_list: "社員リスト確認中",
    staff_orgchart: "組織図取得中",
    staff_hire: "採用処理中",
    staff_update: "編集処理中",
    staff_retire: "退職処理中",
    staff_transfer_propose: "ナレッジ引継候補抽出中",
    browser_action: "ブラウザ操作中",
    delegate_to_employee: "社員に委任中",
    search_past_conversations: "過去会話検索中",
    create_approval_request: "承認依頼作成中",
    knowledge_cleanup_preview: "ナレッジ整理候補抽出中",
    knowledge_cleanup_delete: "ナレッジ整理実行中",
  };
  return labels[name] || name;
}

// 通常応答時のシンキングラベル（バリエーション）
const THINKING_VERBS = [
  "考え中", "考えています", "整理中", "分析中", "確認中", "推論中", "検討中",
];
function pickThinkingVerb(): string {
  return THINKING_VERBS[Math.floor(Math.random() * THINKING_VERBS.length)];
}

// ─────────────────────────────────────────────
// メッセージバブル
// ─────────────────────────────────────────────
function UserMessageBubble() {
  return (
    <MessagePrimitive.Root className="flex gap-2 flex-row-reverse items-start">
      <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-1"
        style={{ background: "var(--eb-primary)" }}>
        <UserIcon className="w-4 h-4" style={{ color: "#ffffff" }} />
      </div>
      <div className="max-w-[80%]">
        <div className="px-4 py-2.5 rounded-2xl text-sm shadow-sm"
          style={{
            background: "var(--eb-primary)",
            color: "white",
            borderTopRightRadius: 6,
            wordBreak: "break-word",
          }}>
          <MessagePrimitive.Content />
        </div>
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessageBubble({ avatarEmoji, employeeColor }: {
  avatarEmoji?: string;
  employeeColor?: string;
}) {
  const bg = employeeColor ? employeeColor + "22" : "var(--eb-primary-container)";
  return (
    <MessagePrimitive.If hasContent>
      <MessagePrimitive.Root className="flex gap-2 items-start">
        <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-1 text-base"
          style={{ background: bg }}>
          {avatarEmoji ? (
            <span>{avatarEmoji}</span>
          ) : (
            <Bot className="w-4 h-4" style={{ color: employeeColor || "var(--eb-primary)" }} />
          )}
        </div>
        <div className="max-w-[85%] flex-1 min-w-0">
          <div className="px-4 py-3 rounded-2xl text-sm shadow-sm"
            style={{
              background: "#ffffff",
              border: "1px solid var(--eb-border)",
              borderTopLeftRadius: 6,
              color: "#1f2937",
              fontFamily: "var(--font-noto-sans-jp), system-ui, sans-serif",
              lineHeight: 1.75,
              wordBreak: "break-word",
            }}>
            <MessagePrimitive.Parts components={{ Text: TextWithToolUI }} />
          </div>
        </div>
      </MessagePrimitive.Root>
    </MessagePrimitive.If>
  );
}

function ThinkingIndicator({ color, avatarEmoji, label }: {
  color: string; avatarEmoji?: string; label: string;
}) {
  return (
    <div className="flex gap-2 items-center px-1 py-1">
      <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-base"
        style={{ background: color + "22" }}>
        {avatarEmoji ? <span>{avatarEmoji}</span> : <Sparkles className="w-3.5 h-3.5" style={{ color }} />}
      </div>
      <span className="text-xs italic"
        style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-noto-sans-jp)" }}>
        {label}
      </span>
      <span className="flex gap-1 items-center">
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: color, animation: "thinkPulse 1.4s ease-in-out infinite" }} />
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: color, animation: "thinkPulse 1.4s ease-in-out 0.2s infinite" }} />
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: color, animation: "thinkPulse 1.4s ease-in-out 0.4s infinite" }} />
      </span>
      <style jsx>{`
        @keyframes thinkPulse {
          0%, 80%, 100% { opacity: 0.3; transform: scale(0.85); }
          40% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </div>
  );
}

function TextWithToolUI({ text }: { text: string }) {
  const { remaining, blocks } = parseToolUIBlocks(text);
  return (
    <Fragment>
      {remaining && <MarkdownView>{remaining}</MarkdownView>}
      {blocks.map((b, i) => <ToolUIBlock key={i} block={b} />)}
    </Fragment>
  );
}

// ─────────────────────────────────────────────
// 入力欄ヘルパ
// ─────────────────────────────────────────────
// ─────────────────────────────────────────────
// NativeComposer: native textarea + 直接 runtime.thread.append
// IME を完全自前で処理（lib の compositionRef スタック問題回避）
// ─────────────────────────────────────────────
function NativeComposer({
  runtime, recording, attachments, fileRef, handleFile, toggleRecording,
  llmProviders, llmSel, setLlmSel, helperSel, setHelperSel, employeeColor,
}: {
  runtime: any;
  recording: boolean;
  attachments: Attachment[];
  fileRef: React.RefObject<HTMLInputElement | null>;
  handleFile: (e: React.ChangeEvent<HTMLInputElement>) => void;
  toggleRecording: () => void;
  llmProviders: LLMProvider[];
  llmSel: { provider: string; model: string };
  setLlmSel: (s: { provider: string; model: string }) => void;
  helperSel: { provider: string; model: string } | null;
  setHelperSel: (s: { provider: string; model: string } | null) => void;
  employeeColor: string;
}) {
  const [text, setText] = useState("");
  const [composing, setComposing] = useState(false);
  const taRef = useRef<HTMLTextAreaElement | null>(null);

  // composer.setText 経由で外部からテキスト注入できるよう ref 連携
  useEffect(() => {
    const composer: any = runtime?.thread?.composer;
    if (!composer) return;
    // 音声入力等で setText が呼ばれたら反映
    let unsub: any = null;
    try {
      unsub = composer.subscribe?.(() => {
        const s = composer.getState?.();
        if (s && typeof s.text === "string" && s.text !== text) {
          // 外部から反映（音声入力など）
          if (s.text.length > 0 && !composing) setText(s.text);
        }
      });
    } catch {}
    return () => { try { unsub?.(); } catch {} };
  }, [runtime, composing, text]);

  // 自動リサイズ（minRows=1, maxRows=6 相当）
  useEffect(() => {
    const ta = taRef.current; if (!ta) return;
    ta.style.height = "auto";
    const max = 6 * 24; // ≒ line-height * maxRows
    ta.style.height = Math.min(ta.scrollHeight, max) + "px";
  }, [text]);

  const send = useCallback(() => {
    const t = text.trim();
    if (!t) return;
    try {
      runtime.thread.append({
        role: "user",
        content: [{ type: "text", text: t }],
      });
      setText("");
      try { runtime.thread.composer.setText(""); } catch {}
    } catch (e) {
      console.error("[NativeComposer] append failed:", e);
    }
  }, [text, runtime]);

  const onKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // IME composition 中は Enter で送信しない（変換確定が優先）
    if (composing) return;
    if (e.nativeEvent.isComposing) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }, [composing, send]);

  const disabled = !text.trim();

  return (
    <div className="px-4 pt-3 pb-3 bg-white"
      style={{ borderTop: "1px solid var(--eb-border)" }}>
      <div className="max-w-3xl mx-auto">
        <div className="rounded-2xl flex flex-col"
          style={{ border: "1px solid var(--eb-border)", background: "#fff", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
          <textarea
            ref={taRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onCompositionStart={() => setComposing(true)}
            onCompositionEnd={(e) => {
              setComposing(false);
              setText((e.target as HTMLTextAreaElement).value);
            }}
            onKeyDown={onKeyDown}
            placeholder={recording ? "🎙️ 音声入力中..." : "メッセージを入力..."}
            rows={1}
            className="px-4 pt-3 pb-2 text-sm resize-none outline-none bg-transparent"
            style={{
              fontFamily: "var(--font-noto-sans-jp), system-ui, sans-serif",
              lineHeight: 1.6,
              color: "#1f2937",
              maxHeight: 144,
            }}
          />
          <div className="flex items-center gap-1 px-2 pb-2">
            <input ref={fileRef as any} type="file"
              accept="image/*,video/*,audio/*,application/pdf,.txt,.md"
              multiple className="hidden" onChange={handleFile} />
            <ToolBtn icon={Paperclip} label="添付" onClick={() => fileRef.current?.click()} />
            <ToolBtn icon={recording ? MicOff : Mic} label={recording ? "停止" : "音声"}
              onClick={toggleRecording} active={recording} activeColor="var(--eb-error)" />
            <div className="flex-1" />
            <LLMPicker
              providers={llmProviders}
              selected={llmSel}
              onChange={setLlmSel}
              helperSel={helperSel}
              setHelperSel={setHelperSel}
            />
            <button onClick={send} disabled={disabled}
              className="p-2 rounded-lg text-white disabled:opacity-40 ml-1 transition-opacity"
              style={{ background: employeeColor }}>
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function ToolBtn({ icon: Icon, label, onClick, active, activeColor }: any) {
  return (
    <button onClick={onClick} title={label}
      className="p-1.5 rounded-md hover:bg-gray-100"
      style={{ color: active ? activeColor : "var(--eb-neutral)" }}>
      <Icon className="w-4 h-4" />
    </button>
  );
}

// ツール非対応モデル（Function Calling 未サポート）
const TOOL_INCOMPATIBLE = /gemma|phi/i;
function modelSupportsTools(provider: string, model: string) {
  if (provider === "openai" || provider === "claude" || provider === "anthropic") return true;
  return !TOOL_INCOMPATIBLE.test(model || "");
}

function LLMPicker({ providers, selected, onChange, helperSel, setHelperSel }: {
  providers: LLMProvider[];
  selected: { provider: string; model: string };
  onChange: (s: { provider: string; model: string }) => void;
  helperSel?: { provider: string; model: string } | null;
  setHelperSel?: (s: { provider: string; model: string } | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [showHelper, setShowHelper] = useState(false);
  const currentLabel = useMemo(() => {
    const p = providers.find(p => p.id === selected.provider);
    const m = p?.models.find(m => m.id === selected.model);
    return m?.name || selected.model;
  }, [providers, selected]);
  const helperLabel = useMemo(() => {
    if (!helperSel) return "メインと同じ";
    const p = providers.find(p => p.id === helperSel.provider);
    const m = p?.models.find(m => m.id === helperSel.model);
    return m?.name || helperSel.model;
  }, [providers, helperSel]);
  const isToolless = !modelSupportsTools(selected.provider, selected.model);
  const isLocalMain = selected.provider === "ollama";
  return (
    <div className="relative">
      <button onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1 px-2 py-1.5 rounded-md text-[11px] hover:bg-gray-100"
        style={{
          color: isToolless ? "#92400E" : "var(--eb-neutral)",
          background: isToolless ? "#FEF3C7" : "transparent",
          fontFamily: "var(--font-inter)",
        }}
        title={isToolless ? "このモデルは Function Calling 未対応 — ツール実行不可" : ""}>
        <Cpu className="w-3 h-3" />
        <span>{currentLabel}{isToolless && " ⚠"}</span>
        <ChevronUp className={`w-3 h-3 transition-transform ${open ? "" : "rotate-180"}`} />
      </button>
      {open && (
        <div className="absolute right-0 bottom-full mb-1 z-50 bg-white rounded-md shadow-lg p-1 min-w-[260px] max-h-[400px] overflow-y-auto"
          style={{ border: "1px solid var(--eb-border)" }}>
          <p className="text-[10px] font-bold opacity-60 px-2 py-1.5">メインLLM</p>
          {providers.map(p => (
            <div key={p.id} className="mb-1 last:mb-0">
              <p className="text-[10px] font-bold opacity-50 px-2 py-1">{p.name}</p>
              {p.models.map(m => {
                const isSel = selected.provider === p.id && selected.model === m.id;
                return (
                  <button key={m.id}
                    disabled={!p.available}
                    onClick={() => { onChange({ provider: p.id, model: m.id }); setOpen(false); }}
                    className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded text-[11px] text-left hover:bg-gray-50 disabled:opacity-30"
                    style={{ background: isSel ? "var(--eb-primary-container)" : "transparent" }}>
                    {isSel && <Check className="w-3 h-3" style={{ color: "var(--eb-primary)" }} />}
                    <span className={isSel ? "font-medium" : ""}>{m.name}</span>
                  </button>
                );
              })}
            </div>
          ))}

          {/* 補助LLM 折りたたみ */}
          {setHelperSel && (
            <div className="border-t mt-1 pt-1" style={{ borderColor: "var(--eb-border)" }}>
              <button
                onClick={() => setShowHelper(s => !s)}
                className="w-full flex items-center justify-between px-2 py-1.5 text-[10px] hover:bg-gray-50">
                <span className="opacity-70">補助LLM（裏方処理用）: {helperLabel}</span>
                <ChevronUp className={`w-3 h-3 transition-transform ${showHelper ? "" : "rotate-180"}`} />
              </button>
              {showHelper && (
                <div className="px-1">
                  {isLocalMain && (
                    <div className="mx-1 mb-1 p-1.5 rounded text-[10px]"
                      style={{ background: "#FEF3C7", color: "#92400E" }}>
                      💡 ローカルLLMをメインに選んでいます。補助LLMだけ高速API（gpt-4o-mini等）にすると応答が速くなります。
                    </div>
                  )}
                  <button
                    onClick={() => { setHelperSel(null); }}
                    className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded text-[11px] text-left hover:bg-gray-50"
                    style={{ background: !helperSel ? "var(--eb-primary-container)" : "transparent" }}>
                    {!helperSel && <Check className="w-3 h-3" style={{ color: "var(--eb-primary)" }} />}
                    <span className={!helperSel ? "font-medium" : ""}>メインと同じ（自動）</span>
                  </button>
                  {providers.map(p => (
                    <div key={p.id} className="mb-1 last:mb-0">
                      <p className="text-[10px] font-bold opacity-50 px-2 py-0.5">{p.name}</p>
                      {p.models.map(m => {
                        const isSel = !!helperSel && helperSel.provider === p.id && helperSel.model === m.id;
                        return (
                          <button key={m.id}
                            disabled={!p.available}
                            onClick={() => { setHelperSel({ provider: p.id, model: m.id }); }}
                            className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded text-[11px] text-left hover:bg-gray-50 disabled:opacity-30"
                            style={{ background: isSel ? "var(--eb-primary-container)" : "transparent" }}>
                            {isSel && <Check className="w-3 h-3" style={{ color: "var(--eb-primary)" }} />}
                            <span className={isSel ? "font-medium" : ""}>{m.name}</span>
                          </button>
                        );
                      })}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
