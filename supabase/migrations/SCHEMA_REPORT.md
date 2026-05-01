# Build-Factory Schema Migration Report

SQLite + alembic から Supabase Postgres 17 への統合移行レポート。

## 出力ファイル

- `20260501220000_initial_schema.sql` — 全テーブル統合スキーマ
- `20260501220100_pgvector.sql` — pgvector / pg_trgm 拡張 + embedding カラム

## ソース範囲

alembic migration 9 ファイル (依存順):

```
d83319c25a4f → fa5e1c5eaac0 → c1a2b3d4e5f6
                                ↓
                         e9f0a1b2c3d4 → f1a2b3c4d5e6 → a7b8c9d0e1f2
                                                              ↓
                                                       b1c2d3e4f5a6
                                                          ↙        ↘
                                              c1d2e3f4g5h6    d7e8f9a0b1c2
```

加えて、**alembic 管理外**で SQL 直 CREATE されていたレガシー company-dashboard
テーブル群 (SQLite live schema より抽出) も統合した。

---

## 全テーブル一覧 (合計 54 テーブル)

### A. レガシー company-dashboard (alembic 管理外、20 テーブル)

| テーブル | 主要カラム | 用途 |
|---|---|---|
| `invoices` | invoice_no, client, total, status | 請求書管理 |
| `pipeline` | client, project, stage, amount | 営業パイプライン |
| `weekly_reviews` | week_label, sales_actual, top3_next | 週次レビュー |
| `monthly_reviews` | month_label, sales_actual, profit | 月次レビュー |
| `okr` | year, quarter, objective, kr1..3 | OKR |
| `outreach_log` | contact_date, channel, status | アウトリーチログ |
| `task_log` | task_date, task1..3 | 日次タスクログ |
| `contacts` | name, company, email, type | 連絡先 |
| `contracts` | contract_no, counterparty, status | 契約書 |
| `outsource_jobs` | job_no, vendor, status | 外注ジョブ |
| `brand_assets` | type, version, md_path | ブランド素材 |
| `seo_reports` | report_date, organic_sessions | SEO レポート |
| `kpi_records` | record_date, metric_name, metric_value | KPI 記録 |
| `network` | name, category, specialty | ネットワーク管理 |
| `expenses` | expense_date, amount, category | 経費 |
| `sns_posts` | post_date, platform, likes | SNS 投稿 |
| `pl_records` | month, revenue, profit | PL 記録 |
| `cf_forecasts` | forecast_month, balance_end | キャッシュフロー予測 |
| `cs_feedback` | client, nps_score | CS フィードバック |
| `tools_inventory` | tool_name, monthly_cost | ツール在庫 |
| `portfolio_items` | project_name, deliverables | ポートフォリオ |

### B. AI 社員システム (5 テーブル)

| テーブル | 用途 |
|---|---|
| `ai_employee_config` | AI 社員定義 + 階層 + 個性 + ナレッジスコープ |
| `skill_definitions` | スキル定義 (md_path 紐付け) |
| `ai_employee_skills` | 社員 ↔ スキル割当 |
| `task_schedule` | スケジュール定義 (cron) |
| `execution_log` | スキル実行ログ |
| `approval_queue` | 承認キュー |
| `communication_log` | 通信ログ (Slack/メール等) |

### C. ナレッジベース (2 テーブル)

| テーブル | 用途 |
|---|---|
| `knowledge_base` | ナレッジ本体 (+ embedding は pgvector で追加) |
| `knowledge_transfer_log` | 採用/退職時のナレッジ移動履歴 |

### D. プロジェクト / タスク / ワークフロー (5 テーブル)

| テーブル | 用途 |
|---|---|
| `projects` | プロジェクト |
| `tasks` | タスク (再帰: parent_task_id) |
| `task_questions` | タスク内 Q&A |
| `workflow_runs` | ワークフロー実行 |
| `workflow_steps` | ワークフローステップ |

### E. チャット / 会話 (5 テーブル)

| テーブル | 用途 |
|---|---|
| `threads` | チャットスレッド |
| `conversation_log` | 会話ログ (+ embedding は pgvector で追加) |
| `conversation_slots` | 会話スロット (slot tracking) |
| `slack_processed_messages` | Slack idempotency |
| `user_profile` | ユーザープロファイル (まさと等) |

### F. 出力アーティファクト (2 テーブル)

| テーブル | 用途 |
|---|---|
| `artifacts` | view 化された出力 (15 view 型) |
| `artifact_events` | アーティファクト変更履歴 (JSON Patch) |

