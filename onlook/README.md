# Onlook 連携 (Build-Factory)

[Onlook](https://github.com/onlook-dev/onlook) はデザイン編集レイヤーとして採用（Apache 2.0）。

## Phase 1: ホスト版を別タブで開く（最速・推奨）

Build-Factory の Workspace Design タブから **「Onlook で開く」**ボタン押下で
新規タブで https://onlook.com を開く。

### メリット
- 自前 self-host コストゼロ（Supabase 不要・Bun ビルド不要）
- Onlook の最新機能をそのまま享受
- Apache 2.0 ライセンスのため切替・離脱は自由
- 完成 HTML / Next.js コードを Build-Factory に取り込める

### デメリット
- データが onlook.com に流れる（プロトタイプフェーズ向き）
- 商用案件で機密データを扱う際は Phase 2 へ

---

## Phase 2: Self-host（本格運用時）

Onlook は以下の構成で self-host できる:

```
- Bun ランタイム
- Supabase (Postgres + Auth + Storage)
- Next.js + React (apps/web/client)
- Backend (apps/backend)
- Docker Compose
```

### 公式 self-host 手順（要約）

```bash
# 1. クローン
git clone https://github.com/onlook-dev/onlook.git
cd onlook

# 2. 依存インストール（Bun 必須）
bun install

# 3. 環境変数セットアップ（packages/scripts/setup-env が対話的に作る）
bun setup:env

# 4. Supabase 起動 (Docker)
docker compose up -d  # supabase_network_onlook-web を立ち上げる

# 5. DB マイグレーション + seed
bun db:migrate
bun db:seed

# 6. アプリ起動
bun dev          # → http://localhost:3000
```

### Build-Factory 側のリバースプロキシ案

商用 self-host 段階で `onlook.engine-base.com` ドメイン or
Build-Factory 内 `/design` パスでプロキシする想定。

---

## 採用判断（2026-05-01 時点）

**Phase 1 = ホスト版を別タブで開くボタンのみ実装**:
- 自社初運用は onlook.com で問題ない
- 機密案件（受託）が始まる前に Phase 2 へ移行

**Phase 2 への移行トリガー**:
- 商用 SaaS 化に向けたデータ主権が必要になった時
- onlook.com のレート制限・コストが課題になった時
- カスタマイズが必要になった時

---

## 連携設計（Phase 1）

### Build-Factory → Onlook へ context 渡す方法

1. **Onlook プロジェクトを user が onlook.com で作成**
2. プロジェクト URL を Build-Factory に貼る（workspace.metadata.onlook_url）
3. Build-Factory が「[Onlook で開く]」ボタンに紐付ける
4. Build-Factory の Design Phase 出力（design-md / frontend-design 等）を
   ユーザーが Onlook へ手動でコピー（or 将来 OAuth/API 連携）

### Onlook → Build-Factory へ完成物を取り込む方法

1. Onlook で完成したら Next.js プロジェクトを GitHub にエクスポート
2. Build-Factory に repo URL を登録
3. Claude Code が `bf_get_spec` でレポジトリ参照しながら実装

---

## ライセンス

Apache 2.0 — SaaS 商用 OK・改変 OK・再配布 OK
