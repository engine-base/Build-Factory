/** account_settings API クライアント */
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export interface AchievementStat { value: string; label: string; }
export interface CaseStudy {
  type?: string;          // 業種・種別 (EC / BtoB SaaS / etc.)
  client_name?: string;   // クライアント名 (匿名化可)
  title?: string;         // 案件タイトル
  duration?: string;      // 期間 (例: 2026年4月〜8月)
  desc?: string;          // 概要・取り組み内容
  result?: string;        // 主要な成果 (例: 月商 200→500 万円)
  tech?: string;          // 使用技術スタック
  image_url?: string;     // メイン画像 (スクショ・成果ビジュアル)
  url?: string;           // 公開リンク (任意)
}

export interface AccountSettings {
  account_id: number;
  company_name: string;
  company_name_kana?: string;
  representative_name?: string;
  representative_title?: string;
  postal_code?: string;
  address?: string;
  phone?: string;
  email?: string;
  website?: string;
  bank_name?: string;
  bank_branch?: string;
  bank_account_type?: string;
  bank_account_number?: string;
  bank_account_holder?: string;
  logo_url?: string;
  stamp_url?: string;
  stamp_text?: string;
  primary_color?: string;
  secondary_color?: string;
  font_family?: string;
  achievement_stats?: AchievementStat[];
  case_studies?: CaseStudy[];
  payment_terms_default?: string;
  warranty_days?: number;
  monthly_maintenance_yen?: number;
  estimate_validity_days?: number;
  tax_rate?: number;
  estimate_prefix?: string;
  proposal_prefix?: string;
  default_notes?: string[];
  template_config?: Record<string, any>;
}

export async function fetchAccountSettings(accountId: number): Promise<AccountSettings> {
  const r = await fetch(`${BASE}/api/accounts/${accountId}/settings`);
  return r.json();
}

export async function patchAccountSettings(accountId: number, patch: Partial<AccountSettings>): Promise<AccountSettings> {
  const r = await fetch(`${BASE}/api/accounts/${accountId}/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return r.json();
}

export async function uploadImage(opts: {
  accountId: number;
  kind: "logo" | "stamp" | "ceo_photo" | "case_study" | "hero_bg" | "icon" | "other";
  file: File | Blob;
  filename?: string;
}): Promise<{ url: string; path: string; size: number; storage: string }> {
  const fd = new FormData();
  fd.append("account_id", String(opts.accountId));
  fd.append("kind", opts.kind);
  const file = opts.file instanceof File ? opts.file : new File([opts.file], opts.filename || "upload");
  fd.append("file", file);
  const r = await fetch(`${BASE}/api/uploads`, { method: "POST", body: fd });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`upload failed: ${r.status} ${text}`);
  }
  return r.json();
}
