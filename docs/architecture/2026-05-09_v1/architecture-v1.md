# Build-Factory v2.1 アーキテクチャ設計書 v1.0

**プロジェクト**: Build-Factory（SaaS 型開発工場 OS）
**バージョン**: v1.0
**作成日**: 2026-05-09
**前提**: 要件定義 v1.0（`docs/requirements/2026-05-09_v1/`）

---

## 1. 全体方針

### アーキパターン
**モジュラーモノリス**（FastAPI + Next.js）

### 選定理由
- 1 人開発（dogfooding）+ Claude Code 実装エンジンで運用負荷を最小化
- swarm 50 並列セッション + WebSocket 状態同期は単一プロセスが最適
- Supabase が DB / Auth / Realtime / Storage を一手に担うため Backend を軽量化
- ドメイン境界（13 モジュール）を明確化することで Phase 2/3 で必要箇所のみマイクロサービス化可能

### 採用しなかった選択肢
- **モノリス（無構造）**：Phase 1.5 以降に分離困難
- **マイクロサービス**：1 人運用では over-engineering
- **サーバレス全面**：subprocess + 長時間 swarm + WebSocket に不向き

---

## 2. システム構成図

```
ブラウザ (Chrome / Edge / Safari / Firefox)
        ↓ HTTPS / wss://
Vercel CDN（Frontend ホスト・CDN・DDoS）
        ↓
[Next.js 15 SSR/RSC + Server Actions]
        ↓ API call / WebSocket
[FastAPI（モジュラーモノリス・13 ドメイン）+ Worker（asyncio）]
        ↓                                   ↓
Supabase Cloud (Postgres+RLS+         Worker Pool
Auth+Realtime+Storage+pgsodium        ・claude-agent-sdk subprocess 管理
+pgvector+pg_trgm+pg_cron)            ・1 案件 5 並列 / 全体 50 並列
                                       ・circuit breaker
                                       ・WebSocket でログ stream
                                       ↓
                                       Claude Code processes
                                       (各ユーザの Pro/Max OAuth)
                                       ↓
                                       Anthropic API
        ↓
外部連携：Slack（Bolt SDK）/ GitHub（gh CLI + MCP）
        / Obsidian（Storage MD upload P1 → Headless Sync P1.5）
        / LiteLLM self-host（Claude / OpenAI / Gemini）
        / Langfuse self-host（観測）
        / Sentry（エラー）/ Better Stack（uptime）
```

---

## 3. 技術スタック一覧

### Frontend
| 項目 | 採用 | 理由 |
|---|---|---|
| Framework | Next.js 15 App Router | 既存・SSR/RSC + Server Actions |
| UI | shadcn/ui + Tailwind CSS 4 | 既存 |
| State | Zustand + TanStack Query | 既存・SSR 対応 |
| Graph 可視化 | React Flow | DAG / 組織図 / 画面遷移 |
| Chart | Recharts | コスト ダッシュボード |
| HTML Editor | GrapesJS Studio SDK（P1.5）| 確定 |

### Backend
| 項目 | 採用 | 理由 |
|---|---|---|
| Framework | FastAPI（モジュラーモノリス）| 既存・asyncio・OpenAPI |
| Worker | asyncio + Semaphore + Queue（P1）→ Celery + Redis（P2 必要時） | dogfood 段階はシンプル |
| Subprocess 管理 | **claude-agent-sdk**（Python） | 公式 SDK・Docker friendly・Langfuse 統合 |
| MCP Server | Anthropic MCP Python SDK + FastAPI | stdio + HTTP transport |
| ORM | SQLAlchemy 2.0 async + Pydantic + Supabase Python SDK（軽量クエリ用）| 既存 + Supabase 統合 |
| Lint / Format | ruff（既存） | 高速 |
| Type Check | pyright（既存） | |
| Package | uv（既存） | 高速 |

### DB / 認証 / Storage
| 項目 | 採用 |
|---|---|
| DB | Supabase Postgres（managed → P3 で self-host 可能性） |
| Auth | Supabase Auth（JWT + 2FA + OAuth） |
| Realtime | Supabase Realtime + 自前 WebSocket（FastAPI）の 2 系統ハイブリッド |
| Storage | Supabase Storage（S3 互換） |
| Migration | **Supabase CLI**（既存 alembic は archive） |
| Vector | pgvector |
| FTS | Postgres FTS + pg_trgm |
| 暗号化 | pgsodium |
| 定期実行 | pg_cron |

