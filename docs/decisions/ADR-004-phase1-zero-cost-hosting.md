# ADR-004: Phase 1 ¥0 ホスティング

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: 高本まさと

## Context

Phase 1 (内製 dogfood) は以下の条件:

- **収益はゼロ** (内製運用のみ)
- **masato 1 人で運用**
- **本番品質は不要だが、本番運用に近い形で検証したい** (Phase 2 SaaS 化に備え)
- **Claude API コストは別途** (¥300/月想定)

候補:
- **AWS** = 学習コスト + ¥10,000+/月 → 過剰
- **Cloudflare Workers** = 関数限定、FastAPI 動かない → 不採用
- **Render / Railway** = Free tier 短期、コールドスタート → 不採用
- **Vercel + Oracle Cloud Free** = ホスト分離、いずれも永久無料 → 採用候補
- **VPS 自前** = 運用コスト大 → 不採用

## Decision

**Vercel Hobby + Oracle Cloud Free Tier + Supabase Free** の 3 段構成。

### Frontend: Vercel Hobby
- 無料 (個人 / 商用利用に注意 → Phase 2 で Pro 切替)
- 自動 HTTPS / プレビュー環境 / Edge CDN
- Next.js 15 との相性良し

### Backend: Oracle Cloud Free Tier
- **永久無料**: ARM Ampere 4 vCPU + 24 GB RAM
- + 200 GB ブロックストレージ
- + 10 TB 月次転送
- → FastAPI を Docker で動かすには十分

### DB / Auth / Storage: Supabase Free
- 500 MB DB / 5 GB Storage / 50,000 月次 MAU
- pgvector / RLS / Auth (GoTrue) 全部含む
- Phase 2 で Pro ($25/月) に切替

### 接続: Cloudflare Tunnel (無料)
- Vercel から Oracle Cloud へ HTTP 接続
- 静的 IP 不要 / 双方向 HTTPS

### 観測: Sentry / Better Stack / GitHub Actions
- それぞれ Free tier (個人)

### コスト
- ホスティング: **¥0/月**
- ドメイン: ¥125/月 (Cloudflare Registrar)
- Claude API: 別途 ¥10,000-30,000/月 (使用量による)
- **合計: ¥125/月 + Claude API**

## Consequences

### 得られるもの
- ✅ Phase 1 のホスティングコスト実質ゼロ
- ✅ 本番運用に近い形 (HTTPS / CDN / DB / Auth) で検証可能
- ✅ Phase 2 SaaS 化時、Vercel Pro + Supabase Pro + Oracle 課金プランへスムーズ移行

### 諦めるもの
- ❌ Vercel Hobby は商用利用に制約 → Phase 2 で Pro 必須
- ❌ Oracle Cloud Free Tier は突然終了リスク (公式は永久無料宣言だが信用度は中)
  - → バックアップ計画: Hetzner Cloud (€4/月) に移行可能な構成にしておく
- ❌ Cloudflare Tunnel は CF アカウント依存 → ロックインリスク中

### 検討した代替案
- **Vercel + Render** = Render Free は cold start 30s+ → UX 悪化、不採用
- **AWS Free Tier** = 12 ヶ月限定、複雑 → 不採用
- **Self-hosted (自宅サーバ)** = 運用コスト・電気代・停電リスク → 不採用

### 関連
- 影響を受けるタスク: T-S0-01 (環境セットアップ) / T-021-04 (deploy pipeline)
