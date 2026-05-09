"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

/* ────── 静的テキスト (直接編集なし・AI チャット経由でのみ更新) ────── */
function E({ value, multiline = false, inline = false, style, className }: {
  id?: string; value: string; multiline?: boolean; inline?: boolean;
  style?: React.CSSProperties; className?: string;
}) {
  const Tag = (inline ? "span" : "div") as "span" | "div";
  return (
    <Tag
      className={className}
      style={{
        ...style,
        whiteSpace: multiline ? "pre-wrap" : undefined,
        wordBreak: "break-word",
      }}
    >
      {value}
    </Tag>
  );
}

/* ────── 静的リスト (直接編集なし・AI チャット経由でのみ更新) ────── */
function L({ items, listType = "bullet" }: {
  id?: string; items: string[]; listType?: "bullet" | "number" | "check";
}) {
  const Tag = (listType === "number" ? "ol" : "ul") as "ol" | "ul";
  return (
    <Tag style={{ paddingLeft: 22, margin: 0 }}>
      {items.map((it, i) => (
        <li key={i} style={{ marginBottom: 4, lineHeight: 1.7, color: "var(--bf-text-2)" }}>{it}</li>
      ))}
    </Tag>
  );
}

/**
 * 要件定義書 (テンプレ準拠) リッチビュー — デモモード専用
 *
 * `/Users/masato0420/Downloads/要件定義書_ENGINEBASE.html` の構造を React で再現。
 * カラーは BF プライマリ (--bf-primary) をそのまま使用。
 *
 * 各タブで描画する HTML 要素:
 *  - overview      : 目的(p) + 課題(table) + TO-BE flow + 制約(info-grid) + 技術スタック(table)
 *  - users         : persona-grid (3 カード)
 *  - features      : table + badge
 *  - functional    : feature-block × N (header + row layout)
 *  - nonfunctional : table
 *  - screens       : table × 2 + flow-block × 2
 *  - data          : table
 *  - integrations  : table
 *  - legal         : info-grid + table × 2 + ul × 2
 *  - risks         : table
 *  - unresolved    : unresolved-list
 */

export const RICH_TABS = [
  { key: "overview", num: 1, label: "プロジェクト概要" },
  { key: "users", num: 2, label: "ターゲットユーザー" },
  { key: "features", num: 3, label: "主要機能一覧" },
  { key: "functional", num: 4, label: "機能要件詳細" },
  { key: "nonfunctional", num: 5, label: "非機能要件" },
  { key: "screens", num: 6, label: "画面・UX概要" },
  { key: "data", num: 7, label: "データ構造" },
  { key: "integrations", num: 8, label: "外部連携" },
  { key: "legal", num: 9, label: "法的考慮・コンプライアンス" },
  { key: "risks", num: 10, label: "リスク・懸念点" },
  { key: "infra_cost", num: 11, label: "インフラコスト試算" },
  { key: "unresolved", num: 12, label: "未確認事項" },
  { key: "scope", num: 13, label: "スコープ・スケジュール" },
  { key: "history", num: 14, label: "改訂履歴" },
];

export function RichSectionCard({
  num, title, sourceSteps, children,
}: { num: number; title: string; sourceSteps?: number[]; children: React.ReactNode }) {
  return (
    <div className="rd-section-card">
      <div className="rd-section-header">
        <div className="rd-section-num">{num}</div>
        <div className="rd-section-title">{title}</div>
        {sourceSteps && sourceSteps.length > 0 && (
          <span className="rd-section-step-tag">STEP {sourceSteps.join(", ")}</span>
        )}
      </div>
      {children}
    </div>
  );
}

export function RichSubsection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rd-subsection">
      <div className="rd-subsection-title">{title}</div>
      {children}
    </div>
  );
}

/* ════ Overview ════ */
const OVERVIEW_CHALLENGES: Array<[string, string, string]> = [
  ["① 定期便機能", "BASE では定期便機能なし。スプレッドシート + 手動配送指示", "顧客 30 名超で運用が破綻。スキップ・変更要望に当日対応できず解約発生"],
  ["② BtoB 対応", "BtoB 価格表示・請求書払い・与信機能が存在しない", "飲食店からの問い合わせを取りこぼし。月 5-10 件の機会損失"],
  ["③ 商品レコメンド", "顧客の好み (焙煎度・抽出方法) を記録できない", "クロスセル機会を逃し、平均購入単価 2,800 円で頭打ち"],
  ["④ 在庫管理", "BASE と倉庫システムが連携しておらず手動転記", "欠品/超過在庫で月 8 万円の機会損失と廃棄ロス"],
];

