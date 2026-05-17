"use client";

import { useEffect, useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Building2, Banknote, Palette, Award, Settings as SettingsIcon, Save, Check, Loader2, Plus, Trash2,
} from "lucide-react";
import {
  fetchAccountSettings, patchAccountSettings,
  type AccountSettings, type AchievementStat, type CaseStudy,
} from "@/lib/account-settings-api";
import { ImageDropper } from "@/components/settings/ImageDropper";

const ACCOUNT_ID = 1; // TODO: 認証統合後に動的取得

const TABS: { key: TabKey; label: string; icon: any }[] = [
  { key: "basic",  label: "基本情報", icon: Building2 },
  { key: "bank",   label: "振込先",   icon: Banknote },
  { key: "brand",  label: "ブランド", icon: Palette },
  { key: "ach",    label: "実績・事例", icon: Award },
  { key: "default", label: "デフォルト条件", icon: SettingsIcon },
];

type TabKey = "basic" | "bank" | "brand" | "ach" | "default";

export default function AccountSettingsPage() {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabKey>("basic");
  const [draft, setDraft] = useState<AccountSettings | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  const { data: settings, isLoading } = useQuery<AccountSettings>({
    queryKey: ["account-settings", ACCOUNT_ID],
    queryFn: () => fetchAccountSettings(ACCOUNT_ID),
  });

  useEffect(() => {
    if (settings && !draft) setDraft(settings);
  }, [settings, draft]);

  const saveMut = useMutation({
    mutationFn: (patch: Partial<AccountSettings>) => patchAccountSettings(ACCOUNT_ID, patch),
    onSuccess: (data) => {
      qc.setQueryData(["account-settings", ACCOUNT_ID], data);
      setDraft(data);
      setSavedAt(Date.now());
      setTimeout(() => setSavedAt(null), 2500);
    },
  });

  // 自動保存 (debounce 1.5s)
  useEffect(() => {
    if (!draft || !settings) return;
    const changed: Partial<AccountSettings> = {};
    for (const k of Object.keys(draft) as (keyof AccountSettings)[]) {
      if (k === "account_id") continue;
      const a = (draft as any)[k];
      const b = (settings as any)[k];
      if (JSON.stringify(a) !== JSON.stringify(b)) (changed as any)[k] = a;
    }
    if (Object.keys(changed).length === 0) return;
    const t = setTimeout(() => saveMut.mutate(changed), 1500);
    return () => clearTimeout(t);
  }, [draft, settings]);

  const update = (patch: Partial<AccountSettings>) => {
    setDraft((d) => (d ? { ...d, ...patch } : d));
  };

  if (isLoading || !draft) {
    return (
      <div style={{ padding: 40, color: "var(--bf-text-3)" }}>
        <Loader2 className="w-5 h-5 inline mr-2 animate-spin" />設定を読み込み中…
      </div>
    );
  }

  return (
    <div style={{ padding: "var(--bf-space-6)", height: "100vh", overflowY: "auto" }}>
      {/* ヘッダー */}
      <div style={{ marginBottom: 24, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: "var(--bf-text-1)", marginBottom: 4 }}>アカウント設定</h1>
          <p style={{ fontSize: 12.5, color: "var(--bf-text-3)" }}>
            提案書・見積書・請求書のすべてに自動的に流し込まれる発行者情報・ブランド・実績を管理します
          </p>
        </div>
        <SaveStatus saving={saveMut.isPending} savedAt={savedAt} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 480px", gap: 16, alignItems: "flex-start" }}>
        {/* 左: フォーム */}
        <div style={{
          background: "var(--bf-bg-elev)", border: "1px solid var(--bf-border)",
          borderRadius: 12, overflow: "hidden",
        }}>
          {/* タブナビ */}
          <div style={{ display: "flex", borderBottom: "1px solid var(--bf-divider)", background: "var(--bf-bg)" }}>
            {TABS.map((t) => {
              const isActive = activeTab === t.key;
              const Icon = t.icon;
              return (
                <button
                  key={t.key}
                  onClick={() => setActiveTab(t.key)}
                  style={{
                    padding: "12px 16px", fontSize: 12.5,
                    fontWeight: isActive ? 700 : 500,
                    color: isActive ? "var(--bf-primary)" : "var(--bf-text-3)",
                    background: isActive ? "var(--bf-bg-elev)" : "transparent",
                    border: "none", borderBottom: isActive ? "2px solid var(--bf-primary)" : "2px solid transparent",
                    borderRight: "1px solid var(--bf-divider)",
                    cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 6,
                    fontFamily: "inherit",
                  }}
                >
                  <Icon className="w-3.5 h-3.5" />{t.label}
                </button>
              );
            })}
          </div>

          {/* タブ中身 */}
          <div style={{ padding: 24 }}>
            {activeTab === "basic" && <BasicTab d={draft} onChange={update} />}
            {activeTab === "bank" && <BankTab d={draft} onChange={update} />}
            {activeTab === "brand" && <BrandTab d={draft} onChange={update} />}
            {activeTab === "ach" && <AchievementsTab d={draft} onChange={update} />}
            {activeTab === "default" && <DefaultsTab d={draft} onChange={update} />}
          </div>
        </div>

        {/* 右: リアルタイムプレビュー */}
        <div style={{ position: "sticky", top: 16, height: "fit-content" }}>
          <PreviewPanel settings={draft} />
        </div>
      </div>
    </div>
  );
}

