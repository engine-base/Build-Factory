"use client";

/**
 * Tool-UI ブロックレンダラ集約
 *
 * 秘書・社員AIのメッセージ末尾に以下を埋め込むと自動描画：
 *   ```tool-ui
 *   { "type": "table", "title": "...", "data": {...} }
 *   ```
 *
 * インタラクティブ要素（ボタン等）クリック時は ToolUIActionContext.onAction(text) を呼び、
 * ChatPanel が新しい user メッセージとして自動送信する。
 */

import {
  CheckSquare, Square, Sliders, ListChecks, HelpCircle,
  ExternalLink, BarChart3, Terminal, CloudSun, MapPin, Layers,
  PieChart, Code, GitCompare, Table2, FileText, Hash,
  CheckCircle2, ShoppingBag, Image as ImageIcon, Video, Music,
  Target, Clock, ChevronRight, X, Edit3, CheckIcon, CircleIcon,
} from "lucide-react";
import { createContext, useContext, useState } from "react";

// ─────────────────────────────────────────────
// Action Context（ボタンクリック → メッセージ送信）
// ─────────────────────────────────────────────
type ActionFn = (text: string) => void;
const ToolUIActionContext = createContext<ActionFn | null>(null);

export function ToolUIActionProvider({ onAction, children }: {
  onAction: ActionFn;
  children: React.ReactNode;
}) {
  return (
    <ToolUIActionContext.Provider value={onAction}>
      {children}
    </ToolUIActionContext.Provider>
  );
}

function useToolUIAction(): ActionFn {
  return useContext(ToolUIActionContext) ?? (() => {});
}

