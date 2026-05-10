# Supabase 全移行 + Onlook 統合 — 完了レポート

作成日: 2026-05-01
ブランチ: `feature/dev-specialization`

## 完了したフェーズ

### ✅ Phase A: Supabase ローカル + スキーマ + データ移行

- `supabase init` + `supabase start` で Postgres 17 + Auth + Storage + Studio 起動
- alembic migration 9 個分 + 既存 SQLite live schema を統合した Postgres SQL を生成
  - `supabase/migrations/20260501220000_initial_schema.sql` (54 テーブル)
  - `supabase/migrations/20260501220100_pgvector.sql` (pgvector + pg_trgm)
- SQLite → Postgres データ移行
  - `backend/scripts/migrate_sqlite_to_postgres.py`
  - 178 行 / 9 テーブル移行
  - boolean / jsonb / CSV→array の自動正規化対応

### ✅ Phase B: backend を psycopg async に移行

- `backend/db/async_db.py` — aiosqlite 互換 API を psycopg で実装したアダプタ
  - `?` → `%s` プレースホルダ変換
  - `is_active = 1` → `is_active = TRUE` 自動変換
  - `datetime('now')` → `NOW()` 変換
  - `execute_fetchone` / `execute_fetchall` 互換メソッド
- 41 ファイルの import を一括置換（aiosqlite → async_db アダプタ）
- 25 箇所の INSERT 文に `RETURNING id` を追加（lastrowid 廃止対応）
- backend FastAPI 起動 + `/api/accounts/1` で Postgres から取得確認

### ✅ Phase F: Obsidian + pgvector 知識スコープ

- knowledge_base スキーマ拡張: `visibility / owner_user_id / scope_path`
  - `supabase/migrations/20260501220200_knowledge_scope.sql`
- visibility: `private | member_shared | account_shared | ai_only | public`
- Obsidian vault ディレクトリ構造設計
  - `backend/scripts/init_obsidian_vault.py`
  - 階層: `accounts/{slug}/{shared|members/{user}|ai-personas/{persona}}/...`
  - workspaces にも同じ構造で AI 専用ナレッジ領域を用意
  - 7 dev AI personas (nana-pm/ken-architect/haru-engineer/rin-reviewer/saki-qa/taku-devops/mio-docs)
- 同期サービス: `backend/services/obsidian_vault_sync.py`
  - `sync` / `watch` モード
  - SHA256 で差分検知、INSERT/UPDATE/DELETE
  - パスから account_id / workspace_id / owner_user_id / assigned_employee_id 自動解決
  - OPENAI_API_KEY があれば embedding 生成 (pgvector 行に保存)
- スコープ付き検索 API: `backend/routers/knowledge_search.py`
  - `/api/knowledge/search?q=...&account_id=1&as_user=masato&as_persona=rin-reviewer`
  - cosine 類似度 + trigram 類似度の合成スコア
  - 動作確認: 3 種の visibility (private/ai_only/account_shared) 全て正常検索可能

### ✅ Phase E: Onlook canvas 抽出

- 抽出元: `https://github.com/onlook-dev/onlook` (Apache-2.0)
- 抽出方式: コンポーネント抽出（フォーク管理ではなく、Build-Factory 内の通常コードとして組み込み）
- 配置先:
  - `frontend/src/lib/onlook/` (137 ファイル) — penpal/constants/models/utility/parser/ui shim
  - `frontend/src/components/design-canvas/` (49 ファイル) — canvas + editor store
- 削除した Onlook 依存:
  - `@onlook/db, code-provider, git, github, stripe`
  - `@supabase/ssr, @trpc/*, @xterm/*, @zenfs/*`
- スタブ化した API:
  - `api.userCanvas.update`, `api.frame.{create,update,delete}` (REST 配線は次フェーズ)
  - 20 個の EditorEngine マネージャ (action/ast/branch/chat 等) を Proxy no-op で代替
- 帰属表示: `frontend/src/lib/onlook/NOTICE.md` (Apache-2.0)
- TypeScript エラー: 14 件残存（next dev で動作するレベル、本番ビルド前に解消必要）
- design ページ: `frontend/src/app/workspaces/[id]/design/page.tsx`
  - `EditorEngineProvider` + `Canvas` を dynamic import で SSR 回避
  - HTTP 200 でレンダリング確認済

### ✅ Phase C/D/G: Auth + Storage + RLS skeleton

- `backend/services/supabase_client.py` — Supabase REST クライアント
  - JWT 検証 (HS256)
  - Storage upload / signed URL
- `backend/services/auth_middleware.py` — FastAPI 用 Auth ミドルウェア
  - `Depends(get_current_user)` で JWT claims 取得
  - `BUILD_FACTORY_DEV_BYPASS_AUTH=1` で dummy user (masato) として動作（ローカル開発用）
- RLS skeleton: `supabase/migrations/20260501220300_rls_skeleton.sql`
  - knowledge_base / accounts / workspaces に最小限のポリシー適用
  - `auth.jwt() ->> 'sub'` と `account_members.user_id` の結合で制御
  - service_role は全アクセス可（backend は service key 経由）