/* ─── Save Status ─── */
function SaveStatus({ saving, savedAt }: { saving: boolean; savedAt: number | null }) {
  if (saving) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--bf-text-3)" }}>
        <Loader2 className="w-3.5 h-3.5 animate-spin" />保存中…
      </div>
    );
  }
  if (savedAt) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--bf-success)", fontWeight: 600 }}>
        <Check className="w-3.5 h-3.5" />保存しました
      </div>
    );
  }
  return (
    <div style={{ fontSize: 11.5, color: "var(--bf-text-4)" }}>変更すると自動保存されます</div>
  );
}

/* ─── 共通フォーム部品 ─── */
function Field({ label, hint, children, full }: {
  label: string; hint?: string; children: React.ReactNode; full?: boolean;
}) {
  return (
    <div style={{ gridColumn: full ? "1 / -1" : undefined }}>
      <label style={{
        fontSize: 11.5, fontWeight: 700, color: "var(--bf-text-3)",
        letterSpacing: "0.04em", display: "block", marginBottom: 6,
      }}>
        {label}
      </label>
      {children}
      {hint && <div style={{ fontSize: 11, color: "var(--bf-text-4)", marginTop: 4 }}>{hint}</div>}
    </div>
  );
}

function TextInput({ value, onChange, placeholder, type = "text" }: {
  value: string | number | undefined;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <input
      type={type}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      style={{
        width: "100%", height: 36, padding: "0 12px",
        background: "var(--bf-bg)", border: "1px solid var(--bf-border)",
        borderRadius: 6, fontSize: 13, color: "var(--bf-text-1)",
        fontFamily: "inherit",
      }}
    />
  );
}

function TextArea({ value, onChange, rows = 3 }: { value?: string; onChange: (v: string) => void; rows?: number }) {
  return (
    <textarea
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      rows={rows}
      style={{
        width: "100%", padding: "10px 12px",
        background: "var(--bf-bg)", border: "1px solid var(--bf-border)",
        borderRadius: 6, fontSize: 13, color: "var(--bf-text-1)",
        fontFamily: "inherit", lineHeight: 1.6, resize: "vertical",
      }}
    />
  );
}

const Grid2: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>{children}</div>
);