// ─────────────────────────────────────────────
// 共通カードシェル
// ─────────────────────────────────────────────
function Card({ icon: Icon, title, children, accent = "var(--eb-primary)" }: any) {
  return (
    <div className="rounded-xl my-3 overflow-hidden bg-white"
      style={{
        border: "1px solid var(--eb-border)",
        borderLeft: `3px solid ${accent}`,
        boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
      }}>
      {title && (
        <div className="flex items-center gap-2 px-4 py-2.5"
          style={{ borderBottom: "1px solid var(--eb-border)", background: "var(--eb-surface-variant)" }}>
          {Icon && <Icon className="w-3.5 h-3.5" style={{ color: accent }} />}
          <p className="text-xs font-bold" style={{ fontFamily: "var(--font-inter)", color: "#374151" }}>
            {title}
          </p>
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}

// ─────────────────────────────────────────────
// INPUT (4)
// ─────────────────────────────────────────────
function OptionList({ data }: any) {
  // 単一選択モードならクリック即送信、複数選択なら選んで「決定」ボタンで送信
  const action = useToolUIAction();
  const multi = data.multi === true;
  const [selected, setSelected] = useState<string[]>([]);
  const submit = (label: string) => action(label);
  const submitMulti = () => {
    if (selected.length === 0) return;
    action(selected.join(", "));
  };
  return (
    <Card icon={ListChecks} title={data.title || "選択肢"}>
      <div className="space-y-1.5">
        {data.options?.map((o: any) => {
          const id = o.id ?? o.value ?? o.label;
          const label = o.label || o.title || String(id);
          const isSel = selected.includes(id);
          const onClick = () => {
            if (multi) {
              setSelected(prev => isSel ? prev.filter(s => s !== id) : [...prev, id]);
            } else {
              submit(label);
            }
          };
          return (
            <button key={id} onClick={onClick}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-left transition-colors hover:opacity-90"
              style={{
                background: isSel ? "var(--eb-primary-container)" : "var(--eb-surface-variant)",
                border: `1px solid ${isSel ? "var(--eb-primary)" : "transparent"}`,
                fontFamily: "var(--font-noto-sans-jp)"
              }}>
              {multi
                ? (isSel ? <CheckSquare className="w-3.5 h-3.5" style={{ color: "var(--eb-primary)" }} /> : <Square className="w-3.5 h-3.5 opacity-40" />)
                : <ChevronRight className="w-3.5 h-3.5 opacity-50" />}
              <div className="flex-1">
                <p className="font-medium">{label}</p>
                {o.description && <p className="text-[10px] opacity-70 mt-0.5">{o.description}</p>}
              </div>
            </button>
          );
        })}
      </div>
      {multi && selected.length > 0 && (
        <button onClick={submitMulti}
          className="mt-3 px-3 py-1.5 rounded text-xs text-white font-semibold w-full"
          style={{ background: "var(--eb-primary)" }}>
          選択した {selected.length} 件で決定
        </button>
      )}
    </Card>
  );
}

function ParameterSlider({ data }: any) {
  const [val, setVal] = useState<number>(data.default ?? data.min ?? 0);
  return (
    <Card icon={Sliders} title={data.title || "パラメータ"}>
      {(data.params || [{ name: data.label, ...data }]).map((p: any, i: number) => (
        <div key={i} className="mb-3 last:mb-0">
          <div className="flex justify-between mb-1">
            <span className="text-xs font-medium" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{p.name || p.label}</span>
            <span className="text-xs font-mono" style={{ color: "var(--eb-primary)" }}>{val}{p.unit || ""}</span>
          </div>
          <input type="range" min={p.min ?? 0} max={p.max ?? 100} step={p.step ?? 1}
            value={val} onChange={e => setVal(Number(e.target.value))}
            className="w-full" style={{ accentColor: "var(--eb-primary)" }} />
          {p.hint && <p className="text-[10px] mt-1" style={{ color: "var(--eb-neutral)" }}>{p.hint}</p>}
        </div>
      ))}
    </Card>
  );
}

function PreferencePanel({ data }: any) {
  const [prefs, setPrefs] = useState<Record<string, any>>(data.defaults || {});
  return (
    <Card icon={Sliders} title={data.title || "設定"}>
      <div className="space-y-2.5">
        {data.fields?.map((f: any) => (
          <div key={f.name} className="flex items-center justify-between">
            <span className="text-xs" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{f.label}</span>
            {f.type === "toggle" ? (
              <button onClick={() => setPrefs(p => ({ ...p, [f.name]: !p[f.name] }))}
                className="w-9 h-5 rounded-full relative transition-colors"
                style={{ background: prefs[f.name] ? "var(--eb-primary)" : "var(--eb-border)" }}>
                <div className="w-4 h-4 rounded-full bg-white absolute top-0.5 transition-all"
                  style={{ left: prefs[f.name] ? 18 : 2 }} />
              </button>
            ) : (
              <select value={prefs[f.name] ?? ""} onChange={e => setPrefs(p => ({ ...p, [f.name]: e.target.value }))}
                className="text-xs px-2 py-1 rounded" style={{ border: "1px solid var(--eb-border)" }}>
                {f.options?.map((o: any) => <option key={o} value={o}>{o}</option>)}
              </select>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

function QuestionFlow({ data }: any) {
  const [step, setStep] = useState(0);
  const q = data.questions?.[step];
  return (
    <Card icon={HelpCircle} title={`${data.title || "ヒアリング"} (${step + 1}/${data.questions?.length})`}>
      {q && (
        <div>
          <p className="text-sm font-medium mb-3" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{q.text}</p>
          {q.choices ? (
            <div className="grid gap-1.5">
              {q.choices.map((c: string) => (
                <button key={c} onClick={() => setStep(s => Math.min(s + 1, (data.questions?.length || 1) - 1))}
                  className="px-3 py-2 rounded-lg text-xs text-left"
                  style={{ background: "var(--eb-surface-variant)", fontFamily: "var(--font-noto-sans-jp)" }}>
                  {c}
                </button>
              ))}
            </div>
          ) : (
            <input className="w-full px-3 py-2 rounded text-xs" placeholder={q.placeholder}
              style={{ border: "1px solid var(--eb-border)" }} />
          )}
        </div>
      )}
    </Card>
  );
}

// ─────────────────────────────────────────────
// DISPLAY (7)
// ─────────────────────────────────────────────
function Citations({ data }: any) {
  return (
    <Card icon={ExternalLink} title={data.title || "引用元"}>
      <div className="space-y-2">
        {data.sources?.map((s: any, i: number) => (
          <a key={i} href={s.url} target="_blank" rel="noopener" className="block p-2 rounded-lg hover:bg-gray-50"
            style={{ background: "var(--eb-surface-variant)" }}>
            <div className="flex items-start gap-2">
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded shrink-0"
                style={{ background: "var(--eb-primary-container)", color: "var(--eb-on-primary-container)" }}>
                [{i + 1}]
              </span>
              <div className="min-w-0">
                <p className="text-xs font-medium truncate" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{s.title}</p>
                <p className="text-[10px] truncate" style={{ color: "var(--eb-neutral)" }}>{s.url}</p>
                {s.snippet && <p className="text-[11px] mt-1 line-clamp-2" style={{ color: "var(--eb-neutral)" }}>{s.snippet}</p>}
              </div>
            </div>
          </a>
        ))}
      </div>
    </Card>
  );
}

function LinkPreview({ data }: any) {
  return (
    <a href={data.url} target="_blank" rel="noopener" className="block">
      <Card icon={ExternalLink} title={data.title}>
        <div className="flex gap-3">
          {data.image && <img src={data.image} alt="" className="w-24 h-24 object-cover rounded" />}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{data.heading || data.title}</p>
            <p className="text-xs mt-1 line-clamp-3" style={{ color: "var(--eb-neutral)" }}>{data.description}</p>
            <p className="text-[10px] mt-1" style={{ color: "var(--eb-primary)" }}>{data.url}</p>
          </div>
        </div>
      </Card>
    </a>
  );
}

function Stats({ data }: any) {
  return (
    <Card icon={BarChart3} title={data.title || "数値"}>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {data.stats?.map((s: any, i: number) => (
          <div key={i} className="rounded-lg p-3" style={{ background: "var(--eb-surface-variant)" }}>
            <p className="text-[10px] uppercase tracking-wider" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
              {s.label}
            </p>
            <p className="text-xl font-bold mt-1" style={{ color: s.color || "var(--eb-primary)", fontFamily: "var(--font-inter)" }}>
              {s.value}
            </p>
            {s.delta && (
              <p className="text-[10px] mt-0.5" style={{ color: s.delta.startsWith("+") ? "#16A34A" : "#DC2626" }}>
                {s.delta}
              </p>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

function Terminal_({ data }: any) {
  return (
    <Card icon={Terminal} title={data.title || "Terminal"} accent="#374151">
      <pre className="text-[11px] p-3 rounded overflow-auto whitespace-pre-wrap"
        style={{ background: "#1f2937", color: "#d1fae5", fontFamily: "ui-monospace, monospace" }}>
        {data.lines?.map((l: any, i: number) => (
          <div key={i}>
            {l.startsWith("$") ? <span style={{ color: "#fbbf24" }}>{l}</span> : l}
          </div>
        ))}
      </pre>
    </Card>
  );
}

function Weather({ data }: any) {
  return (
    <Card icon={CloudSun} title={data.location || "天気"}>
      <div className="flex items-center gap-4">
        <p className="text-3xl font-bold" style={{ fontFamily: "var(--font-inter)" }}>{data.temp}°</p>
        <div>
          <p className="text-sm font-medium" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{data.condition}</p>
          <p className="text-[11px]" style={{ color: "var(--eb-neutral)" }}>体感 {data.feels_like}° / 湿度 {data.humidity}%</p>
        </div>
      </div>
    </Card>
  );
}

function Map_({ data }: any) {
  return (
    <Card icon={MapPin} title={data.title || "地図"}>
      <p className="text-sm" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{data.location}</p>
      <p className="text-[11px] mt-1" style={{ color: "var(--eb-neutral)", fontFamily: "var(--font-inter)" }}>
        {data.lat}, {data.lng}
      </p>
      {data.places && (
        <ul className="mt-2 space-y-1">
          {data.places.map((p: any, i: number) => (
            <li key={i} className="text-xs flex items-center gap-2">
              <MapPin className="w-3 h-3" />{p.name} <span className="opacity-60">({p.distance})</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Carousel({ data }: any) {
  return (
    <Card icon={Layers} title={data.title || "カルーセル"}>
      <div className="flex gap-3 overflow-x-auto pb-1">
        {data.items?.map((it: any, i: number) => (
          <div key={i} className="rounded-lg overflow-hidden shrink-0 w-44"
            style={{ border: "1px solid var(--eb-border)" }}>
            {it.image && <img src={it.image} alt="" className="w-full h-24 object-cover" />}
            <div className="p-2">
              <p className="text-xs font-medium truncate" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{it.title}</p>
              {it.subtitle && <p className="text-[10px] mt-0.5 truncate" style={{ color: "var(--eb-neutral)" }}>{it.subtitle}</p>}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ─────────────────────────────────────────────
// ARTIFACTS (6)
// ─────────────────────────────────────────────
function ChartBlock({ data }: any) {
  // 簡易バーチャート
  const max = Math.max(...(data.data?.map((d: any) => d.value) || [1]));
  return (
    <Card icon={PieChart} title={data.title || "チャート"}>
      <div className="space-y-1.5">
        {data.data?.map((d: any, i: number) => (
          <div key={i} className="flex items-center gap-2">
            <span className="text-[11px] w-20 truncate" style={{ fontFamily: "var(--font-inter)" }}>{d.label}</span>
            <div className="flex-1 h-5 rounded relative" style={{ background: "var(--eb-surface-variant)" }}>
              <div className="absolute inset-y-0 left-0 rounded"
                style={{ width: `${(d.value / max) * 100}%`, background: d.color || "var(--eb-primary)" }} />
            </div>
            <span className="text-[11px] font-mono" style={{ fontFamily: "var(--font-inter)" }}>{d.value}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function CodeBlock({ data }: any) {
  return (
    <Card icon={Code} title={`${data.title || "コード"}${data.lang ? ` (${data.lang})` : ""}`} accent="#7E3AED">
      <pre className="text-[11px] p-3 rounded overflow-auto"
        style={{ background: "#1f2937", color: "#f3f4f6", fontFamily: "ui-monospace, monospace" }}>
        <code>{data.code}</code>
      </pre>
    </Card>
  );
}

function DiffViewer({ data }: any) {
  return (
    <Card icon={GitCompare} title={data.title || "Diff"}>
      <pre className="text-[11px] p-3 rounded overflow-auto"
        style={{ background: "var(--eb-surface-variant)", fontFamily: "ui-monospace, monospace" }}>
        {data.lines?.map((l: any, i: number) => (
          <div key={i} style={{
            background: l.type === "add" ? "#dcfce7" : l.type === "del" ? "#fee2e2" : "transparent",
            color: l.type === "add" ? "#166534" : l.type === "del" ? "#991b1b" : "#374151"
          }}>
            <span className="opacity-50 mr-2">{l.type === "add" ? "+" : l.type === "del" ? "-" : " "}</span>
            {l.text}
          </div>
        ))}
      </pre>
    </Card>
  );
}

function TableBlock({ data }: any) {
  return (
    <Card icon={Table2} title={data.title || "テーブル"}>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr style={{ background: "var(--eb-surface-variant)" }}>
              {data.columns?.map((c: any) => (
                <th key={c} className="px-3 py-1.5 text-left font-semibold"
                  style={{ fontFamily: "var(--font-inter)", color: "var(--eb-neutral)" }}>
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows?.map((r: any, i: number) => (
              <tr key={i} style={{ borderTop: "1px solid var(--eb-border)" }}>
                {data.columns?.map((c: any) => (
                  <td key={c} className="px-3 py-1.5" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
                    {String(r[c] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Draft({ data }: any) {
  return (
    <Card icon={FileText} title={data.title || "ドラフト"}>
      {data.subject && (
        <p className="text-xs mb-2 pb-2" style={{ borderBottom: "1px dashed var(--eb-border)" }}>
          <span className="font-bold">件名:</span> {data.subject}
        </p>
      )}
      <pre className="text-xs whitespace-pre-wrap" style={{ fontFamily: "var(--font-noto-sans-jp)", lineHeight: 1.7 }}>
        {data.body}
      </pre>
    </Card>
  );
}

function SocialPost({ data }: any) {
  return (
    <Card icon={Hash} title={`${data.platform || "投稿"}下書き`}>
      <p className="text-xs whitespace-pre-wrap" style={{ fontFamily: "var(--font-noto-sans-jp)", lineHeight: 1.7 }}>
        {data.body}
      </p>
      {data.tags && (
        <div className="flex flex-wrap gap-1 mt-2">
          {data.tags.map((t: string) => (
            <span key={t} className="text-[10px] px-2 py-0.5 rounded-full"
              style={{ background: "var(--eb-primary-container)", color: "var(--eb-on-primary-container)" }}>
              #{t}
            </span>
          ))}
        </div>
      )}
      <p className="text-[10px] mt-2" style={{ color: "var(--eb-neutral)" }}>
        {data.body?.length || 0}文字
      </p>
    </Card>
  );
}

// ─────────────────────────────────────────────
// CONFIRMATION (2)
// ─────────────────────────────────────────────
function ApprovalCard({ data }: any) {
  const action = useToolUIAction();
  const approveText = data.approve_label || "承認・実行してください";
  const rejectText  = data.reject_label || "中止";
  const editText    = data.edit_label   || "修正したい";
  return (
    <Card icon={CheckCircle2} title={data.title || "確認カード"} accent="#D97706">
      {data.description && (
        <p className="text-sm mb-3" style={{ fontFamily: "var(--font-noto-sans-jp)", lineHeight: 1.7 }}>
          {data.description}
        </p>
      )}
      {data.details && (
        <div className="rounded p-3 mb-3" style={{ background: "var(--eb-surface-variant)" }}>
          {Object.entries(data.details).map(([k, v]) => (
            <div key={k} className="flex text-xs py-1 gap-2" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
              <span className="w-28 opacity-70 shrink-0">{k}</span>
              <span className="flex-1 break-words">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
            </div>
          ))}
        </div>
      )}
      <div className="grid grid-cols-3 gap-2">
        <button onClick={() => action(approveText)}
          className="flex items-center justify-center gap-1 px-3 py-2 rounded-lg text-xs font-semibold text-white hover:opacity-90"
          style={{ background: "#16A34A" }}>
          <CheckCircle2 className="w-3.5 h-3.5" />承認
        </button>
        <button onClick={() => action(editText)}
          className="flex items-center justify-center gap-1 px-3 py-2 rounded-lg text-xs font-semibold hover:opacity-90"
          style={{ background: "var(--eb-surface-variant)", color: "var(--eb-neutral)" }}>
          <Edit3 className="w-3.5 h-3.5" />修正
        </button>
        <button onClick={() => action(rejectText)}
          className="flex items-center justify-center gap-1 px-3 py-2 rounded-lg text-xs font-semibold hover:opacity-90"
          style={{ background: "#FEE2E2", color: "#991B1B" }}>
          <X className="w-3.5 h-3.5" />中止
        </button>
      </div>
    </Card>
  );
}

function OrderSummary({ data }: any) {
  const total = data.items?.reduce((s: number, i: any) => s + (i.price * (i.qty || 1)), 0) || 0;
  return (
    <Card icon={ShoppingBag} title={data.title || "注文内容"}>
      <div className="space-y-1 mb-3">
        {data.items?.map((it: any, i: number) => (
          <div key={i} className="flex justify-between text-xs">
            <span style={{ fontFamily: "var(--font-noto-sans-jp)" }}>
              {it.name} × {it.qty || 1}
            </span>
            <span style={{ fontFamily: "var(--font-inter)" }}>¥{(it.price * (it.qty || 1)).toLocaleString()}</span>
          </div>
        ))}
      </div>
      <div className="flex justify-between font-bold text-sm pt-2"
        style={{ borderTop: "1px solid var(--eb-border)", fontFamily: "var(--font-inter)" }}>
        <span>合計</span>
        <span style={{ color: "var(--eb-primary)" }}>¥{total.toLocaleString()}</span>
      </div>
    </Card>
  );
}

// ─────────────────────────────────────────────
// MEDIA (3)
// ─────────────────────────────────────────────
function ImageGallery({ data }: any) {
  return (
    <Card icon={ImageIcon} title={data.title || "ギャラリー"}>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        {data.images?.map((img: any, i: number) => (
          <a key={i} href={img.url} target="_blank" rel="noopener">
            <img src={img.thumbnail || img.url} alt={img.alt || ""}
              className="w-full h-24 object-cover rounded hover:opacity-80 transition" />
            {img.caption && <p className="text-[10px] mt-1" style={{ color: "var(--eb-neutral)" }}>{img.caption}</p>}
          </a>
        ))}
      </div>
    </Card>
  );
}

function VideoBlock({ data }: any) {
  return (
    <Card icon={Video} title={data.title || "動画"}>
      <video controls src={data.url} poster={data.poster} className="w-full rounded" />
      {data.description && <p className="text-xs mt-2" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{data.description}</p>}
    </Card>
  );
}

function AudioBlock({ data }: any) {
  return (
    <Card icon={Music} title={data.title || "音声"}>
      <audio controls src={data.url} className="w-full" />
      {data.description && <p className="text-xs mt-2" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{data.description}</p>}
    </Card>
  );
}

// ─────────────────────────────────────────────
// PROGRESS (2)
// ─────────────────────────────────────────────
function Plan({ data }: any) {
  return (
    <Card icon={Target} title={data.title || "プラン"}>
      <ol className="space-y-2">
        {data.steps?.map((s: any, i: number) => (
          <li key={i} className="flex gap-2">
            <span className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0"
              style={{ background: s.done ? "#DCFCE7" : "var(--eb-surface-variant)",
                       color: s.done ? "#16A34A" : "var(--eb-neutral)" }}>
              {s.done ? <CheckIcon className="w-3 h-3" aria-label="done" /> : i + 1}
            </span>
            <div className="flex-1">
              <p className="text-xs font-medium" style={{ fontFamily: "var(--font-noto-sans-jp)" }}>{s.title}</p>
              {s.description && <p className="text-[10px] mt-0.5" style={{ color: "var(--eb-neutral)" }}>{s.description}</p>}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

function ProgressTracker({ data }: any) {
  const pct = Math.round(((data.current || 0) / (data.total || 1)) * 100);
  return (
    <Card icon={Clock} title={data.title || "進捗"}>
      <div className="flex items-center gap-3 mb-2">
        <div className="flex-1 h-2 rounded-full" style={{ background: "var(--eb-surface-variant)" }}>
          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: "var(--eb-primary)" }} />
        </div>
        <span className="text-xs font-mono" style={{ fontFamily: "var(--font-inter)" }}>{pct}%</span>
      </div>
      {data.tasks && (
        <ul className="space-y-1">
          {data.tasks.map((t: any, i: number) => (
            <li key={i} className="flex items-center gap-2 text-xs">
              <span style={{ color: t.done ? "#16A34A" : "var(--eb-neutral)" }} className="inline-flex items-center">
                {t.done ? <CheckIcon className="w-3 h-3" aria-label="done" /> : <CircleIcon className="w-3 h-3" aria-label="todo" />}
              </span>
              <span style={{ fontFamily: "var(--font-noto-sans-jp)", textDecoration: t.done ? "line-through" : "none", opacity: t.done ? 0.6 : 1 }}>
                {t.name}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ─────────────────────────────────────────────
// メインルーター
// ─────────────────────────────────────────────
const REGISTRY: Record<string, any> = {
  "option-list":      OptionList,
  "parameter-slider": ParameterSlider,
  "preference-panel": PreferencePanel,
  "question-flow":    QuestionFlow,
  "citations":        Citations,
  "link-preview":     LinkPreview,
  "stats":            Stats,
  "terminal":         Terminal_,
  "weather":          Weather,
  "map":              Map_,
  "carousel":         Carousel,
  "chart":            ChartBlock,
  "code-block":       CodeBlock,
  "diff":             DiffViewer,
  "table":            TableBlock,
  "draft":            Draft,
  "social-post":      SocialPost,
  "approval-card":    ApprovalCard,
  "order-summary":    OrderSummary,
  "image-gallery":    ImageGallery,
  "video":            VideoBlock,
  "audio":            AudioBlock,
  "plan":             Plan,
  "progress-tracker": ProgressTracker,
};

export function ToolUIBlock({ block }: { block: any }) {
  if (!block?.type) return null;
  const Component = REGISTRY[block.type];
  if (!Component) {
    return (
      <Card title={`不明なツールUI: ${block.type}`}>
        <pre className="text-[10px] overflow-auto" style={{ color: "var(--eb-neutral)" }}>
          {JSON.stringify(block.data || block, null, 2)}
        </pre>
      </Card>
    );
  }
  return <Component data={block.data || block} />;
}

/**
 * メッセージテキストから ```tool-ui {...} ``` ブロックを抽出して
 * 残テキスト + ブロック配列を返す
 */
export function parseToolUIBlocks(text: string): { remaining: string; blocks: any[] } {
  const blocks: any[] = [];
  const regex = /```tool-ui\s*([\s\S]*?)```/g;
  let remaining = text.replace(regex, (_, json) => {
    try {
      blocks.push(JSON.parse(json.trim()));
    } catch (e) {
      console.warn("[tool-ui] JSON parse error:", e);
    }
    return "";
  });
  // 先頭の JSON 断片（{}, [], null）を除去
  remaining = remaining.replace(/^\s*(\{\s*\}|\[\s*\]|null|true|false)\s*/i, "");
  return { remaining: remaining.trim(), blocks };
}

export const TOOL_UI_TYPES = Object.keys(REGISTRY);
