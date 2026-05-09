/** references API クライアント (参考資料アップロード) */
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export type DocType =
  | "generic"
  | "proposal_reference"
  | "requirements_reference"
  | "estimate_reference"
  | "hearing_reference"
  | "pricing_reference"
  | "template_reference";

export interface ReferenceItem {
  id: string;
  title: string;
  tags: string[];
  doc_type?: string;
  filename?: string;
  kind?: string;
  preview?: string;
  char_count?: number;
  stored_url?: string | null;
  uploaded_at?: string;
}

export async function uploadReference(opts: {
  account_id: number;
  file: File;
  doc_type?: DocType;
  title?: string;
  tags?: string[];
}): Promise<{ status: string; artifact: any; extracted: any; stored: any }> {
  const fd = new FormData();
  fd.append("account_id", String(opts.account_id));
  fd.append("file", opts.file);
  fd.append("doc_type", opts.doc_type ?? "generic");
  if (opts.title) fd.append("title", opts.title);
  if (opts.tags && opts.tags.length) fd.append("tags", opts.tags.join(","));

  const res = await fetch(`${BASE}/api/references/upload`, {
    method: "POST",
    body: fd,
  });
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(`upload failed: ${res.status} ${t}`);
  }
  return res.json();
}

export async function listReferences(opts?: {
  account_id?: number;
  doc_type?: DocType;
  limit?: number;
}): Promise<{ items: ReferenceItem[]; count: number }> {
  const sp = new URLSearchParams();
  if (opts?.account_id != null) sp.set("account_id", String(opts.account_id));
  if (opts?.doc_type) sp.set("doc_type", opts.doc_type);
  if (opts?.limit) sp.set("limit", String(opts.limit));
  const res = await fetch(`${BASE}/api/references?${sp.toString()}`);
  if (!res.ok) throw new Error(`list failed: ${res.status}`);
  return res.json();
}

export async function getReferenceText(artifactId: string): Promise<string> {
  const res = await fetch(`${BASE}/api/references/${artifactId}/text`);
  if (!res.ok) return "";
  const d = await res.json();
  return d.text || "";
}