## 実行環境

### ローカル起動手順

```bash
# 1. Supabase ローカルスタック起動
cd /Users/masato0420/Documents/Build-Factory
supabase start

# 2. backend (Postgres 接続)
cd backend
source .venv/bin/activate
DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:54322/postgres" \
  uvicorn main:app --port 8001

# 3. frontend
cd frontend
/opt/homebrew/bin/node ./node_modules/next/dist/bin/next dev --turbo --port 3001

# 4. Obsidian 同期 (任意)
cd backend
python -m services.obsidian_vault_sync watch
```

### 接続情報

| サービス | URL |
|---|---|
| frontend | http://localhost:3001 |
| backend API | http://localhost:8001 |
| Supabase API | http://127.0.0.1:54321 |
| Supabase Studio | http://127.0.0.1:54323 |
| Postgres | postgresql://postgres:postgres@127.0.0.1:54322/postgres |
| Mailpit (test SMTP) | http://127.0.0.1:54324 |

### 環境変数（.env or .env.local）

```bash
# 必須
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_ANON_KEY=REPLACE_WITH_SUPABASE_ANON_KEY              # `supabase start` で表示された publishable key
SUPABASE_SERVICE_KEY=REPLACE_WITH_SUPABASE_SERVICE_KEY        # `supabase start` で表示された secret key
SUPABASE_JWT_SECRET=super-secret-jwt-token-with-at-least-32-characters-long

# 開発時のみ (auth bypass)
BUILD_FACTORY_DEV_BYPASS_AUTH=1

# 任意 (embedding 自動生成)
OPENAI_API_KEY=sk-...
```

## 次フェーズで対処すべき TODO

### 優先度: 高

1. **Onlook canvas の REST 配線**
   - `frame/manager.ts` の `api.frame.{create,update,delete}` を Build-Factory backend (`/api/workspaces/:id/design/frames`) に接続
   - `canvas store` の `api.userCanvas.update` も同様
2. **TypeScript エラー 14 件の解消**
   - 主に `unknown → DomElement` の型ガード補強
   - `view.tsx` の penpal 型ブリッジ修正
3. **Auth UI 実装**
   - frontend に `@supabase/supabase-js` 導入
   - サインイン/サインアウト UI
   - account_members.user_id を Supabase Auth user_id (UUID) に upgrade

### 優先度: 中

4. **EditorEngine マネージャの本実装**
   - 現在 20 個の Proxy no-op スタブ
   - chat / action / history / style / move / copy あたりが優先
5. **Storage 統合**
   - artifacts (mockup HTML 等) を Supabase Storage に保存
   - `bf_attach_artifact` MCP ツールから upload_file() を呼ぶ
6. **RLS の全テーブル展開**
   - 現在は accounts / workspaces / knowledge_base のみ
   - artifacts / threads / conversation_log / tasks 等にも account/workspace スコープで適用

### 優先度: 低

7. **mobx → zustand 移行** (Onlook canvas)
8. **Obsidian → embedding バッチ生成**（OPENAI_API_KEY 設定時の初回フル同期で時間が掛かる）
9. **本番デプロイ手順整備**（Supabase Cloud / Vercel）
10. **i18n** (next-intl の peer 衝突解決)

## 統計

| 指標 | 数 |
|---|---|
| 移行スキーマ | 54 テーブル |
| 移行データ | 178 行 |
| psycopg 移行 backend ファイル | 41 |
| 追加した RETURNING 句 | 25 |
| Obsidian vault ディレクトリ | accounts × shared/members/ai-personas/workspaces |
| 抽出した Onlook ファイル | 186 (lib 137 + canvas 49) |
| スタブ化した Onlook 依存 | 11 パッケージ |
| 残存 TypeScript エラー | 14 |
| 新規 backend サービス | 4 (async_db, obsidian_vault_sync, supabase_client, auth_middleware) |
| 新規 router | 1 (knowledge_search) |
| 新規 migration | 4 ファイル |

## アーキテクチャ概観

```
┌─────────────────────────────────────────────────────────────┐
│                    Build-Factory                            │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │  frontend    │  │   backend    │  │  Obsidian Vault  │ │
│  │  (Next.js)   │  │  (FastAPI)   │  │  (filesystem)    │ │
│  │              │  │              │  │                  │ │
│  │  /workspaces │  │  41 services │  │  accounts/       │ │
│  │   /[id]/     │  │  routers/api │  │  workspaces/     │ │
│  │   design ◄───┤◄─┤              │  │   ai-personas/   │ │
│  │  (Onlook)    │  │  async_db    │  │   members/       │ │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬────────┘ │
│         │                 │                    │ sync     │
│         │                 │                    ▼          │
│         │       ┌─────────▼──────────────────────────┐    │
│         │       │      Supabase Local Stack          │    │
│         │       │                                    │    │
│         └──────►│  Postgres 17 + pgvector + pg_trgm │    │
│                 │  Auth (GoTrue)                     │    │
│                 │  Storage (S3 互換)                 │    │
│                 │  Realtime / Studio / Mailpit       │    │
│                 └────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```