### G. アカウント / ワークスペース階層 (5 テーブル)

| テーブル | 用途 |
|---|---|
| `accounts` | 課金単位 |
| `account_members` | アカウントメンバー |
| `workspaces` | プロジェクト単位 |
| `workspace_members` | ワークスペースメンバー |
| `workspace_invitations` | 招待トークン |

### H. 開発フロー (3 テーブル)

| テーブル | 用途 |
|---|---|
| `repos` | リポジトリ登録 |
| `pull_requests` | PR 追跡 |
| `reviews` | レビュー記録 |

### I. その他 (3 テーブル)

| テーブル | 用途 |
|---|---|
| `browser_task_queue` | ブラウザ自動化キュー |
| `checkpoints` | LangGraph state checkpoint (legacy 互換) |
| `writes` | LangGraph writes (legacy 互換) |
| `alembic_version` | alembic 互換 (移行期のみ) |

---

## SQLite ↔ Postgres 変換時の注意点

| SQLite | Postgres | 備考 |
|---|---|---|
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGSERIAL PRIMARY KEY` | 64bit 化 |
| `INTEGER` (0/1 フラグ) | `BOOLEAN` | `is_active`, `archived`, `task1_done` 等を変換 |
| `TEXT DEFAULT (datetime('now','localtime'))` | `TIMESTAMPTZ DEFAULT NOW()` | TZ-aware 化 |
| `TEXT DEFAULT (date('now','localtime'))` | `DATE DEFAULT CURRENT_DATE` | |
| `TEXT` (JSON 保存) | `JSONB` | `metadata`, `tags`, `aliases`, `params` 等 |
| `TEXT DEFAULT '[]'` (JSON 文字列) | `JSONB DEFAULT '[]'::jsonb` | キャスト必須 |
| `BLOB` (embedding) | `vector(1536)` | pgvector migration で追加 |
| `BLOB` (LangGraph) | `BYTEA` | checkpoint / writes |
| `CHECK (... IN (...))` | そのまま | Postgres 互換 |
| `INSERT OR IGNORE` | `INSERT ... ON CONFLICT DO NOTHING` | seed で使用 |
| `datetime('now','localtime')` 集約関数 | `NOW()` | 関数 SQL 違い |

### 挙動が変わる箇所

1. **タイムゾーン**: SQLite は `localtime` ベースで naive。Postgres は `TIMESTAMPTZ` で UTC 保存・クライアント TZ 表示。
   アプリ側のコードで `datetime.now()` を使っている箇所は要確認 (UTC で揃える)。
2. **boolean cast**: SQLite の `is_active = 1` 比較は Postgres では `is_active = TRUE`。SQL 直書きの WHERE 句は要修正。
3. **JSON クエリ**: `tags` 等が `TEXT` から `JSONB` になるため、文字列 LIKE 検索ではなく `tags @> '...'::jsonb` や `tags ? 'tag_name'` の演算子が必要。
4. **autoincrement の値域**: BIGSERIAL なので 32bit を超えるが、アプリの int 型変数は問題なし。
5. **CHECK 制約**: SQLite は緩く強制するが Postgres は厳密。テストデータが既存 ENUM 外を含む場合 INSERT 失敗。

---

## 暗黙 FK を明示化したケース (合計 16 件)

alembic では FK を `op.create_foreign_key` で作っていない箇所が多く、
SQLite には型レベルの FK 制約が存在しないものを Postgres で明示化した。

| Child テーブル.列 | Parent テーブル.列 | ON DELETE |
|---|---|---|
| `ai_employee_config.parent_id` | `ai_employee_config.id` | SET NULL |
| `ai_employee_config.inherited_to` | `ai_employee_config.id` | SET NULL |
| `ai_employee_config.account_id` | `accounts.id` | SET NULL |
| `knowledge_base.source_execution_id` | `execution_log.id` | SET NULL |
| `knowledge_base.assigned_employee_id` | `ai_employee_config.id` | SET NULL |
| `knowledge_base.account_id` | `accounts.id` | SET NULL |
| `knowledge_base.workspace_id` | `workspaces.id` | SET NULL |
| `knowledge_transfer_log.knowledge_id` | `knowledge_base.id` | CASCADE |
| `knowledge_transfer_log.from_employee` / `to_employee` | `ai_employee_config.id` | SET NULL |
| `approval_queue.source_execution_id` | `execution_log.id` | SET NULL |
| `approval_queue.workspace_id` | `workspaces.id` | SET NULL |
| `threads.with_employee` | `ai_employee_config.id` | SET NULL |
| `threads.workspace_id` | `workspaces.id` | SET NULL |
| `conversation_log.thread_id` | `threads.id` | CASCADE |
| `conversation_log.workspace_id` | `workspaces.id` | SET NULL |
| `conversation_slots.thread_id` | `threads.id` | CASCADE |
| `conversation_slots.workspace_id` | `workspaces.id` | SET NULL |
| `artifacts.thread_id` | `threads.id` | SET NULL |
| `artifacts.employee_id` | `ai_employee_config.id` | SET NULL |
| `artifacts.workspace_id` | `workspaces.id` | SET NULL |
| `artifact_events.artifact_id` | `artifacts.id` | CASCADE |
| `account_members.account_id` | `accounts.id` | CASCADE |
| `workspaces.account_id` | `accounts.id` | CASCADE |
| `workspace_members.workspace_id` | `workspaces.id` | CASCADE |
| `workspace_invitations.workspace_id` | `workspaces.id` | CASCADE |
| `repos.workspace_id` | `workspaces.id` | CASCADE |
| `pull_requests.repo_id` | `repos.id` | CASCADE |
| `reviews.pr_id` | `pull_requests.id` | CASCADE |
| `reviews.workspace_id` | `workspaces.id` | CASCADE |
| `browser_task_queue.requested_via_thread` | `threads.id` | SET NULL |

(細かく数えると ~30 だが、循環依存回避のため一部は `DO $$ ... ALTER ADD CONSTRAINT` ブロックで後付け)

---

## 翻訳の難所サマリ

1. **循環依存**: `ai_employee_config.account_id` ↔ `accounts.id` および workspace_id ↔ workspaces.id を参照する既存テーブルが多数。先に列を nullable で作り、テーブル定義後に `DO $$ ALTER TABLE ... ADD CONSTRAINT $$` で FK を追加する形にした。
2. **knowledge_base の累積 ALTER**: SQLite で migration 外に `ALTER TABLE ADD COLUMN` で `content`, `source`, `skill_tags`, `confidence`, `embedding` 等が継ぎ足されていた。これらを統合 CREATE で復元。
3. **alembic 外スキーマ**: `projects`, `tasks`, `threads`, `conversation_log`, `knowledge_base`, `skill_definitions`, `workflow_runs/steps`, `slack_processed_messages`, `task_questions` は alembic で CREATE されていない (起動時 SQL or 手動作成)。SQLite live schema から抽出して移植。
4. **TIMESTAMPTZ 化**: 全 `created_at` / `updated_at` 系を SQLite TEXT から TIMESTAMPTZ に変えた。アプリの datetime シリアライズが SQLite では文字列だったため、ORM 設定 (asyncpg / SQLAlchemy) 側の調整が必要。
5. **embedding の再生成**: SQLite BLOB から Postgres `vector(1536)` への直接コピー不可。pgvector migration で空のカラムを追加し、後続フェーズでアプリ側から再 embed する想定。

---

## TODO (後続フェーズ)

- [ ] **データ移行**: SQLite → Postgres のデータ ETL スクリプト作成 (pandas / psycopg / asyncpg)。embedding は再生成が必要。
- [ ] **boolean cast**: バックエンドコード内の `is_active = 1` のような SQL 直書き箇所を `= TRUE` または ORM 経由に置換。
- [ ] **JSONB クエリ書き換え**: `tags LIKE '%#共通%'` のような曖昧 JSON 検索を `tags @> '["#共通"]'::jsonb` に置換。
- [ ] **alembic → Supabase migration 移行**: 今後の schema 変更は `supabase/migrations/` 側で書く。alembic は段階的に廃止。
- [ ] **RLS 設計**: Supabase ネイティブの Row Level Security を `accounts` / `workspaces` 階層に基づき設計 (multi-tenant 化)。
- [ ] **LangGraph PostgresSaver 切替**: `checkpoints` / `writes` テーブルは AsyncSqliteSaver 互換の枠組み。Postgres 化に合わせ `AsyncPostgresSaver` を導入。
- [ ] **ivfflat → hnsw**: 件数が増えてきたら `vector_cosine_ops` のインデックスを `hnsw` に切り替え検討。
- [ ] **datetime TZ 統一**: アプリ全体で `datetime.now(UTC)` ベースに揃える。
- [ ] **alembic_version テーブル削除**: 完全移行後に DROP。
