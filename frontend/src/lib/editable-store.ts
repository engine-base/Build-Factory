/**
 * editable-store — InlineEditable の編集値を保存するストア
 *
 * モード:
 *  - demo:  localStorage 永続化 (?demo=1 ページ用)
 *  - live:  バックエンド PATCH 経由で center_artifact に保存
 *
 * 「最終更新者勝ち」(last write wins) 戦略:
 *  - PM が編集 → タイムスタンプ更新 + edited_by_pm: true
 *  - AI が後続で patch → そのまま上書き (タイムスタンプ更新 + edited_by_pm: false)
 *  - 双方向で「直近の更新を採用」する
 */
import { useEffect, useSyncExternalStore } from "react";

const LS_PREFIX = "bf-rd-edit:";

/** id 形式: `${workspaceId}:${tabKey}:${sectionKey}:${itemPath}` */
export type EditId = string;

interface EditValue {
  value: string;
  updatedAt: number;
  source: "pm" | "ai";
}

/* ────── store impl (シンプルなイベントエミッター + localStorage backing) ────── */
type Listener = () => void;
const listeners = new Set<Listener>();
const memCache = new Map<EditId, EditValue>();

function notify() {
  listeners.forEach((l) => l());
}

function readLS(key: string): EditValue | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    const raw = localStorage.getItem(LS_PREFIX + key);
    if (!raw) return undefined;
    return JSON.parse(raw);
  } catch { return undefined; }
}

function writeLS(key: string, v: EditValue) {
  if (typeof window === "undefined") return;
  try { localStorage.setItem(LS_PREFIX + key, JSON.stringify(v)); } catch {}
}

export function getEdited(id: EditId): string | undefined {
  if (memCache.has(id)) return memCache.get(id)!.value;
  const v = readLS(id);
  if (v) {
    memCache.set(id, v);
    return v.value;
  }
  return undefined;
}

export function setEdited(id: EditId, value: string, source: "pm" | "ai" = "pm") {
  const next: EditValue = { value, updatedAt: Date.now(), source };
  memCache.set(id, next);
  writeLS(id, next);
  notify();
}

export function clearAllEdits(prefix?: string) {
  if (typeof window === "undefined") return;
  const keys: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (k && k.startsWith(LS_PREFIX) && (!prefix || k.startsWith(LS_PREFIX + prefix))) {
      keys.push(k);
    }
  }
  keys.forEach((k) => localStorage.removeItem(k));
  if (!prefix) memCache.clear();
  else for (const k of memCache.keys()) if (k.startsWith(prefix)) memCache.delete(k);
  notify();
}

/* ────── React hooks ────── */

/**
 * useEditable — 編集値を取得し、setter を返す
 * - デフォルト値 (= テンプレ初期値) を渡す
 * - 編集があればそれを優先表示
 */
export function useEditable(id: EditId, defaultValue: string): [string, (next: string) => void] {
  const subscribe = (cb: Listener) => { listeners.add(cb); return () => { listeners.delete(cb); }; };
  const getSnapshot = () => memCache.get(id)?.value ?? readLS(id)?.value ?? defaultValue;
  const getServerSnapshot = () => defaultValue;
  const value = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  // 初回 mount で localStorage 値があればキャッシュに乗せる
  useEffect(() => {
    if (!memCache.has(id)) {
      const ls = readLS(id);
      if (ls) memCache.set(id, ls);
    }
  }, [id]);

  const setter = (next: string) => setEdited(id, next, "pm");
  return [value, setter];
}

/* ────── Live モード (API) 用ヘルパー ────── */

export async function pushEditToApi(opts: {
  workspaceId: number;
  step: number;
  centerSnapshot: any;
  apiBase?: string;
}): Promise<void> {
  const base = opts.apiBase ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
  await fetch(`${base}/api/workspaces/${opts.workspaceId}/requirements/center?step=${opts.step}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      center: { ...opts.centerSnapshot, edited_by_pm: true, last_edited_at: new Date().toISOString() },
      edited_by_pm: true,
    }),
  });
}