### AI / LLM
| 項目 | 採用 |
|---|---|
| AI 社員 | BMAD 思想流用 + 自前統合 + Anthropic Agent Teams + 既存 96 スキル ハイブリッド |
| LLM 抽象化 | **LiteLLM**（self-host・Langfuse 統合・OSS） |
| 実装層 LLM | 各ユーザの Claude Pro/Max（OAuth 経由） |
| チャット層 LLM | 自社 API（Claude / OpenAI / Gemini）+ BYOK の 2 系統 |
| 観測 | Langfuse self-host（MIT） |
| Long-term Memory | Mem0（既存） |

### インフラ（Phase 1 = ¥0 構成）
| 項目 | 採用 |
|---|---|
| Frontend ホスト | **Vercel Hobby**（無料） |
| Backend / Worker / Langfuse | **Oracle Cloud Free Tier**（永久無料 4 vCPU + 24GB RAM）or 自宅 PC + Cloudflare Tunnel |
| Supabase | **Free**（500MB DB / 1GB Storage / 50K MAU） |
| Sentry | 無料（5K events/月） |
| Uptime | Better Stack 無料（10 monitors） |
| CI/CD | GitHub Actions 無料（2000 分/月 public） |
| DNS | Vercel DNS or Cloudflare DNS（無料） |

---

## 4. DB 設計方針（要点）

### 設計原則
- **PK**: UUID v7（時系列ソート可・衝突なし）
- **削除**: ソフトデリート（`deleted_at TIMESTAMPTZ`）
- **マルチテナント**: `account_id` / `workspace_id` 全テーブル必須 + RLS で auto enforce
- **命名**: snake_case / 複数形テーブル / FK は `<table>_id`
- **タイムスタンプ**: `created_at` / `updated_at`（trigger 自動更新）
- **作成・更新者**: `created_by` / `updated_by` UUID
- **JSONB**: custom_permissions / project_meta / capabilities
- **enum**: Postgres ENUM 型 + check constraint
- **時系列**: BRIN index + pg_partman 月次 partition（P2）

### 主要テーブル（42）
- 認証・テナント 6（accounts / account_members / workspaces / workspace_members / workspace_invitations / users）
- AI・スキル 5（ai_employees / skills / skill_executions / user_knowledge_namespace / user_interaction_log）
- プロジェクト管理 6（phases / phase_gates / tasks / task_dependencies / acceptance_criteria / constitutions）
- 仕様・モック 5（artifacts / artifact_versions / screens / components / screen_components）
- 実装・レビュー 7（sessions / session_logs / session_artifacts / prs / pr_reviews / red_lines / red_line_violations）
- 連携・運用 11（llm_providers / api_keys / slack_webhooks / github_repos / obsidian_vaults / notifications / cost_logs / token_limits / audit_logs / backups / user_settings）
- 補助 2（workspace_settings / schema_versions）

### インデックス
- RLS 対象（workspace_id / account_id）全テーブル必須・partial index（`WHERE deleted_at IS NULL`）
- 全 FK にインデックス
- GIN（tsv / tags / skill_ids[]）
- ivfflat（embedding vector_cosine_ops）
- BRIN（時系列：audit_logs / session_logs / cost_logs）
- 複合（workspace_id + status + 並び）

### マイグレーション
- **Supabase CLI 統一**（`supabase migration new ...` + `supabase db push`）
- 既存 alembic は archive
- 本番は expand-and-contract で zero-downtime
- seed は `supabase/seed.sql`（`BF_ENV=development` ガード）

### Constitution + 赤線リストの階層管理
```
constitutions（不変原則）
  └─ red_lines（検出ルール・FK constitution_id）
       └─ red_line_violations（抵触ログ）
```

### 個人クローン opt-in（M-22）
- `users.user_clone_opt_in DEFAULT FALSE`
- `user_interaction_log` への INSERT は trigger で opt_in = TRUE 時のみ許可
- いつでも OFF + 全ログ削除可

---

## 5. インフラ・デプロイ構成

### 環境
| 環境 | ホスティング | 立ち上げ |
|---|---|---|
| development | Docker Compose ローカル + Supabase Cloud | Phase 1 開始 |
| staging | Production 同等構成（別 Supabase プロジェクト） | Phase 1.5 |
| production | Vercel + Oracle Free Tier or VPS + Supabase Cloud | Phase 1 中盤 |