/* ─── 基本情報タブ ─── */
function BasicTab({ d, onChange }: { d: AccountSettings; onChange: (p: Partial<AccountSettings>) => void }) {
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <Grid2>
        <Field label="会社名">
          <TextInput value={d.company_name} onChange={(v) => onChange({ company_name: v })} placeholder="株式会社○○" />
        </Field>
        <Field label="会社名 (カナ)">
          <TextInput value={d.company_name_kana} onChange={(v) => onChange({ company_name_kana: v })} placeholder="カブシキガイシャ オオオオ" />
        </Field>
      </Grid2>
      <Grid2>
        <Field label="代表者役職">
          <TextInput value={d.representative_title} onChange={(v) => onChange({ representative_title: v })} placeholder="代表取締役" />
        </Field>
        <Field label="代表者氏名">
          <TextInput value={d.representative_name} onChange={(v) => onChange({ representative_name: v })} placeholder="山田 太郎" />
        </Field>
      </Grid2>
      <Grid2>
        <Field label="郵便番号">
          <TextInput value={d.postal_code} onChange={(v) => onChange({ postal_code: v })} placeholder="150-0002" />
        </Field>
        <Field label="電話番号">
          <TextInput value={d.phone} onChange={(v) => onChange({ phone: v })} placeholder="03-XXXX-XXXX" />
        </Field>
      </Grid2>
      <Field label="住所">
        <TextInput value={d.address} onChange={(v) => onChange({ address: v })} placeholder="東京都渋谷区○○1-2-3" />
      </Field>
      <Grid2>
        <Field label="メールアドレス">
          <TextInput value={d.email} onChange={(v) => onChange({ email: v })} type="email" placeholder="info@example.com" />
        </Field>
        <Field label="ウェブサイト">
          <TextInput value={d.website} onChange={(v) => onChange({ website: v })} placeholder="https://example.com" />
        </Field>
      </Grid2>
    </div>
  );
}

/* ─── 振込先タブ ─── */
function BankTab({ d, onChange }: { d: AccountSettings; onChange: (p: Partial<AccountSettings>) => void }) {
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <Grid2>
        <Field label="銀行名">
          <TextInput value={d.bank_name} onChange={(v) => onChange({ bank_name: v })} placeholder="三菱UFJ銀行" />
        </Field>
        <Field label="支店名">
          <TextInput value={d.bank_branch} onChange={(v) => onChange({ bank_branch: v })} placeholder="渋谷支店" />
        </Field>
      </Grid2>
      <Grid2>
        <Field label="口座種別">
          <select
            value={d.bank_account_type ?? "普通"}
            onChange={(e) => onChange({ bank_account_type: e.target.value })}
            style={{
              width: "100%", height: 36, padding: "0 12px",
              background: "var(--bf-bg)", border: "1px solid var(--bf-border)",
              borderRadius: 6, fontSize: 13, fontFamily: "inherit",
            }}
          >
            <option>普通</option>
            <option>当座</option>
            <option>貯蓄</option>
          </select>
        </Field>
        <Field label="口座番号">
          <TextInput value={d.bank_account_number} onChange={(v) => onChange({ bank_account_number: v })} placeholder="1234567" />
        </Field>
      </Grid2>
      <Field label="口座名義 (カナ)" hint="例: カ) エンジンベース">
        <TextInput value={d.bank_account_holder} onChange={(v) => onChange({ bank_account_holder: v })} placeholder="カ) ○○○○" />
      </Field>
    </div>
  );
}

/* ─── ブランドタブ ─── */
function BrandTab({ d, onChange }: { d: AccountSettings; onChange: (p: Partial<AccountSettings>) => void }) {
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <Grid2>
        <ImageDropper
          label="ロゴ画像"
          hint="PNG / SVG 推奨・横長 OK"
          accountId={ACCOUNT_ID}
          kind="logo"
          value={d.logo_url}
          onChange={(url) => onChange({ logo_url: url })}
          cropMode="free"
          previewHeight={80}
        />
        <ImageDropper
          label="角印 (任意)"
          hint="PNG 推奨・正方形クロップ"
          accountId={ACCOUNT_ID}
          kind="stamp"
          value={d.stamp_url}
          onChange={(url) => onChange({ stamp_url: url })}
          cropMode="square"
          previewHeight={80}
        />
      </Grid2>

      <Grid2>
        <Field label="角印テキスト" hint="画像が無い場合のフォールバック (例: EB)">
          <TextInput value={d.stamp_text} onChange={(v) => onChange({ stamp_text: v })} placeholder="EB" />
        </Field>
        <Field label="フォントファミリー">
          <select
            value={d.font_family ?? "Noto Sans JP"}
            onChange={(e) => onChange({ font_family: e.target.value })}
            style={{
              width: "100%", height: 36, padding: "0 12px",
              background: "var(--bf-bg)", border: "1px solid var(--bf-border)",
              borderRadius: 6, fontSize: 13, fontFamily: "inherit",
            }}
          >
            <option>Noto Sans JP</option>
            <option>Inter</option>
            <option>Hiragino Sans</option>
          </select>
        </Field>
      </Grid2>

      <Grid2>
        <Field label="プライマリカラー" hint="提案書・見積書のテーマ色">
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="color"
              value={d.primary_color ?? "#004CD9"}
              onChange={(e) => onChange({ primary_color: e.target.value })}
              style={{ width: 44, height: 36, border: "1px solid var(--bf-border)", borderRadius: 6, cursor: "pointer", padding: 2, background: "var(--bf-bg)" }}
            />
            <TextInput value={d.primary_color} onChange={(v) => onChange({ primary_color: v })} placeholder="#004CD9" />
          </div>
        </Field>
        <Field label="セカンダリカラー (任意)">
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="color"
              value={d.secondary_color ?? "#1A5FE0"}
              onChange={(e) => onChange({ secondary_color: e.target.value })}
              style={{ width: 44, height: 36, border: "1px solid var(--bf-border)", borderRadius: 6, cursor: "pointer", padding: 2, background: "var(--bf-bg)" }}
            />
            <TextInput value={d.secondary_color} onChange={(v) => onChange({ secondary_color: v })} placeholder="#1A5FE0" />
          </div>
        </Field>
      </Grid2>
    </div>
  );
}

