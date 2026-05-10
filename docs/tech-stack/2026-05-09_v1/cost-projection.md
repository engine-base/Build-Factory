# Build-Factory コスト試算（Phase 別・2026-05-09）

## 為替レート（試算用）
1 USD = 150 円（2026-05 概算）

---

## Phase 1（dogfood・ユーザ 1 名・¥0 構成）

| 項目 | 月額（USD）| 月額（円）|
|---|---|---|
| Vercel Hobby | $0 | ¥0 |
| Oracle Cloud Free Tier（ARM 4 vCPU + 24GB × 2）| $0 | ¥0 |
| Supabase Free（500MB DB / 1GB Storage / 50K MAU）| $0 | ¥0 |
| Sentry Free（5K events/mo）| $0 | ¥0 |
| Better Stack Free（10 monitors）| $0 | ¥0 |
| GitHub Actions Free（2000 min/mo public）| $0 | ¥0 |
| Cloudflare DNS Free | $0 | ¥0 |
| ドメイン（.com 年 ¥1,500）| - | ¥125 |
| **Build-Factory 運用コスト** | **$0** | **¥125/月** |
| 高本まさと Claude Max（個人負担）| $200 | ¥30,000 |
| **合計（個人プラン込）** | **$200** | **¥30,125/月** |

→ **実質運用コスト = ¥125/月**（ドメインのみ）

---

## Phase 1.5（社内拡張・2-3 人想定）

| 項目 | 月額（USD）| 月額（円）|
|---|---|---|
| Vercel Pro（個人 use → 商用へ移行）| $20 | ¥3,000 |
| Supabase Pro（8GB DB / 100GB egress / 100K MAU）| $25 | ¥3,750 |
| Sentry Team（50K events）| $26 | ¥3,900 |
| Better Stack Pro（60 monitors）| $25 | ¥3,750 |
| Coolify on $20-50 VPS | $30（中央値）| ¥4,500 |
| GitHub Actions（必要時 minute 追加）| $5（任意）| ¥750 |
| ドメイン | - | ¥125 |
| **小計** | **$131** | **¥19,775/月** |
| + 各メンバー Claude Pro/Max（各自負担）| $20-200/人 | ¥3,000-30,000/人 |

→ **¥17,000-21,000/月 + 各自プラン**

---

## Phase 2（β試用・5-10 顧客）

| 項目 | 月額（USD）| 月額（円）|
|---|---|---|
| Phase 1.5 同等 | $131 | ¥19,775 |
| Coolify VPS スケール（複数台）| +$30 | ¥4,500 |
| Langfuse 専用 VPS（必要時）| $30 | ¥4,500 |
| OpenFGA self-host（C-1）| $0（同 VPS）| ¥0 |
| Apache AGE（C-12 Knowledge Graph・Postgres 拡張）| $0 | ¥0 |
| Stripe（C-6・売上の 3.6%）| - | 売上次第 |
| **小計** | **$191** | **¥28,775/月** |
| + 顧客課金（収入で相殺可能）| - | - |

→ **¥30,000-50,000/月**

---

## Phase 3（商用 SaaS・MAU 100 想定）

### 想定顧客プラン（仮）
- Free：MAU 制限あり
- Pro：$30/mo → ¥4,500/mo per workspace
- Team：$100/mo → ¥15,000/mo per workspace

### コスト
| 項目 | 月額（USD）| 月額（円）|
|---|---|---|
| Vercel Pro チーム | $40 | ¥6,000 |
| Supabase Team（10 orgs）| $599 | ¥89,850 |
| Sentry Business | $80 | ¥12,000 |
| Better Stack Business | $50 | ¥7,500 |
| Cloudflare Pro | $20 | ¥3,000 |
| Coolify VPS（本格運用）| $100 | ¥15,000 |
| OpenFGA Cloud（C-1・必要時）| $50 | ¥7,500 |
| Langfuse 専用 VPS | $50 | ¥7,500 |
| ドメイン + DNS + SSL | - | ¥1,000 |
| **インフラ小計** | **$989** | **¥148,350/月** |
| 法務 / 会計 / SaaS 運用 | - | ¥30,000-100,000 |
| **合計** | - | **¥180,000-250,000/月** |

### 採算ライン（仮）
- Pro $30/mo × 50 顧客 = $1,500/mo（¥225,000）→ コスト相殺
- Pro $30/mo × 100 顧客 = $3,000/mo（¥450,000）→ 利益開始
- ARR ¥1,200-3,600 万で採算合う

---

## 累積試算（年次）

| Phase | 開始月 | 月額 | 期間 | 年間コスト |
|---|---|---|---|---|
| Phase 1（dogfood）| Month 0 | ¥125 | 2 ヶ月 | ¥250 |
| Phase 1.5（社内拡張）| Month 2 | ¥20,000 | 3 ヶ月 | ¥60,000 |
| Phase 2（β試用）| Month 5 | ¥40,000 | 4 ヶ月 | ¥160,000 |
| Phase 3（商用 SaaS）| Month 9 | ¥200,000 | 3 ヶ月 | ¥600,000 |
| **Year 1 累計** | | | | **¥820,250** |

→ **個人 Claude Max は別**（年 ¥360,000・個人負担で ENGINE BASE 経費にならない場合）

---

## 削減ポイント（さらに ¥0 を粘る場合）

| 項目 | 削減方法 |
|---|---|
| Sentry → 自前 logging | structlog のみで運用（Phase 1 は OK）|
| Better Stack → cron + curl | 簡易 health check（精度低下）|
| Vercel Pro → Coolify on VPS で Frontend も hosting | ただし Next.js 最適化が劣化 |
| Supabase Pro → self-host | サーバ管理負荷増 |

→ **Phase 1.5 は最低 ¥10,000/月**まで削れる（Sentry / Better Stack なし）

---

## 改訂履歴
- v1.0（2026-05-09）：初版・Phase 1-3 全体試算