### CI/CD（GitHub Actions）
- `ci.yml`: lint / typecheck / test
- `license-check.yml`: AGPL 検出
- `deploy-staging.yml`: main push 自動
- `deploy-prod.yml`: tag push（手動承認）
- `nightly-backup.yml`: 日次バックアップ + 検証

### ブランチ戦略
- `main`（production）/ `staging`（P1.5+）/ `feature/*`（PR 起点）/ `claude/*`（Claude Code 自動）

### docker-compose（dev）
- next（3001）/ backend（8001）/ worker / langfuse（3100）+ langfuse-db / Supabase は外部接続

---

## 6. セキュリティ方針

| 領域 | 対策 |
|---|---|
| 認証 | Supabase Auth JWT + 2FA + OAuth（Anthropic / Slack / GitHub） |
| 認可 | RLS（必須）+ custom_permissions JSONB / OpenFGA（P2 補完） |
| 通信 | HTTPS + wss:// + CORS ホワイトリスト + CSP + CSRF（SameSite=Lax）|
| データ at rest | Supabase Cloud disk encryption + pgsodium で API キー / トークン暗号化 |
| クライアント側 | JWT は httpOnly + Secure + SameSite cookie |
| ログマスキング | structlog processor で API キー / トークン / メールを自動マスク |
| 個人クローン | opt-in 必須 / namespace 完全分離 / いつでも OFF + 全削除可 |
| レートリミット | API 1000/5min/user / Cloudflare 10000/5min/IP / LLM コスト workspace 上限 |
| 秘匿情報 | Coolify Secrets / GitHub Actions Secrets / .env / pre-commit gitleaks |
| 赤線 5 項目 + Constitution | ミドルウェア層で全アクション前にチェック → 該当時 block + 監査ログ |

### 監視・ログ
- LLM: Langfuse self-host（cost / tokens / latency / eval）
- アプリエラー: Sentry（無料 5K events/月）
- 構造化ログ: structlog（Python）+ pino（Node.js）JSON 形式
- 死活: Better Stack（無料 10 monitors / 1 分間隔）
- 監査ログ: DB 内 7 年保持（pg_partman 月次 partition）

### バックアップ
- DB 日次（Supabase 自動 + 手動 export 二重化）/ 90 日
- Storage 週次 / 90 日
- Obsidian リアルタイム（P1.5 双方向時）/ 永続
- 監査ログ DB 内 7 年

---

## 7. 設計トレードオフ一覧

| 採用 | 犠牲 | 受容理由 |
|---|---|---|
| モジュラーモノリス | 1 サービス障害で全停止 | 1 人運用で許容・冗長化は P3 |
| Supabase 採用 | 中程度のベンダーロックイン | 標準 SQL + RLS portable で緩和 / 統合性のメリット大 |
| LiteLLM self-host | VPS 運用負荷 | Langfuse 統合 + OSS / コスト最小 |
| 自前 WebSocket（swarm） | 開発コスト + sticky session 必要 | swarm の 100ms 要件は Supabase Realtime 不向き |
| Vercel + Oracle Free Tier | 環境分散 | 初期コスト ¥0 / dogfood に十分 |
| pgsodium | Supabase Vault GA で再検討必要 | 現時点での標準 + Postgres ネイティブ |
| GitHub Actions | GitHub 依存 | M-13 GitHub 連携と統合性高 |
| 個人クローン opt-in OFF デフォルト | 学習データ集まりにくい | プライバシー保守 / 信頼獲得 |
| Supabase CLI（alembic 廃止） | 既存資産の一部破棄 | DB 統一性 / RLS 管理性 |

---

## 関連ファイル

- `er-diagram-v1.html` — ER 図 + テーブル定義 + インデックス設計
- `architecture-v1.html` — 同 HTML 版（Mermaid 図解付き）
- `architecture_design.json` — 後続スキル引き継ぎ
- `architecture_decision_log.json` — 判断ログ + リサーチ
- `../../requirements/2026-05-09_v1/` — 要件定義 v1.0
- `../../hearing/2026-05-09_re-hearing/` — ヒアリング v2.1

## 次のスキル

```
tech-stack → functional-breakdown → feature-decomposition
  → task-decomposition → distributed-dev (Claude Code 実装開始)
```
