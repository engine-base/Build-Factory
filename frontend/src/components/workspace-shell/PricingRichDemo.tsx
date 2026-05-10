"use client";

import { StarIcon } from "lucide-react";

/**
 * 価格設計 デモ用リッチビュー (テンプレモック準拠)
 * - 4 タブ: 原価試算 / 市場相場 / 価値試算 / 推奨レンジ・採用案
 * - Hero / Range Bar / Stat / Feature Table / Competitor Bar / ROI Cards / Reasoning
 */

export const PR_TAB_NUMBER: Record<string, number> = {
  cost_estimate: 1, market_research: 2, value_calc: 3, recommended_range: 4,
};

/* ════════ 推奨レンジ・採用案 ════════ */
function RecommendedTab() {
  return (
    <>
      {/* Hero */}
      <div className="pr-hero">
        <div className="pr-hero-label">推奨見積金額</div>
        <div className="pr-hero-amount">
          320<span className="pr-yen">万円</span><span className="pr-tax">税抜</span>
        </div>
        <div className="pr-hero-meta">
          <div className="pr-hero-meta-item">
            <div className="key">粗利率</div>
            <div className="val">48%</div>
            <div className="sub">利益 154 万円</div>
          </div>
          <div className="pr-hero-meta-item">
            <div className="key">競合相対</div>
            <div className="val">71%</div>
            <div className="sub">中堅 Web 制作 350 万円基準</div>
          </div>
          <div className="pr-hero-meta-item">
            <div className="key">投資回収</div>
            <div className="val">6.4 か月</div>
            <div className="sub">月 50 万円効果想定</div>
          </div>
        </div>
      </div>

      {/* Range Bar */}
      <div className="pr-range-card">
        <div className="pr-range-title">3 軸サマリー — コスト下限・競合中央・価値上限</div>
        <div className="pr-range-bar">
          <div className="pr-range-track" />
          <div className="pr-range-marker pr-cost" style={{ left: "18%" }}>
            <div className="pr-pin-amount">237 万</div>
            <div className="pr-pin-label">コスト下限<br />(粗利 30%)</div>
          </div>
          <div className="pr-range-marker pr-market" style={{ left: "50%" }}>
            <div className="pr-pin-amount">350 万</div>
            <div className="pr-pin-label">競合中央</div>
          </div>
          <div className="pr-range-marker pr-recommended" style={{ left: "64%" }}>
            <div className="pr-pin-amount inline-flex items-center gap-1">320 万 <StarIcon className="w-3 h-3" aria-label="recommended" /> 推奨</div>
            <div className="pr-pin-label">採用案</div>
          </div>
          <div className="pr-range-marker pr-value" style={{ left: "78%" }}>
            <div className="pr-pin-amount">560 万</div>
            <div className="pr-pin-label">価値上限<br />(1 年回収)</div>
          </div>
        </div>
      </div>

      {/* 採用根拠 */}
      <div className="pr-section">
        <div className="pr-section-title">採用根拠</div>
        <div className="pr-reasoning">
          {[
            ["①", "粗利 40% を確保しつつ競合中央の中間値で着地",
              "コスト下限 (粗利 40% 確保) 277 万円と競合中央 350 万円の中間値で 320 万円。値下げ余地も残しつつ確実な利益を確保。"],
            ["②", "顧客の 6 か月以内回収条件を満たす",
              "月 50 万円の効果想定で 6.4 か月で投資回収。短期 ROI が見えるため社内稟議が通りやすい。"],
            ["③", "AI 速度感の優位を価格に転嫁",
              "中堅 Web 制作の 71% で同等品質を提供。短納期 (1-2 か月) を強みとして打ち出せる。"],
            ["④", "値引きバッファ",
              "290 万円まで下げても粗利 30% 確保可能。営業ネゴ時の最終ライン。"],
          ].map(([icon, title, detail]) => (
            <div className="pr-reason-row" key={icon}>
              <div className="pr-reason-icon">{icon}</div>
              <div className="pr-reason-body">
                <div className="pr-reason-title">{title}</div>
                <div className="pr-reason-detail">{detail}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 引き継ぎ */}
      <div className="pr-section">
        <div className="pr-section-title">見積書フェーズへの引き継ぎ事項</div>
        <table className="pr-feature-table">
          <tbody>
            <tr><td className="pr-th-cell">構築費</td><td><strong>320 万円</strong> (税抜)</td></tr>
            <tr><td className="pr-th-cell">月額保守</td><td>月 5 万円</td></tr>
            <tr><td className="pr-th-cell">支払条件</td><td>着手金 30% / 中間 30% / 検収後 40%</td></tr>
            <tr><td className="pr-th-cell">値引き戦略</td><td>290 万円まで OK・それ以下は要相談</td></tr>
            <tr><td className="pr-th-cell">オプション</td><td>SEO 月 3 万 / 広告運用 月 5 万 / 追加開発 1 時間 1.5 万</td></tr>
          </tbody>
        </table>
      </div>
    </>
  );
}

/* ════════ 原価試算 ════════ */
function CostTab() {
  const features: Array<[string, string, string, number]> = [
    ["F001", "認証・会員管理 (eKYC 連携)", "登録 / ログイン / 管理者承認", 6],
    ["F002", "商品カタログ・検索", "一覧 / 絞り込み / 全文検索 / ページネーション", 8],
    ["F003", "商品詳細・レコメンド", "詳細 UI + 好み連動レコメンド", 5],
    ["F004", "カート・購入・決済 (Stripe)", "カート / Checkout / Webhook / 二重課金防止", 7],
    ["F005", "サブスクリプション (定期便)", "Stripe Subscription + スキップ/解約", 10],
    ["F006", "BtoB 申込・与信 (Paid 連携)", "申込フォーム + 書類 + 与信フロー", 8],
    ["F007", "BtoB 専用ダッシュボード", "一括発注 + 専用価格", 6],
    ["F008", "顧客マイページ", "注文履歴 / 好み登録 / 定期便管理", 5],
    ["F009", "管理: 商品・在庫", "CRUD + Shippinno 同期 + 安全在庫アラート", 8],
    ["F010", "管理: 受注・出荷", "ステータス管理 + CSV エクスポート", 5],
    ["F011", "管理: 顧客・与信審査", "BtoB 申込 + 与信判断", 4],
    ["F012-14", "メール / レビュー / クーポン", "計 3 機能", 6],
  ];
  return (
    <>
      <div className="pr-stat-grid">
        <div className="pr-stat-card pr-cost-c">
          <div className="key">人件費</div>
          <div className="num">123<span className="yen">万円</span></div>
          <div className="sub">高本 60 人日 + AI 90 人日 + 外注 30 人日</div>
        </div>
        <div className="pr-stat-card pr-tools-c">
          <div className="key">ツール・インフラ</div>
          <div className="num">6<span className="yen">万円</span></div>
          <div className="sub">構築期 (4 か月)</div>
        </div>
        <div className="pr-stat-card pr-outsource-c">
          <div className="key">外注費</div>
          <div className="num">37<span className="yen">万円</span></div>
          <div className="sub">デザイン 25 万 + 移行スクリプト 12 万</div>
        </div>
        <div className="pr-stat-card pr-total-c">
          <div className="key">合計コスト (下限)</div>
          <div className="num">166<span className="yen">万円</span></div>
          <div className="sub">粗利 40% で 277 万・粗利 30% で 237 万</div>
        </div>
      </div>

      <div className="pr-section">
        <div className="pr-section-title">機能別工数試算 (合計 90 人日)</div>
        <table className="pr-feature-table">
          <thead>
            <tr><th style={{ width: 80 }}>機能 ID</th><th>機能名</th><th>内訳</th><th style={{ width: 100 }}>工数</th></tr>
          </thead>
          <tbody>
            {features.map(([id, name, detail, effort]) => (
              <tr key={id}>
                <td><span className="pr-id-code">{id}</span></td>
                <td>{name}</td>
                <td>{detail}</td>
                <td className="pr-effort">{effort}<span className="pr-unit">人日</span></td>
              </tr>
            ))}
            <tr>
              <td colSpan={2} style={{ color: "var(--bf-text-3)", fontStyle: "italic" }}>設計 / テスト / デプロイ / ドキュメント</td>
              <td>共通工数</td>
              <td className="pr-effort">12<span className="pr-unit">人日</span></td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={3} style={{ textAlign: "right", fontWeight: 700 }}>合計</td>
              <td className="pr-effort">90<span className="pr-unit">人日</span></td>
            </tr>
          </tfoot>
        </table>
        <div className="pr-note">人件費単価: 高本 1.2 万円/日 / AI 社員 0.3 万円/日 / 外注 0.8 万円/日</div>
      </div>
    </>
  );
}

/* ════════ 市場相場 ════════ */
function MarketTab() {
  const competitors: Array<[string, string, number, boolean]> = [
    ["中堅 Web 制作会社", "350 〜 600 万円", 75, false],
    ["Shopify Plus 構築会社", "250 〜 400 万円", 50, false],
    ["フルスタックフリーランス", "180 〜 350 万円", 38, false],
    ["Build-Factory", "280 〜 350 万円", 55, true],
  ];
  return (
    <>
      <div className="pr-section">
        <div className="pr-section-title">競合相場 (類似案件・食品 EC + BtoB 連携)</div>
        <div className="pr-compete">
          {competitors.map(([name, amount, width, isUs]) => (
            <div key={name} className={`pr-compete-row ${isUs ? "pr-us" : ""}`}>
              <div className="pr-compete-name">
                {name}
                {isUs && <span className="pr-tag">自社</span>}
              </div>
              <div className="pr-compete-bar-wrap">
                <div className="pr-compete-bar" style={{ width: `${width}%` }} />
              </div>
              <div className="pr-compete-amount">{amount}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="pr-section">
        <div className="pr-section-title">自社ポジション</div>
        <div className="pr-stat-grid">
          <div className="pr-stat-card">
            <div className="key">強み</div>
            <div className="num" style={{ fontSize: 14 }}>短納期 + AI 反復</div>
            <div className="sub">通常 3-6 か月 → 1-2 か月</div>
          </div>
          <div className="pr-stat-card">
            <div className="key">弱み</div>
            <div className="num" style={{ fontSize: 14 }}>大型ブランディング</div>
            <div className="sub">複雑カスタマイズ実績不足</div>
          </div>
          <div className="pr-stat-card pr-total-c">
            <div className="key">ポジション</div>
            <div className="num" style={{ fontSize: 18 }}>中堅の 65-75%</div>
            <div className="sub">同等品質を提供</div>
          </div>
        </div>
      </div>
    </>
  );
}

/* ════════ 価値試算 ════════ */
function ValueTab() {
  return (
    <>
      <div className="pr-section">
        <div className="pr-section-title">顧客 ROI 試算</div>
        <div className="pr-roi-flex">
          <div className="pr-roi-card pr-benefit">
            <div className="label">月次効果</div>
            <div className="num">42 〜 67<span className="unit">万円/月</span></div>
            <div className="breakdown">
              ・BtoB 機会損失回復: 25-50 万<br />
              ・運用工数削減: 9 万<br />
              ・在庫管理自動化: 8 万
            </div>
          </div>
          <div className="pr-roi-card pr-payback">
            <div className="label">年間効果</div>
            <div className="num">504 〜 804<span className="unit">万円/年</span></div>
            <div className="breakdown">
              ・1 年回収許容: 350-560 万円<br />
              ・6 か月回収: 250-400 万円<br />
              ・予算 70-80%: 210-400 万円
            </div>
          </div>
        </div>
      </div>

      <div className="pr-section">
        <div className="pr-section-title">価値ベースの価格上限</div>
        <div className="pr-stat-grid">
          <div className="pr-stat-card pr-cost-c">
            <div className="key">1 年回収許容</div>
            <div className="num">350-560<span className="yen">万円</span></div>
            <div className="sub">年間効果の 70%</div>
          </div>
          <div className="pr-stat-card pr-outsource-c">
            <div className="key">6 か月回収</div>
            <div className="num">250-400<span className="yen">万円</span></div>
            <div className="sub">半年効果ベース</div>
          </div>
          <div className="pr-stat-card pr-total-c">
            <div className="key">価値上限 (推奨)</div>
            <div className="num">350<span className="yen">万円</span></div>
            <div className="sub">1 年回収 + 予算 70%</div>
          </div>
        </div>
      </div>
    </>
  );
}

/* ════════ ディスパッチャ ════════ */
export function PricingRichTabContent({ tabKey }: { tabKey: string }) {
  switch (tabKey) {
    case "cost_estimate":     return <CostTab />;
    case "market_research":   return <MarketTab />;
    case "value_calc":        return <ValueTab />;
    case "recommended_range": return <RecommendedTab />;
    default: return <div style={{ padding: 40, color: "var(--bf-text-3)" }}>このタブは未実装です。</div>;
  }
}

/* ════════ スタイル (テンプレモック準拠 + BF tokens) ════════ */
export function PricingRichStyles() {
  return (
    <style>{`
      .pr-rd { font-feature-settings: "palt"; }

      /* Hero */
      .pr-rd .pr-hero {
        background: linear-gradient(135deg, var(--bf-primary) 0%, #1A5FE0 100%);
        border-radius: 16px;
        padding: 32px 36px;
        color: #fff;
        margin-bottom: 28px;
        box-shadow: 0 4px 16px rgba(0,76,217,0.15);
      }
      .pr-rd .pr-hero-label {
        font-size: 11px; font-weight: 700;
        letter-spacing: 0.12em; text-transform: uppercase;
        color: rgba(255,255,255,0.7); margin-bottom: 10px;
      }
      .pr-rd .pr-hero-amount {
        font-size: 56px; font-weight: 800;
        letter-spacing: -0.02em; line-height: 1.1; margin-bottom: 4px;
      }
      .pr-rd .pr-hero-amount .pr-yen { font-size: 28px; font-weight: 600; opacity: 0.85; margin-left: 4px; }
      .pr-rd .pr-hero-amount .pr-tax { font-size: 13px; font-weight: 500; opacity: 0.7; margin-left: 8px; vertical-align: middle; }
      .pr-rd .pr-hero-meta {
        display: grid; grid-template-columns: repeat(3, 1fr);
        gap: 24px; margin-top: 24px; padding-top: 24px;
        border-top: 1px solid rgba(255,255,255,0.2);
      }
      .pr-rd .pr-hero-meta-item .key {
        font-size: 10.5px; font-weight: 700;
        letter-spacing: 0.06em; text-transform: uppercase;
        color: rgba(255,255,255,0.65); margin-bottom: 4px;
      }
      .pr-rd .pr-hero-meta-item .val { font-size: 18px; font-weight: 700; }
      .pr-rd .pr-hero-meta-item .sub { font-size: 11.5px; color: rgba(255,255,255,0.7); margin-top: 2px; }

      /* Range Bar */
      .pr-rd .pr-range-card {
        background: var(--bf-bg-elev); border: 1px solid var(--bf-border);
        border-radius: 12px; padding: 24px 28px; margin-bottom: 20px;
      }
      .pr-rd .pr-range-title {
        font-size: 12px; font-weight: 700; color: var(--bf-text-3);
        letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 20px;
      }
      .pr-rd .pr-range-bar { position: relative; height: 56px; margin: 30px 0 50px; }
      .pr-rd .pr-range-track {
        position: absolute; inset: 22px 0;
        background: linear-gradient(90deg, #DC2626 0%, #F59E0B 35%, #16A34A 65%, #7C3AED 100%);
        border-radius: 6px;
      }
      .pr-rd .pr-range-marker {
        position: absolute; top: 0; width: 2px; height: 56px;
        background: var(--bf-text-2);
      }
      .pr-rd .pr-range-marker.pr-recommended {
        width: 4px; background: var(--bf-primary);
        box-shadow: 0 0 0 4px rgba(0,76,217,0.18);
      }
      .pr-rd .pr-pin-label {
        position: absolute; top: 60px; left: 50%; transform: translateX(-50%);
        font-size: 10.5px; font-weight: 700; color: var(--bf-text-2); white-space: nowrap;
      }
      .pr-rd .pr-pin-amount {
        position: absolute; bottom: 60px; left: 50%; transform: translateX(-50%);
        font-size: 13.5px; font-weight: 700; color: var(--bf-text-1);
        white-space: nowrap; background: var(--bf-bg-elev);
        padding: 2px 8px; border: 1px solid var(--bf-border); border-radius: 4px;
      }
      .pr-rd .pr-range-marker.pr-recommended .pr-pin-amount {
        background: var(--bf-primary); color: #fff; border-color: var(--bf-primary);
        font-size: 14px; font-weight: 800;
      }
      .pr-rd .pr-range-marker.pr-recommended .pr-pin-label { color: var(--bf-primary); font-weight: 800; }

      /* Section */
      .pr-rd .pr-section { margin-bottom: 32px; }
      .pr-rd .pr-section:last-child { margin-bottom: 0; }
      .pr-rd .pr-section-title {
        font-size: 14px; font-weight: 700; color: var(--bf-text-1);
        margin-bottom: 14px; padding-left: 12px;
        border-left: 3px solid var(--bf-primary);
      }

      /* Stat cards */
      .pr-rd .pr-stat-grid {
        display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
        gap: 12px; margin-bottom: 20px;
      }
      .pr-rd .pr-stat-card {
        background: var(--bf-bg-elev); border: 1px solid var(--bf-border);
        border-radius: 10px; padding: 16px 18px; position: relative;
        border-left: 4px solid var(--bf-primary);
      }
      .pr-rd .pr-stat-card.pr-cost-c { border-left-color: #2563EB; }
      .pr-rd .pr-stat-card.pr-tools-c { border-left-color: #06B6D4; }
      .pr-rd .pr-stat-card.pr-outsource-c { border-left-color: #F97316; }
      .pr-rd .pr-stat-card.pr-total-c { border-left-color: #16A34A; background: #DCFCE7; }
      .pr-rd .pr-stat-card .key {
        font-size: 10.5px; font-weight: 700;
        letter-spacing: 0.06em; text-transform: uppercase;
        color: var(--bf-text-4); margin-bottom: 6px;
      }
      .pr-rd .pr-stat-card .num {
        font-size: 24px; font-weight: 800; color: var(--bf-text-1);
        line-height: 1.1; letter-spacing: -0.01em;
      }
      .pr-rd .pr-stat-card .num .yen { font-size: 14px; font-weight: 600; opacity: 0.7; margin-left: 2px; }
      .pr-rd .pr-stat-card .sub { font-size: 11.5px; color: var(--bf-text-3); margin-top: 4px; }

      /* Feature table */
      .pr-rd .pr-feature-table {
        width: 100%; border-collapse: separate; border-spacing: 0;
        background: var(--bf-bg-elev); border: 1px solid var(--bf-border);
        border-radius: 10px; overflow: hidden; font-size: 12.5px; margin-bottom: 16px;
      }
      .pr-rd .pr-feature-table thead th {
        background: #F8FAFC; color: var(--bf-text-3); font-weight: 700;
        text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--bf-divider);
        font-size: 11px; letter-spacing: 0.04em; text-transform: uppercase;
      }
      .pr-rd .pr-feature-table td {
        padding: 10px 14px; border-top: 1px solid var(--bf-divider); vertical-align: middle;
      }
      .pr-rd .pr-feature-table tbody tr:first-child td { border-top: none; }
      .pr-rd .pr-feature-table tbody tr:hover td { background: var(--bf-primary-bg); }
      .pr-rd .pr-feature-table .pr-th-cell { width: 200px; color: var(--bf-text-3); font-weight: 600; }
      .pr-rd .pr-id-code {
        font-family: 'SF Mono', 'Courier New', monospace;
        font-size: 11px; background: var(--bf-primary-bg); color: var(--bf-primary);
        padding: 2px 8px; border-radius: 4px; font-weight: 700; display: inline-block;
      }
      .pr-rd .pr-effort { font-weight: 700; color: var(--bf-text-1); text-align: right; white-space: nowrap; }
      .pr-rd .pr-unit { font-size: 11px; color: var(--bf-text-4); margin-left: 2px; font-weight: 500; }
      .pr-rd .pr-feature-table tfoot td {
        background: var(--bf-primary-bg); font-weight: 700; color: var(--bf-primary);
        border-top: 2px solid var(--bf-primary);
      }
      .pr-rd .pr-feature-table tfoot .pr-effort { color: var(--bf-primary); font-size: 14px; }
      .pr-rd .pr-note {
        font-size: 11.5px; color: var(--bf-text-3);
        background: rgba(0,76,217,0.04); border-left: 3px solid var(--bf-primary);
        padding: 10px 14px; border-radius: 0 6px 6px 0; margin-top: 10px;
      }

      /* Compete */
      .pr-rd .pr-compete { display: grid; grid-template-columns: 1fr; gap: 10px; }
      .pr-rd .pr-compete-row {
        display: grid; grid-template-columns: 200px 1fr 110px;
        gap: 14px; align-items: center; padding: 12px 16px;
        background: var(--bf-bg-elev); border: 1px solid var(--bf-border); border-radius: 8px;
      }
      .pr-rd .pr-compete-row.pr-us {
        border-color: var(--bf-primary); background: var(--bf-primary-bg);
      }
      .pr-rd .pr-compete-name { font-size: 12.5px; font-weight: 700; color: var(--bf-text-1); }
      .pr-rd .pr-compete-name .pr-tag {
        display: inline-block; font-size: 10px; font-weight: 700;
        background: var(--bf-primary); color: #fff;
        padding: 1px 6px; border-radius: 3px; margin-left: 6px;
      }
      .pr-rd .pr-compete-bar-wrap {
        position: relative; height: 8px; background: #EEF1F5; border-radius: 4px;
      }
      .pr-rd .pr-compete-bar {
        position: absolute; height: 100%;
        background: linear-gradient(90deg, var(--bf-text-4) 0%, var(--bf-text-2) 100%);
        border-radius: 4px;
      }
      .pr-rd .pr-compete-row.pr-us .pr-compete-bar {
        background: linear-gradient(90deg, var(--bf-primary) 0%, #1A5FE0 100%);
      }
      .pr-rd .pr-compete-amount {
        font-size: 12.5px; font-weight: 700; color: var(--bf-text-2);
        text-align: right; white-space: nowrap;
      }
      .pr-rd .pr-compete-row.pr-us .pr-compete-amount { color: var(--bf-primary); }

      /* ROI */
      .pr-rd .pr-roi-flex {
        display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 20px;
      }
      .pr-rd .pr-roi-card {
        padding: 20px 22px; border-radius: 12px;
        background: var(--bf-bg-elev); border: 1px solid var(--bf-border);
      }
      .pr-rd .pr-roi-card.pr-benefit { border-color: #16A34A; background: #DCFCE7; }
      .pr-rd .pr-roi-card.pr-payback { border-color: #7C3AED; background: #F3E8FF; }
      .pr-rd .pr-roi-card .label {
        font-size: 10.5px; font-weight: 700;
        letter-spacing: 0.06em; text-transform: uppercase;
        color: var(--bf-text-3); margin-bottom: 8px;
      }
      .pr-rd .pr-roi-card .num {
        font-size: 28px; font-weight: 800; color: var(--bf-text-1); letter-spacing: -0.01em;
      }
      .pr-rd .pr-roi-card.pr-benefit .num { color: #16A34A; }
      .pr-rd .pr-roi-card.pr-payback .num { color: #7C3AED; }
      .pr-rd .pr-roi-card .num .unit { font-size: 14px; font-weight: 600; opacity: 0.7; margin-left: 4px; }
      .pr-rd .pr-roi-card .breakdown { font-size: 11.5px; color: var(--bf-text-3); margin-top: 10px; line-height: 1.7; }

      /* Reasoning */
      .pr-rd .pr-reasoning { display: flex; flex-direction: column; gap: 10px; }
      .pr-rd .pr-reason-row {
        display: flex; gap: 12px; align-items: flex-start;
        padding: 14px 16px; background: var(--bf-bg-elev);
        border: 1px solid var(--bf-border); border-radius: 10px;
      }
      .pr-rd .pr-reason-icon {
        flex-shrink: 0; width: 32px; height: 32px;
        background: var(--bf-primary-bg); color: var(--bf-primary);
        border-radius: 8px; display: flex;
        align-items: center; justify-content: center;
        font-size: 14px; font-weight: 700;
      }
      .pr-rd .pr-reason-body { flex: 1; }
      .pr-rd .pr-reason-title { font-size: 12.5px; font-weight: 700; color: var(--bf-text-1); margin-bottom: 4px; }
      .pr-rd .pr-reason-detail { font-size: 12px; color: var(--bf-text-3); line-height: 1.6; }
    `}</style>
  );
}
