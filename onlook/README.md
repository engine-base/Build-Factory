# Onlook self-host (Build-Factory 用)

[Onlook](https://github.com/onlook-dev/onlook) を self-host する設定。
Apache 2.0 ライセンス・OSS 素のまま使う方針（Phase 1）。

## 起動

```bash
# Build-Factory ルートで .env が整備されている前提
cd onlook
docker compose up -d
```

→ http://localhost:3010 で Onlook が立ち上がる

## Build-Factory との連携

### 案 1: 別タブで開く（最速）

Build-Factory の Workspace Design タブから「[ Onlook で開く ]」ボタンで
新規タブで http://localhost:3010 を開く。

### 案 2: リバースプロキシで `/design` パス（1 アプリ感）

Build-Factory frontend (3001) または Caddy / nginx で `/design/*` を
`http://localhost:3010` に転送する設定を追加。

例（Caddy）:
```
localhost:3001 {
  handle_path /design/* {
    reverse_proxy localhost:3010
  }
  handle {
    reverse_proxy localhost:3000
  }
}
```

## Build-Factory 資産の流用

`docker-compose.yml` で以下が Onlook 内にマウントされる:
- `data/design-systems/` → `/app/imported-design-systems/`
- `data/skills/` → `/app/imported-skills/`

Onlook 起動時に「ブランド指針」「UI パターン」として参照可能。

## 環境変数

`.env` に以下を追加（root の `.env` を読み込み）:
```
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
ONLOOK_NEXTAUTH_SECRET=任意のランダム文字列
```

## 停止

```bash
docker compose down
```

データを残したまま停止。完全削除する場合は:
```bash
docker compose down -v
```