/* ─── 実績・事例タブ ─── */
function AchievementsTab({ d, onChange }: { d: AccountSettings; onChange: (p: Partial<AccountSettings>) => void }) {
  const stats = d.achievement_stats ?? [];
  const cases = d.case_studies ?? [];

  const updateStat = (i: number, patch: Partial<AchievementStat>) => {
    const next = [...stats];
    next[i] = { ...next[i], ...patch };
    onChange({ achievement_stats: next });
  };
  const addStat = () => onChange({ achievement_stats: [...stats, { value: "", label: "" }] });
  const removeStat = (i: number) => onChange({ achievement_stats: stats.filter((_, j) => j !== i) });

  const updateCase = (i: number, patch: Partial<CaseStudy>) => {
    const next = [...cases];
    next[i] = { ...next[i], ...patch };
    onChange({ case_studies: next });
  };
  const addCase = () => onChange({
    case_studies: [...cases, {
      type: "", client_name: "", title: "", duration: "",
      desc: "", result: "", tech: "", image_url: "", url: "",
    }],
  });
  const removeCase = (i: number) => onChange({ case_studies: cases.filter((_, j) => j !== i) });

  return (
    <div style={{ display: "grid", gap: 28 }}>
      {/* 統計 */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h3 style={{ fontSize: 13, fontWeight: 800, color: "var(--bf-text-1)" }}>実績統計 (3〜12 件推奨)</h3>
          <button
            onClick={addStat}
            style={{ padding: "5px 10px", fontSize: 11, fontWeight: 700, color: "var(--bf-primary)", background: "var(--bf-primary-bg)", border: "1px solid var(--bf-primary)", borderRadius: 6, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4 }}
          ><Plus className="w-3 h-3" />追加</button>
        </div>
        <div style={{ display: "grid", gap: 8 }}>
          {stats.map((s, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "150px 1fr 32px", gap: 8, alignItems: "center" }}>
              <TextInput value={s.value} onChange={(v) => updateStat(i, { value: v })} placeholder="30+" />
              <TextInput value={s.label} onChange={(v) => updateStat(i, { label: v })} placeholder="開発実績件数" />
              <button onClick={() => removeStat(i)}
                style={{ width: 32, height: 32, border: "1px solid var(--bf-border)", borderRadius: 6, background: "var(--bf-bg)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Trash2 className="w-3 h-3" style={{ color: "var(--bf-danger)" }} />
              </button>
            </div>
          ))}
          {stats.length === 0 && (
            <div style={{ padding: 16, fontSize: 12, color: "var(--bf-text-4)", textAlign: "center", border: "1px dashed var(--bf-border)", borderRadius: 6 }}>
              「+ 追加」で実績統計を追加 (例: 30+ / 開発実績件数)
            </div>
          )}
        </div>
      </div>

      {/* 事例 (リッチカード) */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h3 style={{ fontSize: 13, fontWeight: 800, color: "var(--bf-text-1)" }}>過去事例 (画像・内容詳細)</h3>
          <button
            onClick={addCase}
            style={{ padding: "5px 10px", fontSize: 11, fontWeight: 700, color: "var(--bf-primary)", background: "var(--bf-primary-bg)", border: "1px solid var(--bf-primary)", borderRadius: 6, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4 }}
          ><Plus className="w-3 h-3" />事例を追加</button>
        </div>
        <div style={{ display: "grid", gap: 16 }}>
          {cases.map((c, i) => (
            <div key={i} style={{
              padding: 18, border: "1px solid var(--bf-border)", borderRadius: 12,
              background: "var(--bf-bg)",
              display: "grid", gridTemplateColumns: "200px 1fr", gap: 18,
            }}>
              {/* 左: 画像 */}
              <div>
                <ImageDropper
                  label="事例画像"
                  hint="スクショ / 成果ビジュアル"
                  accountId={ACCOUNT_ID}
                  kind="case_study"
                  value={c.image_url}
                  onChange={(url) => updateCase(i, { image_url: url })}
                  cropMode="free"
                  previewHeight={140}
                />
              </div>

              {/* 右: フィールド */}
              <div style={{ display: "grid", gap: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "var(--bf-text-4)", letterSpacing: "0.06em" }}>
                    事例 #{i + 1}
                  </div>
                  <button onClick={() => removeCase(i)}
                    style={{ padding: "4px 10px", fontSize: 11, color: "var(--bf-danger)", background: "transparent", border: "1px solid var(--bf-danger)", borderRadius: 6, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4 }}>
                    <Trash2 className="w-3 h-3" />削除
                  </button>
                </div>

                <Grid2>
                  <Field label="種別 / 業界">
                    <TextInput value={c.type} onChange={(v) => updateCase(i, { type: v })} placeholder="EC / BtoB SaaS / 医療 etc." />
                  </Field>
                  <Field label="クライアント名" hint="匿名化したい場合は『食品EC A社』等">
                    <TextInput value={c.client_name} onChange={(v) => updateCase(i, { client_name: v })} placeholder="株式会社○○ / 匿名" />
                  </Field>
                </Grid2>

                <Field label="案件タイトル">
                  <TextInput value={c.title} onChange={(v) => updateCase(i, { title: v })} placeholder="食品 EC × BtoB 卸 統合プラットフォーム構築" />
                </Field>

                <Grid2>
                  <Field label="期間">
                    <TextInput value={c.duration} onChange={(v) => updateCase(i, { duration: v })} placeholder="2026年4月〜8月 (4 か月)" />
                  </Field>
                  <Field label="主要な成果">
                    <TextInput value={c.result} onChange={(v) => updateCase(i, { result: v })} placeholder="月商 200→500 万円・継続率 35→78%" />
                  </Field>
                </Grid2>

                <Field label="概要・取り組み内容">
                  <TextArea value={c.desc} onChange={(v) => updateCase(i, { desc: v })} rows={3} />
                </Field>

                <Grid2>
                  <Field label="使用技術 (任意)">
                    <TextInput value={c.tech} onChange={(v) => updateCase(i, { tech: v })} placeholder="Next.js / Supabase / Stripe" />
                  </Field>
                  <Field label="公開リンク (任意)">
                    <TextInput value={c.url} onChange={(v) => updateCase(i, { url: v })} placeholder="https://..." />
                  </Field>
                </Grid2>
              </div>
            </div>
          ))}
          {cases.length === 0 && (
            <div style={{ padding: 32, fontSize: 12, color: "var(--bf-text-4)", textAlign: "center", border: "1px dashed var(--bf-border)", borderRadius: 8 }}>
              「+ 事例を追加」で過去事例を追加できます。<br />
              画像・タイトル・期間・成果・概要・使用技術を入力できます。
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── デフォルト条件タブ ─── */
function DefaultsTab({ d, onChange }: { d: AccountSettings; onChange: (p: Partial<AccountSettings>) => void }) {
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <Grid2>
        <Field label="支払条件 (デフォルト)" hint="例: 30/30/40 (着手金/中間/検収後)">
          <TextInput value={d.payment_terms_default} onChange={(v) => onChange({ payment_terms_default: v })} placeholder="30/30/40" />
        </Field>
        <Field label="保証期間 (日)">
          <TextInput
            value={d.warranty_days?.toString()}
            onChange={(v) => onChange({ warranty_days: v ? parseInt(v) : 90 })}
            type="number"
          />
        </Field>
      </Grid2>
      <Grid2>
        <Field label="月額保守 (円・税抜)" hint="基本プラン">
          <TextInput
            value={d.monthly_maintenance_yen?.toString()}
            onChange={(v) => onChange({ monthly_maintenance_yen: v ? parseInt(v) : undefined })}
            type="number"
            placeholder="50000"
          />
        </Field>
        <Field label="見積有効期限 (日)">
          <TextInput
            value={d.estimate_validity_days?.toString()}
            onChange={(v) => onChange({ estimate_validity_days: v ? parseInt(v) : 30 })}
            type="number"
          />
        </Field>
      </Grid2>
      <Grid2>
        <Field label="消費税率" hint="例: 0.10 (10%)">
          <TextInput
            value={d.tax_rate?.toString()}
            onChange={(v) => onChange({ tax_rate: v ? parseFloat(v) : 0.10 })}
            type="number"
          />
        </Field>
        <Field label="見積番号プレフィックス">
          <TextInput value={d.estimate_prefix} onChange={(v) => onChange({ estimate_prefix: v })} placeholder="EST" />
        </Field>
      </Grid2>
    </div>
  );
}

/* ═══════════ Real-time Preview ═══════════ */
function PreviewPanel({ settings }: { settings: AccountSettings }) {
  const primary = settings.primary_color || "#004CD9";
  return (
    <div style={{
      background: "var(--bf-bg-elev)", border: "1px solid var(--bf-border)",
      borderRadius: 12, overflow: "hidden",
    }}>
      <div style={{
        padding: "10px 14px",
        background: "var(--bf-bg)",
        borderBottom: "1px solid var(--bf-divider)",
        fontSize: 12, fontWeight: 700, color: "var(--bf-text-1)",
        display: "flex", alignItems: "center", gap: 6,
      }}>
        <span style={{
          fontSize: 10, fontWeight: 800, padding: "2px 6px",
          background: primary, color: "#fff", borderRadius: 3, letterSpacing: "0.06em",
        }}>LIVE</span>
        プレビュー (この設定で生成される文書イメージ)
      </div>
      <div style={{ padding: 16, fontSize: 11, fontFamily: "'Noto Sans JP', sans-serif", maxHeight: "calc(100vh - 200px)", overflowY: "auto", background: "#EEF1F5" }}>
        {/* 見積書ミニプレビュー */}
        <div style={{
          background: "#fff", border: "1px solid #E4E8EE", borderRadius: 8,
          padding: 24, fontSize: 10, lineHeight: 1.6, marginBottom: 16,
          boxShadow: "0 4px 12px rgba(0,0,0,0.04)",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", paddingBottom: 12, borderBottom: `2px solid ${primary}`, marginBottom: 14 }}>
            <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: "0.12em", color: "#0F172A" }}>御 見 積 書</div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 9, color: "#94A3B8", letterSpacing: "0.06em", textTransform: "uppercase", fontWeight: 700 }}>No.</div>
              <div style={{ fontSize: 11, fontFamily: "monospace", fontWeight: 700 }}>{settings.estimate_prefix || "EST"}-20260508-001</div>
              <div style={{ fontSize: 9, color: "#64748B", marginTop: 4 }}>有効期限: {settings.estimate_validity_days || 30}日</div>
            </div>
          </div>

          {/* 宛先 / 発行者 */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 14, fontSize: 9 }}>
            <div>
              <div style={{ borderBottom: "1.5px solid #0F172A", paddingBottom: 4, marginBottom: 4 }}>
                <span style={{ fontSize: 13, fontWeight: 700 }}>○○ 御中</span>
              </div>
              <div style={{ color: "#64748B" }}>クライアント担当者 様</div>
            </div>
            <div style={{ textAlign: "right" }}>
              {settings.logo_url && (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={settings.logo_url.startsWith("http") || settings.logo_url.startsWith("/") ? settings.logo_url : `http://localhost:8001${settings.logo_url}`}
                  alt="logo"
                  style={{ maxHeight: 20, marginBottom: 4 }}
                />
              )}
              <div style={{ fontSize: 11, fontWeight: 700, color: "#0F172A" }}>{settings.company_name || "(会社名 未設定)"}</div>
              <div style={{ color: "#64748B", lineHeight: 1.5 }}>
                {settings.postal_code && `〒${settings.postal_code} `}{settings.address || ""}<br />
                {settings.phone || ""} / {settings.email || ""}<br />
                {settings.representative_title} {settings.representative_name}
              </div>
              {settings.stamp_url ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={settings.stamp_url.startsWith("http") || settings.stamp_url.startsWith("/") ? settings.stamp_url : `http://localhost:8001${settings.stamp_url}`}
                  alt="stamp"
                  style={{ width: 36, height: 36, marginTop: 6 }}
                />
              ) : settings.stamp_text ? (
                <div style={{
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                  width: 36, height: 36, border: "1.5px solid #DC2626",
                  color: "#DC2626", borderRadius: "50%", fontSize: 9, fontWeight: 800,
                  marginTop: 6,
                }}>{settings.stamp_text}</div>
              ) : null}
            </div>
          </div>

          <div style={{ background: `${primary}1A`, borderLeft: `3px solid ${primary}`, padding: "8px 10px", marginBottom: 12 }}>
            <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: "0.06em", color: primary, textTransform: "uppercase" }}>件名</div>
            <div style={{ fontSize: 11, fontWeight: 700 }}>○○ 構築 御見積書</div>
          </div>

          {/* 合計 hero */}
          <div style={{
            padding: "14px 16px", background: `linear-gradient(135deg, ${primary}DD 0%, ${primary} 100%)`,
            borderRadius: 8, color: "#fff", marginBottom: 12,
          }}>
            <div style={{ fontSize: 8, letterSpacing: "0.12em", textTransform: "uppercase", opacity: 0.7, fontWeight: 700 }}>御見積金額 (税込)</div>
            <div style={{ fontSize: 22, fontWeight: 900, marginTop: 2 }}>¥3,520,000</div>
          </div>

          {/* 振込先 */}
          <div style={{ background: "#FAFBFD", border: "1px solid #E4E8EE", borderRadius: 6, padding: "10px 12px", fontSize: 9, color: "#334155" }}>
            <div style={{ fontSize: 8, fontWeight: 800, letterSpacing: "0.06em", color: primary, textTransform: "uppercase", marginBottom: 4 }}>振込先</div>
            <div>{settings.bank_name || "(銀行名)"} {settings.bank_branch || ""} ({settings.bank_account_type || "普通"})</div>
            <div>{settings.bank_account_number || "(口座番号)"} / {settings.bank_account_holder || "(口座名義)"}</div>
          </div>

          <div style={{ marginTop: 10, fontSize: 9, color: "#64748B" }}>
            支払条件: {settings.payment_terms_default || "30/30/40"} ・ 保証期間: {settings.warranty_days || 90}日
            {settings.monthly_maintenance_yen ? ` ・ 月額保守: ¥${settings.monthly_maintenance_yen.toLocaleString()}` : ""}
          </div>
        </div>

        {/* 提案書カバーミニプレビュー */}
        <div style={{
          background: `linear-gradient(135deg, #002B7A 0%, ${primary} 50%, #1A5FE0 100%)`,
          color: "#fff", borderRadius: 10, padding: "28px 24px",
        }}>
          {settings.logo_url && (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={settings.logo_url.startsWith("http") || settings.logo_url.startsWith("/") ? settings.logo_url : `http://localhost:8001${settings.logo_url}`}
              alt="logo"
              style={{ maxHeight: 24, marginBottom: 14, filter: "brightness(0) invert(1)" }}
            />
          )}
          <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.18em", textTransform: "uppercase", color: "rgba(255,255,255,0.7)", marginBottom: 8 }}>
            PROPOSAL · 開発ご提案
          </div>
          <div style={{ fontSize: 18, fontWeight: 900, lineHeight: 1.2, marginBottom: 6, letterSpacing: "-0.01em" }}>
            ○○ 構築プロジェクト
          </div>
          <div style={{ fontSize: 11, opacity: 0.85, marginBottom: 18 }}>
            {settings.company_name || "(会社名 未設定)"}
          </div>
          <div style={{ fontSize: 9, paddingTop: 12, borderTop: "1px solid rgba(255,255,255,0.2)", color: "rgba(255,255,255,0.7)", lineHeight: 1.6 }}>
            実績 {(settings.achievement_stats ?? []).map((s) => `${s.value} ${s.label}`).join(" / ") || "(設定してください)"}
          </div>
        </div>
      </div>
    </div>
  );
}