export function OverviewTab() {
  return (
    <RichSectionCard num={1} title="プロジェクト概要" sourceSteps={[1]}>
      <RichSubsection title="目的・背景">
        <div className="rd-p"><E id="overview/purpose-1" multiline value="自家焙煎コーヒー豆のオンライン販売 EC サイトを新規構築。BtoC を中心に、最近引き合いが増えている飲食店向け BtoB 卸の 2 ラインを統合する。サブスクリプション (定期便) を中核に据え、現行 BASE で限界に達した手動運用から脱却する。" /></div>
        <div className="rd-p"><E id="overview/purpose-2" multiline value="本プロジェクトでは、商品レコメンド・定期便の柔軟な変更/解約・BtoB 与信フローを実装することで、月商 300 万円達成と継続率 80% を実現する。" /></div>
      </RichSubsection>

      <RichSubsection title="現状 (AS-IS) の課題">
        <div className="rd-table-wrap">
          <table>
            <thead><tr><th>課題</th><th>現状</th><th>影響</th></tr></thead>
            <tbody>
              {OVERVIEW_CHALLENGES.map((row, i) => (
                <tr key={i}>
                  <td><E id={`overview/ch-${i}-0`} value={row[0]} /></td>
                  <td><E id={`overview/ch-${i}-1`} value={row[1]} multiline /></td>
                  <td><E id={`overview/ch-${i}-2`} value={row[2]} multiline /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </RichSubsection>

      <RichSubsection title="TO-BE (目標) 業務フロー">
        <div className="rd-flow-block">
          <div className="rd-flow-title"><E id="overview/flow-1-title" value="注文〜配送 (自動化)" /></div>
          <div className="rd-flow-steps">
            <L id="overview/flow-1" listType="number" items={[
              "顧客が商品ページで好み登録 → レコメンド表示",
              "カート → Stripe Checkout (3D セキュア)",
              "受注 Webhook → Shippinno へ自動引当 → 倉庫ピッキング",
              "配送ラベル印刷 → 出荷完了通知メール",
            ]} />
          </div>
        </div>
        <div className="rd-flow-block">
          <div className="rd-flow-title"><E id="overview/flow-2-title" value="定期便サイクル (自動化)" /></div>
          <div className="rd-flow-steps">
            <L id="overview/flow-2" listType="number" items={[
              "次回配送 7 日前: 確認メール送信 (スキップ/変更導線)",
              "顧客がマイページで操作 (1 クリック解約対応)",
              "確定後 Stripe Subscription 自動課金",
              "請求書 PDF 自動生成 → マイページからダウンロード可能",
            ]} />
          </div>
        </div>
      </RichSubsection>

      <RichSubsection title="制約条件">
        <div className="rd-info-grid">
          {([
            ["納品期限", "2026 年 9 月 1 日"],
            ["予算", "350 万円 + 月 5 万円"],
            ["商品数", "80 SKU (将来 200)"],
            ["既存データ", "BASE 顧客 1,200 件 移行必須"],
            ["運用体制", "自社スタッフ 3 名兼任"],
            ["決済", "Stripe + Paid (BtoB)"],
          ] as const).map(([label, value], i) => (
            <div className="rd-info-card" key={i}>
              <div className="rd-info-card-label"><E id={`overview/cons-${i}-l`} value={label} /></div>
              <div className="rd-info-card-value"><E id={`overview/cons-${i}-v`} value={value} multiline /></div>
            </div>
          ))}
        </div>
      </RichSubsection>

      <RichSubsection title="技術スタック (確定)">
        <div className="rd-table-wrap">
          <table>
            <thead><tr><th>層</th><th>採用技術</th><th>状態</th></tr></thead>
            <tbody>
              <tr><td>フロントエンド</td><td>Next.js 16 (App Router) / React / TypeScript</td><td><span className="rd-badge rd-badge-confirmed">確定</span></td></tr>
              <tr><td>バックエンド</td><td>Hono on Node.js / TypeScript</td><td><span className="rd-badge rd-badge-confirmed">確定</span></td></tr>
              <tr><td>データベース</td><td>PostgreSQL 16 (Supabase)</td><td><span className="rd-badge rd-badge-confirmed">確定</span></td></tr>
              <tr><td>決済 BtoC</td><td><strong>Stripe Subscription</strong> (定期便・カード)</td><td><span className="rd-badge rd-badge-confirmed">確定</span></td></tr>
              <tr><td>決済 BtoB</td><td>Paid (請求書払い・与信)</td><td><span className="rd-badge rd-badge-hypothesis">仮説</span></td></tr>
              <tr><td>倉庫</td><td>Shippinno (在庫・配送)</td><td><span className="rd-badge rd-badge-confirmed">確定</span></td></tr>
              <tr><td>メール</td><td>SendGrid (transactional + step)</td><td><span className="rd-badge rd-badge-confirmed">確定</span></td></tr>
              <tr><td>ホスティング</td><td>Vercel + Cloudflare</td><td><span className="rd-badge rd-badge-confirmed">確定</span></td></tr>
            </tbody>
          </table>
        </div>
      </RichSubsection>
    </RichSectionCard>
  );
}

/* ════ Users ════ */
export function UsersTab() {
  return (
    <RichSectionCard num={2} title="ターゲットユーザー" sourceSteps={[2]}>
      <div className="rd-persona-grid">
        <PersonaCard
          idPrefix="users/p-a"
          icon="☕"
          title="ペルソナA: こだわりホームバリスタ"
          rows={[
            ["属性", "30〜45 歳・在宅勤務中心・月のコーヒー支出 5,000 円以上"],
            ["IT リテラシー", "中〜高 (スマホ・PC 両方使う)"],
            ["利用動機", "産地・焙煎度を選びたい。配送スケジュールを自分で管理したい"],
            ["解決されること", "好み登録でレコメンド精度向上。マイページから 1 クリック スキップ"],
          ]}
        />
        <PersonaCard
          idPrefix="users/p-b"
          icon="📷"
          title="ペルソナB: SNS 発信型ユーザー"
          rows={[
            ["属性", "20代後半・カフェ巡りが趣味・SNS 経由で新規購入"],
            ["IT リテラシー", "高 (Instagram・X 中心)"],
            ["利用動機", "話題のコーヒーを試して投稿したい。映える商品ページを期待"],
            ["解決されること", "シェア導線・商品ストーリー閲覧。レビュー投稿でクーポン獲得"],
          ]}
        />
        <PersonaCard
          idPrefix="users/p-c"
          icon="🏪"
          title="ペルソナC: BtoB 個人カフェオーナー"
          rows={[
            ["属性", "個人経営カフェ・15-30 席規模・週 2-3 回の発注"],
            ["IT リテラシー", "中"],
            ["利用動機", "営業終了後に翌週分を一括発注。請求書払いで月締め"],
            ["解決されること", "BtoB 専用ダッシュボード・一括発注・請求書 PDF"],
          ]}
        />
        <PersonaCard
          idPrefix="users/p-d"
          icon="📦"
          title="ペルソナD: 自社スタッフ (運用)"
          rows={[
            ["属性", "ASTcolor 社内スタッフ 3 名・受注/在庫/発送を兼任"],
            ["現在の課題", "BASE と倉庫の手動転記。BtoB 与信判断が属人化"],
            ["解決されること", "管理画面で一元化。Shippinno 自動連携。安全在庫アラート"],
          ]}
        />
      </div>
    </RichSectionCard>
  );
}

function PersonaCard({ idPrefix, icon, title, rows }: {
  idPrefix: string;
  icon: string; title: string; rows: [string, string][];
}) {
  return (
    <div className="rd-persona-card">
      <div className="rd-persona-header">
        <span className="rd-persona-icon">{icon}</span>
        <span className="rd-persona-title" style={{ color: "#fff" }}>
          <E id={`${idPrefix}-title`} value={title} style={{ color: "#fff" }} />
        </span>
      </div>
      <div className="rd-persona-body">
        {rows.map(([label, value], i) => (
          <div className="rd-persona-row" key={i}>
            <div className="rd-persona-row-label"><E id={`${idPrefix}-${i}-l`} value={label} /></div>
            <div className="rd-persona-row-value"><E id={`${idPrefix}-${i}-v`} value={value} multiline /></div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ════ Features 一覧 ════ */
const FEATURES_TABLE = [
  ["F001", "ユーザー認証・会員管理", "メール+パスワード認証・好み登録・パスワードリセット", "must", "p1"],
  ["F002", "商品カタログ・検索", "焙煎度/産地/価格帯/抽出方法での絞り込み・全文検索", "must", "p1"],
  ["F003", "商品詳細・レコメンド", "ストーリー/原産地表示・好みベースの関連商品提案", "must", "p1"],
  ["F004", "カート・購入・決済", "匿名/会員カート・Stripe Checkout・3D セキュア", "must", "p1"],
  ["F005", "サブスクリプション (定期便)", "2/3/4 週サイクル・スキップ/変更/解約 (1 クリック)", "must", "p1"],
  ["F006", "BtoB 申込・与信", "屋号/住所/与信希望額入力・3 営業日以内に審査結果メール", "must", "p1"],
  ["F007", "BtoB 専用ダッシュボード", "一括発注・請求書一覧・専用価格表示", "must", "p1"],
  ["F008", "顧客マイページ", "注文履歴・お気に入り・好み登録・定期便管理", "must", "p1"],
  ["F009", "管理:商品・在庫", "商品 CRUD・実在庫/引当/安全在庫・割れ通知メール", "must", "p1"],
  ["F010", "管理:受注", "ステータス更新・Shippinno CSV エクスポート", "must", "p1"],
  ["F011", "管理:顧客", "BtoB 与信審査・問い合わせ履歴・好みデータ閲覧", "must", "p1"],
  ["F012", "メールマーケティング", "ステップ配信 (登録後 3 日/7 日/30 日)", "should", "p2"],
  ["F013", "レビュー投稿", "購入完了 7 日後にレビュー依頼メール・投稿でクーポン", "should", "p2"],
  ["F014", "クーポン管理", "BtoC/BtoB 別・期限・利用回数制限", "should", "p2"],
];

export function FeaturesTab() {
  return (
    <RichSectionCard num={3} title={`主要機能一覧 (全 ${FEATURES_TABLE.length} 機能)`} sourceSteps={[2]}>
      <div className="rd-table-wrap">
        <table>
          <thead><tr><th>機能ID</th><th>機能名</th><th>概要</th><th>優先度</th><th>Phase</th></tr></thead>
          <tbody>
            {FEATURES_TABLE.map(([id, name, desc, prio, phase], i) => (
              <tr key={i}>
                <td><code className="rd-code"><E id={`features/r${i}-id`} value={id} /></code></td>
                <td><E id={`features/r${i}-name`} value={name} /></td>
                <td><E id={`features/r${i}-desc`} value={desc} multiline /></td>
                <td><span className={`rd-badge rd-badge-${prio}`}>{prio === "must" ? "Must" : "Should"}</span></td>
                <td><span className={`rd-badge rd-badge-${phase}`}>{phase.toUpperCase()}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </RichSectionCard>
  );
}

/* ════ Functional 詳細 (feature-block) ════ */
type FRow =
  | { kind: "text"; label: string; value: string }
  | { kind: "list"; label: string; items: string[] };

const FEATURE_BLOCKS: Array<{
  id: string; name: string; phase: string;
  rows: FRow[];
}> = [
  {
    id: "F004", name: "カート・購入・決済", phase: "p1",
    rows: [
      { kind: "text", label: "概要", value: "匿名カート + ログイン後マージ。Stripe Checkout で 3D セキュア決済。失敗時は再試行可能 (二重課金防止)。" },
      { kind: "list", label: "処理の流れ", items: [
        "商品詳細「カートに入れる」→ セッション (Cookie) にカート ID 保持",
        "ログイン → サーバー側カートに項目をマージ (重複時は数量加算)",
        "チェックアウト → 配送先・配送方法選択 → Stripe Checkout",
        "決済成功 Webhook → 受注作成 → Shippinno に在庫引当",
        "完了画面 → マイページの注文履歴に反映",
      ]},
      { kind: "list", label: "エラーケース", items: [
        "Stripe 決済失敗 → 再試行可能・在庫は予約状態のまま 30 分保持",
        "在庫切れ商品 → カート画面で赤バッジ + 注文不可",
      ]},
      { kind: "list", label: "制約", items: [
        "カートの最大保持期間: 30 日 (匿名カート)",
        "1 注文の上限: 10 SKU・合計 50 個",
      ]},
    ],
  },
  {
    id: "F005", name: "サブスクリプション (定期便)", phase: "p1",
    rows: [
      { kind: "text", label: "概要", value: "Stripe Subscription による定期課金。サイクルは 2/3/4 週から選択。次回配送 7 日前まで変更/スキップ/解約可能。" },
      { kind: "list", label: "処理の流れ", items: [
        "商品詳細「定期便で購入」→ サイクル選択 → 初回決済 (Stripe Subscription 開始)",
        "次回配送 7 日前: 確認メール (スキップ/変更/解約のリンク付き)",
        "確定後 Stripe が自動課金 → 受注作成 → 出荷",
        "解約時: マイページから 1 クリック → 確認モーダル → Subscription cancel",
      ]},
      { kind: "list", label: "エラーケース", items: [
        "カード決済失敗 → 7 日間 3 回リトライ → 最終的に Subscription 一時停止 + メール通知",
        "在庫切れ → 自動スキップ + 翌サイクルへ繰越 + メール通知",
      ]},
      { kind: "list", label: "制約", items: [
        "初回購入から 1 サイクル経過後に解約可能 (約款に明記)",
        "解約導線は申込画面と同等の操作で完結 (改正特商法 2022 対応)",
      ]},
    ],
  },
  {
    id: "F006", name: "BtoB 申込・与信", phase: "p1",
    rows: [
      { kind: "text", label: "概要", value: "個人経営カフェ・飲食店向けの BtoB アカウント申込。屋号・住所・代表者情報・希望取引額を入力 → 自社スタッフが手動審査 (3 営業日以内)。" },
      { kind: "list", label: "処理の流れ", items: [
        "BtoB 申込フォーム入力 → 必要書類 (登記簿/開業届) アップロード",
        "管理画面に申込通知 → 自社スタッフが Paid と連携して与信確認",
        "承認 → 専用ログイン情報をメール送信 → BtoB ダッシュボードへ遷移",
        "否認 → 理由付きでメール通知 (再申込は 6 か月後から可能)",
      ]},
      { kind: "list", label: "エラーケース", items: [
        "必要書類アップロード失敗 → 一時保存 → 再アップロードリンクをメール送信",
        "3 営業日以内に審査未完了 → 自動でエスカレーションメール",
      ]},
      { kind: "list", label: "制約", items: [
        "請求書払いの上限: 月 30 万円 (初回) / 承認後段階的に拡大",
        "支払サイト: 月末締め翌月末払い (下請法準拠 60 日以内)",
      ]},
    ],
  },
  {
    id: "F009", name: "管理: 商品・在庫", phase: "p1",
    rows: [
      { kind: "text", label: "概要", value: "商品 CRUD と Shippinno 連携の在庫管理。実在庫・引当在庫・安全在庫を表示し、安全在庫割れ時に通知メール送信。" },
      { kind: "list", label: "管理項目", items: [
        "商品名 / SKU / 焙煎度 / 産地 / 価格 / 説明 / 画像 (複数)",
        "実在庫 (Shippinno 同期) / 引当在庫 / 安全在庫しきい値",
        "状態フラグ: 公開 / 非公開 / 完売 / 入荷待ち",
      ]},
      { kind: "list", label: "処理の流れ", items: [
        "商品登録 → Shippinno へ商品マスタ同期 (双方向)",
        "受注確定 → Shippinno に引当 → 実在庫から減算",
        "1 時間バッチで Shippinno 実在庫を取得 → DB 同期",
        "安全在庫を下回ったら担当メールに通知",
      ]},
    ],
  },
];

function CollapsibleFeatureBlock({ b, bi }: { b: typeof FEATURE_BLOCKS[number]; bi: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rd-feature-block">
      <div
        className="rd-feature-header"
        onClick={() => setOpen((v) => !v)}
        style={{ cursor: "pointer", userSelect: "none" }}
        role="button"
        aria-expanded={open}
      >
        <span style={{ color: "var(--bf-text-3)", display: "inline-flex", alignItems: "center" }}>
          {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </span>
        <span className="rd-feature-id"><E value={b.id} /></span>
        <span className="rd-feature-name"><E value={b.name} /></span>
        <span className={`rd-feature-phase ${b.phase}`}>{b.phase === "p1" ? "Phase 1" : "Phase 2"}</span>
      </div>
      {open && b.rows.map((row, i) => (
        <div className="rd-feature-row" key={i}>
          <div className="rd-feature-row-label"><E value={row.label} /></div>
          <div className="rd-feature-row-value">
            {row.kind === "text"
              ? <E value={row.value} multiline />
              : <L items={row.items} />}
          </div>
        </div>
      ))}
    </div>
  );
}

export function FunctionalTab() {
  return (
    <RichSectionCard num={4} title="機能要件詳細" sourceSteps={[3]}>
      {FEATURE_BLOCKS.map((b, bi) => (
        <CollapsibleFeatureBlock key={b.id} b={b} bi={bi} />
      ))}
    </RichSectionCard>
  );
}

/* ════ NonFunctional ════ */
export function NonFunctionalTab() {
  const rows: [string, React.ReactNode, string][] = [
    ["パフォーマンス", "LCP < 2.5s (3G 想定) / API p95 < 300ms", "離脱率に直結。GA4 で計測"],
    ["スケーラビリティ", <>商品 5,000 点・月 10,000 注文まで無改修対応</>, "1 年後の伸びを織り込み"],
    ["同時接続", "管理者 5 名同時操作・顧客 500 同時セッション", "セール時のピークを想定"],
    ["可用性", "稼働率 99.5% 以上", "Vercel + Supabase の SLA を活用"],
    ["セキュリティ ①", "HTTPS 必須・Cloudflare DDoS 防御", "個人情報・決済情報を扱うため必須"],
    ["セキュリティ ②", "管理画面 2FA + IP 制限", "不正アクセスによる顧客情報漏洩防止"],
    ["セキュリティ ③", "決済情報は Stripe トークン化のみ (PCI DSS SAQ-A)", "自社 DB に保存しない"],
    ["データ保持", "顧客データ: 解約後 6 か月 / 取引データ: 7 年", "法人税法・特商法準拠"],
    ["バックアップ", "日次自動 + 直近 7 日分保持", "Supabase Backups 機能"],
    ["モバイル対応", "375px〜完全対応", "BtoC は 70% がスマホ流入"],
    ["アクセシビリティ", "WCAG 2.1 AA 準拠", "色コントラスト・キーボード操作・読み上げ"],
  ];
  return (
    <RichSectionCard num={5} title="非機能要件" sourceSteps={[4]}>
      <div className="rd-table-wrap">
        <table>
          <thead><tr><th>種別</th><th>要件</th><th>根拠・備考</th></tr></thead>
          <tbody>
            {rows.map(([k, v, n], i) => (
              <tr key={i}>
                <td><E id={`nonfunctional/r${i}-0`} value={String(k)} /></td>
                <td>{typeof v === "string" ? <E id={`nonfunctional/r${i}-1`} value={v} multiline /> : v}</td>
                <td><E id={`nonfunctional/r${i}-2`} value={String(n)} multiline /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </RichSectionCard>
  );
}

/* ════ Screens ════ */
export function ScreensTab() {
  const userScreens: [string, string, string, string][] = [
    ["S001", "トップ", "全ユーザー", "新着・特集・定期便訴求"],
    ["S002", "商品一覧", "全ユーザー", "焙煎度/産地/価格絞り込み"],
    ["S003", "商品詳細", "全ユーザー", "ストーリー/レビュー/レコメンド"],
    ["S004", "カート", "全ユーザー", "数量変更・削除・在庫表示"],
    ["S005", "チェックアウト", "ログイン済", "Stripe Checkout 遷移"],
    ["S006", "ログイン", "未ログイン", "メール+パスワード"],
    ["S007", "新規登録", "未ログイン", "プロフィール+好み登録"],
    ["S008", "マイページ", "ログイン済", "ダッシュボード・好み"],
    ["S009", "注文履歴", "ログイン済", "詳細・再注文・領収書"],
    ["S010", "定期便管理", "ログイン済", "次回スキップ・変更・解約"],
    ["S011", "BtoB 申込", "BtoB 候補", "書類アップロード・申請"],
    ["S012", "BtoB ダッシュボード", "BtoB 承認済", "一括発注・請求書"],
  ];
  const adminScreens: [string, string, string][] = [
    ["A001", "ダッシュボード", "KPI サマリー (受注/売上/在庫アラート)"],
    ["A002", "商品管理", "CRUD・在庫・安全在庫しきい値"],
    ["A003", "在庫管理", "Shippinno 同期状態・手動補正"],
    ["A004", "受注管理", "ステータス変更・CSV エクスポート"],
    ["A005", "顧客管理", "BtoC/BtoB 一覧・与信審査"],
    ["A006", "BtoB 与信", "申込書類確認・承認/否認"],
    ["A007", "クーポン管理", "発行・期限・利用状況"],
    ["A008", "メール配信", "ステップ配信テンプレート"],
    ["A009", "レポート", "売上/離脱/レコメンド精度"],
    ["A010", "監査ログ", "管理者の全操作履歴"],
  ];
  return (
    <RichSectionCard num={6} title="画面・UX 概要" sourceSteps={[4]}>
      <RichSubsection title="一般ユーザー向け画面 (12 画面)">
        <div className="rd-table-wrap">
          <table>
            <thead><tr><th>画面 ID</th><th>画面名</th><th>対象</th><th>役割</th></tr></thead>
            <tbody>{userScreens.map((r, i) => (
              <tr key={i}>
                <td><code className="rd-code"><E id={`screens/u${i}-id`} value={r[0]} /></code></td>
                <td><E id={`screens/u${i}-name`} value={r[1]} /></td>
                <td><E id={`screens/u${i}-target`} value={r[2]} /></td>
                <td><E id={`screens/u${i}-role`} value={r[3]} multiline /></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </RichSubsection>
      <RichSubsection title="管理者向け画面 (10 画面)">
        <div className="rd-table-wrap">
          <table>
            <thead><tr><th>画面 ID</th><th>画面名</th><th>役割</th></tr></thead>
            <tbody>{adminScreens.map((r, i) => (
              <tr key={i}>
                <td><code className="rd-code"><E id={`screens/a${i}-id`} value={r[0]} /></code></td>
                <td><E id={`screens/a${i}-name`} value={r[1]} /></td>
                <td><E id={`screens/a${i}-role`} value={r[2]} multiline /></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </RichSubsection>
      <RichSubsection title="主要ユーザーフロー">
        <div className="rd-flow-block">
          <div className="rd-flow-title"><E id="screens/flow-1-title" value="新規購入 (BtoC)" /></div>
          <div className="rd-flow-steps">
            <L id="screens/flow-1" listType="number" items={[
              "S001 トップ → S002 商品一覧 → S003 商品詳細",
              "S004 カート → S006 ログイン (未登録なら S007)",
              "S005 チェックアウト → Stripe → 完了画面 → S008 マイページ",
            ]} />
          </div>
        </div>
        <div className="rd-flow-block">
          <div className="rd-flow-title"><E id="screens/flow-2-title" value="定期便スキップ" /></div>
          <div className="rd-flow-steps">
            <L id="screens/flow-2" listType="number" items={[
              "確認メール (配送 7 日前) → リンク → S008 マイページ",
              "S010 定期便管理 → 該当便「スキップ」 → 確認モーダル → 完了",
            ]} />
          </div>
        </div>
      </RichSubsection>
    </RichSectionCard>
  );
}

/* ════ Data ════ */
export function DataTab() {
  const tables: [string, string, string][] = [
    ["users", "id (uuid PK), email (unique), role, password_hash, preferences_jsonb, created_at", "顧客 + 管理者を共通保持。role で識別"],
    ["products", "id (uuid PK), sku, name, slug, roast_level, origin, price, stock_qty, safety_stock, status", "Shippinno と双方向同期"],
    ["orders", "id (uuid PK), user_id (FK), total, status, payment_method, shipping_addr_jsonb, placed_at", "注文ヘッダ"],
    ["order_items", "id (uuid PK), order_id (FK), product_id (FK), qty, unit_price", "注文明細"],
    ["subscriptions", "id (uuid PK), user_id (FK), product_id (FK), cycle_weeks, next_ship_date, status", "Stripe Subscription と紐付け"],
    ["btob_accounts", "id (uuid PK), user_id (FK unique), company_name, credit_status, monthly_limit_yen, approved_at", "BtoB 与信情報"],
    ["coupons", "id (uuid PK), code, type, discount_yen, valid_from, valid_to, max_uses", "クーポン定義"],
    ["audit_logs", "id (uuid PK), actor_id, action, target_type, target_id, payload_jsonb, created_at", "管理操作の全履歴"],
  ];
  return (
    <RichSectionCard num={7} title={`データ構造 (主要 ${tables.length} テーブル)`} sourceSteps={[4]}>
      <div className="rd-table-wrap">
        <table>
          <thead><tr><th>テーブル名</th><th>主要カラム</th><th>役割・関係</th></tr></thead>
          <tbody>{tables.map((r, i) => (
            <tr key={i}>
              <td><code className="rd-code"><E id={`data/r${i}-name`} value={r[0]} /></code></td>
              <td><E id={`data/r${i}-cols`} value={r[1]} multiline /></td>
              <td><E id={`data/r${i}-role`} value={r[2]} multiline /></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </RichSectionCard>
  );
}

/* ════ Integrations ════ */
export function IntegrationsTab() {
  const rows: [string, string, string, string][] = [
    ["Stripe", "BtoC カード決済 + 定期便 Subscription", "REST API + Webhook", "確定"],
    ["Paid", "BtoB 請求書払い・与信", "REST API", "仮説"],
    ["Shippinno", "倉庫・配送・在庫同期", "REST API (1 時間バッチ)", "確定"],
    ["SendGrid", "トランザクションメール + ステップ配信", "SMTP / API", "確定"],
    ["Google Analytics 4", "e コマースイベント・コンバージョン計測", "gtag.js", "確定"],
    ["Google Search Console", "SEO 計測", "API", "確定"],
    ["Slack", "受注通知・在庫アラート", "Incoming Webhook", "確定"],
  ];
  return (
    <RichSectionCard num={8} title="外部連携" sourceSteps={[4]}>
      <div className="rd-table-wrap">
        <table>
          <thead><tr><th>サービス</th><th>用途</th><th>連携方式</th><th>状態</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td><E id={`integrations/r${i}-svc`} value={r[0]} /></td>
                <td><E id={`integrations/r${i}-use`} value={r[1]} multiline /></td>
                <td><E id={`integrations/r${i}-how`} value={r[2]} /></td>
                <td><span className={`rd-badge rd-badge-${r[3] === "確定" ? "confirmed" : "hypothesis"}`}>{r[3]}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </RichSectionCard>
  );
}

/* ════ Legal ════ */
export function LegalTab() {
  const regs: [string, string, string, string][] = [
    ["特定商取引法", "必須", "F002 商品カタログ・F005 定期便・F011 マイページ", "表記ページ + 解約導線 + 改正特商法 2022 対応"],
    ["景品表示法", "必須", "F002 商品カタログ・F014 クーポン", "二重価格の根拠資料 6 か月保管・優良/有利誤認禁止"],
    ["個人情報保護法", "必須", "F001 認証・F008 マイページ", "利用目的明示・同意取得・開示請求窓口"],
    ["食品表示法", "必須", "F002 商品カタログ", "アレルギー表示 (添加物・配合)"],
    ["改正特商法 (2022)", "必須", "F005 定期便", "申込と同等手段で解約完了する導線"],
    ["下請法", "条件付", "F006 BtoB", "支払サイト 60 日以内・取引基本契約"],
  ];
  const features: [string, string, string][] = [
    ["F-LGL-01", "特定商取引法に基づく表記ページ + フッター固定リンク", "特商法"],
    ["F-LGL-02", "プライバシーポリシー / 利用規約 + 新規登録時の同意チェック", "個人情報保護法"],
    ["F-LGL-03", "Cookie 同意バナー (必須/分析/マーケティングを個別選択)", "改正個情法"],
    ["F-LGL-04", "個人情報開示請求フォーム + 30 日以内応答", "個人情報保護法"],
    ["F-LGL-05", "定期便 1 クリック解約導線", "改正特商法 2022"],
    ["F-LGL-06", "アレルギー表示の必須項目化", "食品表示法"],
  ];
  return (
    <RichSectionCard num={9} title="法的考慮・コンプライアンス" sourceSteps={[5]}>
      <RichSubsection title="9-1. 業種・取扱データ判定">
        <div className="rd-info-grid">
          {([
            ["業種", "EC・通販 (食品 BtoC + BtoB)"],
            ["取扱データ", "個人情報 + 決済 (Stripe 経由) + 嗜好"],
            ["ビジネスモデル", "BtoC + BtoB (自社販売)"],
            ["取扱区域", "日本国内のみ"],
          ] as const).map(([l, v], i) => (
            <div className="rd-info-card" key={i}>
              <div className="rd-info-card-label"><E id={`legal/d${i}-l`} value={l} /></div>
              <div className="rd-info-card-value"><E id={`legal/d${i}-v`} value={v} multiline /></div>
            </div>
          ))}
        </div>
      </RichSubsection>

      <RichSubsection title="9-2. 適用法令・規制 一覧">
        <div className="rd-table-wrap">
          <table>
            <thead><tr><th>法令名</th><th>適用要否</th><th>影響を受ける機能</th><th>対応方針</th></tr></thead>
            <tbody>
              {regs.map((r, i) => (
                <tr key={i}>
                  <td><E id={`legal/reg${i}-name`} value={r[0]} /></td>
                  <td><span className={`rd-badge rd-badge-${r[1] === "必須" ? "must" : "should"}`}>{r[1]}</span></td>
                  <td><E id={`legal/reg${i}-feat`} value={r[2]} multiline /></td>
                  <td><E id={`legal/reg${i}-action`} value={r[3]} multiline /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </RichSubsection>

      <RichSubsection title="9-3. 必要な実装要件 (機能要件への追加)">
        <div className="rd-table-wrap">
          <table>
            <thead><tr><th>機能 ID</th><th>内容</th><th>紐づく法令</th></tr></thead>
            <tbody>{features.map((r, i) => (
              <tr key={i}>
                <td><code className="rd-code"><E id={`legal/f${i}-id`} value={r[0]} /></code></td>
                <td><E id={`legal/f${i}-c`} value={r[1]} multiline /></td>
                <td><E id={`legal/f${i}-law`} value={r[2]} /></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </RichSubsection>

      <RichSubsection title="9-4. 非機能要件への追加">
        <L id="legal/nfr" items={[
          "個人情報のアクセスログを 3 年保管 (改正個情法準拠)",
          "決済情報は Stripe トークン化により自社 DB に保存しない (PCI DSS SAQ-A)",
          "管理画面アクセスは 2FA 必須 + IP 制限",
          "身分証画像 (BtoB 申込) は暗号化保存 (Cloudflare R2)",
        ]} />
      </RichSubsection>

      <RichSubsection title="9-5. 法的リスク・要確認事項">
        <L id="legal/risks" items={[
          "[要確認] 定期便の最低継続回数を約款に明記しないと景表法のおとり広告に該当する恐れ",
          "[要確認] BtoB 与信判断を AI 自動化する場合、説明責任の根拠保持が必要",
          "[対応済] 社内ナレッジ #legal-001 「サブスク EC の解約導線テンプレート」参照",
        ]} />
      </RichSubsection>
    </RichSectionCard>
  );
}

/* ════ Risks ════ */
export function RisksTab() {
  const rows: [string, string, string, string, string][] = [
    ["技術", "Shippinno API のレート制限 (1 分 100 req)", "高", "中", "キュー処理で吸収・指数バックオフ"],
    ["運用", "倉庫スタッフが管理画面に不慣れ", "中", "高", "リリース 2 週間前に研修 + 動画マニュアル"],
    ["要件", "BtoB 与信ロジックが未確定", "高", "中", "8/15 までに業務側で基準確定"],
    ["スケジュール", "9 月リリースに対しデザイン未着手", "高", "中", "6 月中にデザイン完了が前提"],
    ["法務", "改正特商法の解約導線実装漏れ", "高", "低", "リリース前に法務レビュー必須"],
    ["セキュリティ", "管理者の権限昇格による情報漏洩", "高", "低", "RBAC + 監査ログ + 2FA"],
  ];
  return (
    <RichSectionCard num={10} title="リスク・懸念点" sourceSteps={[6]}>
      <div className="rd-table-wrap">
        <table>
          <thead><tr><th>種別</th><th>内容</th><th>影響度</th><th>発生確率</th><th>対応策</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td><E id={`risks/r${i}-cat`} value={r[0]} /></td>
                <td><E id={`risks/r${i}-content`} value={r[1]} multiline /></td>
                <td><span className={`rd-badge rd-badge-${r[2] === "高" ? "must" : "should"}`}>{r[2]}</span></td>
                <td><span className={`rd-badge rd-badge-${r[3] === "高" ? "must" : "should"}`}>{r[3]}</span></td>
                <td><E id={`risks/r${i}-action`} value={r[4]} multiline /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </RichSectionCard>
  );
}

/* ════ Infra Cost ════ */
export function InfraCostTab() {
  const phases: Array<{
    title: string; sub: string; amount: string; color: string;
    detail: Array<React.ReactNode>;
  }> = [
    {
      title: "初期フェーズ", sub: "〜100 件累積ユーザー",
      amount: "ほぼ ¥0", color: "var(--bf-primary)",
      detail: [
        <>Vercel Hobby: <strong>無料</strong></>,
        <>Supabase Free (500MB): <strong>無料</strong></>,
        <>Cloudflare R2 (10GB): <strong>無料</strong></>,
        <>SendGrid Free (100通/日): <strong>無料</strong></>,
        <>Stripe: 決済手数料 3.6% のみ</>,
      ],
    },
    {
      title: "成長フェーズ", sub: "〜300 件/月 累積 1,000 人規模",
      amount: "¥5,000〜8,000/月", color: "#2563eb",
      detail: [
        <>Vercel Pro: ¥3,000</>,
        <>Supabase Pro: ¥3,500</>,
        <>SendGrid Essentials: ¥1,500</>,
        <>Cloudflare R2: ¥500〜</>,
        <>Stripe: 売上 × 3.6%</>,
      ],
    },
    {
      title: "本格稼働フェーズ", sub: "月 500 件 / 累積 6,000 人規模",
      amount: "¥10,000〜15,000/月", color: "#7c3aed",
      detail: [
        <>Vercel Pro: ¥3,000</>,
        <>Supabase Pro: ¥3,500〜</>,
        <>SendGrid Pro: ¥3,500</>,
        <>Cloudflare R2: ¥1,000〜</>,
        <>Stripe: 売上 × 3.6%</>,
        <span style={{ color: "var(--bf-text-4)" }}>※ Shippinno は契約内容次第</span>,
      ],
    },
  ];
  return (
    <RichSectionCard num={11} title="インフラコスト試算 (3 段階)" sourceSteps={[6]}>
      <div className="rd-cost-grid">
        {phases.map((p) => (
          <div className="rd-cost-card" key={p.title}>
            <div className="rd-cost-card-header" style={{ background: p.color }}>
              {p.title}
              <br />
              <small style={{ fontWeight: 400, fontSize: 10 }}>{p.sub}</small>
            </div>
            <div className="rd-cost-card-body">
              <div className="rd-cost-card-amount" style={{ color: p.color }}>{p.amount}</div>
              <ul className="rd-cost-card-detail">
                {p.detail.map((d, i) => <li key={i}>{d}</li>)}
              </ul>
            </div>
          </div>
        ))}
      </div>
      <div className="rd-notice-warn">
        <span>⚠️</span>
        <div><strong>Shippinno のコストに注意</strong>　月 500 件超の出荷で従量課金 (1 件 ¥80〜) が発生する場合、インフラコストの中で最大の費用となる可能性があります。契約内容と件数別単価を早急に確認してください。</div>
      </div>
    </RichSectionCard>
  );
}

/* ════ Scope & Schedule ════ */
export function ScopeTab() {
  const scopeIn = [
    "商品カタログ・検索・絞り込み (焙煎度/産地/抽出方法)",
    "カート・購入・決済 (Stripe Checkout)",
    "サブスクリプション (定期便: スキップ/変更/解約)",
    "BtoB 申込・与信・専用価格・請求書払い (Paid)",
    "顧客マイページ (注文履歴・好み登録・定期便管理)",
    "管理画面 (商品/在庫/受注/顧客/レポート)",
    "Shippinno 連携 (在庫同期・配送)",
    "メール自動通知 (12 種テンプレート)",
    "ステップ配信 (登録後 3 日 / 7 日 / 30 日)",
    "現行 BASE データ移行 (商品 80 点・顧客 1,200 件)",
    "請求書・領収書自動発行 (PDF)",
    "Cookie 同意バナー / 法令準拠ページ",
  ];
  const scopeOut = [
    "実店舗 POS 連携",
    "海外配送・国際決済",
    "B2B EDI 連携",
    "ロイヤリティポイントシステム",
    "AI レコメンドの自社学習モデル (将来フェーズ)",
    "モバイルアプリ (PWA で代替)",
  ];
  const schedulePhases = [
    { label: "5月", name: "要件確定・設計", cls: "s-m1" },
    { label: "6月", name: "基盤・商品・カート", cls: "s-m2" },
    { label: "7月", name: "定期便・BtoB・管理", cls: "s-m2" },
    { label: "8月前半", name: "Shippinno 連携・テスト", cls: "s-m3" },
    { label: "9月初週", name: "本番リリース", cls: "s-release" },
  ];
  const scheduleRows: [string, string][] = [
    ["5 月: 要件確定・設計", "DB 設計・画面設計・Stripe 設定・Shippinno 接続確認・Paid 与信フロー確定"],
    ["6 月: 基盤・商品・カート", "認証・商品 CRUD・カート・Stripe Checkout・好み登録"],
    ["7 月: 定期便・BtoB・管理", "Stripe Subscription・BtoB 申込/与信・管理画面・受注/在庫"],
    ["8 月前半: Shippinno・QA", "Shippinno 同期 (1 時間バッチ)・通知メール 12 種・ステップ配信・結合テスト"],
    ["8 月後半: テスト・移行", "セキュリティ確認・本番環境構築・BASE データ移行・受け入れテスト"],
    ["9 月初週: 納品", "本番切替・LP リダイレクト・運用研修"],
  ];
  const costRows: [string, string][] = [
    ["システム開発費 (全 14 機能)", "3,000,000〜3,500,000 円"],
    ["デザイン費 (UI・マイページ・管理画面)", "開発費に含む"],
    ["BASE データ移行スクリプト", "別途見積もり"],
  ];
  const opsRows: [string, string][] = [
    ["ライトプラン (月 5 時間)", "¥30,000"],
    ["スタンダードプラン (月 10 時間)", "¥50,000"],
    ["プレミアムプラン (月 20 時間)", "¥90,000"],
  ];
  return (
    <RichSectionCard num={13} title="開発スコープ・スケジュール" sourceSteps={[7]}>
      <RichSubsection title="スコープ">
        <div className="rd-scope-grid">
          <div>
            <div className="rd-scope-in-label">✅ 含むもの</div>
            <ul>{scopeIn.map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
          <div>
            <div className="rd-scope-out-label">❌ 含まないもの (将来フェーズ)</div>
            <ul>{scopeOut.map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
        </div>
      </RichSubsection>

      <RichSubsection title="開発優先順位・スケジュール">
        <div className="rd-schedule-bar">
          {schedulePhases.map((p, i) => (
            <div className={`rd-schedule-phase ${p.cls}`} key={i}>
              <span className="rd-ph-label">{p.label}</span>
              <span className="rd-ph-name">{p.name}</span>
            </div>
          ))}
        </div>
        <div className="rd-table-wrap">
          <table>
            <thead><tr><th>期間</th><th>作業内容</th></tr></thead>
            <tbody>{scheduleRows.map((r) => <tr key={r[0]}><td><strong>{r[0]}</strong></td><td>{r[1]}</td></tr>)}</tbody>
          </table>
        </div>
      </RichSubsection>

      <RichSubsection title="費用概算">
        <div className="rd-table-wrap">
          <table>
            <thead><tr><th>項目</th><th>金額 (税抜)</th></tr></thead>
            <tbody>{costRows.map((r) => <tr key={r[0]}><td>{r[0]}</td><td>{r[1]}</td></tr>)}</tbody>
          </table>
        </div>
        <div className="rd-table-wrap" style={{ marginTop: 12 }}>
          <table>
            <thead><tr><th>運用コスト (保守)</th><th>月額 (目安・税抜)</th></tr></thead>
            <tbody>{opsRows.map((r) => <tr key={r[0]}><td>{r[0]}</td><td>{r[1]}</td></tr>)}</tbody>
          </table>
        </div>
      </RichSubsection>
    </RichSectionCard>
  );
}

/* ════ History ════ */
export function HistoryTab() {
  const rows: Array<{ ver: string; date: string; change: React.ReactNode; author: string; bold?: boolean }> = [
    {
      ver: "v1.0", date: "2026 年 4 月 17 日",
      change: "初版作成 (ヒアリング・要件定義スキルに基づく仮説ベース版)",
      author: "株式会社 ENGINE BASE　高本 聖斗",
    },
    {
      ver: "v1.1", date: "2026 年 4 月 24 日",
      change: "STEP 1-3 の確認後、機能要件詳細を追加",
      author: "株式会社 ENGINE BASE　高本 聖斗",
    },
    {
      ver: "v2.0", date: "2026 年 5 月 8 日", bold: true,
      change: (
        <>
          打ち合わせを踏まえた確定版に更新。主要変更:
          <ul style={{ marginTop: 4 }}>
            <li>決済を Stripe Subscription に確定</li>
            <li>BtoB 与信を Paid 連携に確定</li>
            <li>Shippinno 連携を 1 時間バッチに統一</li>
            <li>メール配信 (12 種) + ステップ配信 (3/7/30 日) を追加</li>
            <li>法的考慮 (改正特商法 2022・食品表示法) を反映</li>
            <li>インフラコスト 3 段階試算を追加</li>
          </ul>
        </>
      ),
      author: "株式会社 ENGINE BASE　高本 聖斗",
    },
  ];
  return (
    <RichSectionCard num={14} title="改訂履歴" sourceSteps={[7]}>
      <div className="rd-table-wrap">
        <table>
          <thead><tr><th>バージョン</th><th>日付</th><th>変更内容</th><th>作成者</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.ver}>
                <td>{r.bold ? <strong>{r.ver}</strong> : r.ver}</td>
                <td>{r.bold ? <strong>{r.date}</strong> : r.date}</td>
                <td>{r.change}</td>
                <td>{r.author}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ color: "var(--bf-text-4)", fontSize: 12, marginTop: 12 }}>
        ※ <span className="rd-badge rd-badge-hypothesis">【仮説】</span> マークが残っている項目は次回打ち合わせで確定後、v2.1 に更新します。<br />
        ※ 内容の無断転用・二次利用はご遠慮ください。
      </p>
    </RichSectionCard>
  );
}

/* ════ Unresolved ════ */
export function UnresolvedTab() {
  const items: { topic: string; impact: string; flag: "high" | "medium" | "resolved"; note?: string }[] = [
    { topic: "BtoB 請求書発行は Paid 経由か自社発行か", impact: "支払サイト・経理処理に直結。税理士確認待ち", flag: "high", note: "未確認" },
    { topic: "メールマーケティングのステップ配信は 3 本か 5 本か", impact: "SendGrid のテンプレート設計が変わる", flag: "medium", note: "仮説" },
    { topic: "定期便同梱クーポンチラシの印刷可否", impact: "倉庫オペレーションが変わる", flag: "medium", note: "未確認" },
    { topic: "BtoC のレビュー投稿時クーポン額", impact: "F013 の仕様", flag: "resolved", note: "確定: ¥500 / 1 回限り" },
    { topic: "Cookie バナーの「マーケティング」分類の定義", impact: "GA4 / 広告タグの扱い", flag: "high", note: "法務確認待ち" },
  ];
  return (
    <RichSectionCard num={12} title="未確認事項" sourceSteps={[6]}>
      <div className="rd-unresolved-list">
        {items.map((it, i) => (
          <div className="rd-unresolved-item" key={i}>
            <div className={`rd-unresolved-priority ${it.flag}`}>{it.flag === "high" ? "高" : it.flag === "medium" ? "中" : "済"}</div>
            <div className="rd-unresolved-content">
              <div className="rd-unresolved-topic"><E id={`unresolved/i${i}-topic`} value={it.topic} multiline /></div>
              <div className="rd-unresolved-impact"><E id={`unresolved/i${i}-impact`} value={it.impact} multiline /></div>
              {it.note && (
                <span className={`rd-unresolved-${it.flag === "resolved" ? "confirmed" : "hypothesis"}`}>
                  {it.note}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </RichSectionCard>
  );
}

/* ════ ディスパッチャー ════ */
export function RichTabContent({ tabKey }: { tabKey: string }) {
  switch (tabKey) {
    case "overview": return <OverviewTab />;
    case "users": return <UsersTab />;
    case "features": return <FeaturesTab />;
    case "functional": return <FunctionalTab />;
    case "nonfunctional": return <NonFunctionalTab />;
    case "screens": return <ScreensTab />;
    case "data": return <DataTab />;
    case "integrations": return <IntegrationsTab />;
    case "legal": return <LegalTab />;
    case "risks": return <RisksTab />;
    case "infra_cost": return <InfraCostTab />;
    case "unresolved": return <UnresolvedTab />;
    case "scope": return <ScopeTab />;
    case "history": return <HistoryTab />;
    default: return <div style={{ padding: 40, color: "var(--bf-text-3)" }}>このタブは未実装です。</div>;
  }
}
