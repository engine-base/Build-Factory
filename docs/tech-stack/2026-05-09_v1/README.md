# Build-Factory v2.1 → v1.0 tech-stack（2026-05-09）

このフォルダは **tech-stack スキルの最終出力**を保管します。要件定義 v1.0 + アーキ v1.0 + functional-breakdown v1.0 を入力として、OSS / SaaS の最終確定 + ライセンス + コスト + Phase 別積算を行いました。

## ファイル一覧

| ファイル | 役割 |
|---|---|
| `selected-stack.json` | 後続スキル（feature-decomposition / task-decomposition）入力用構造化データ |
| `tech-stack-v1.html` | ライセンス + コスト早見表（クライアント提示用） |
| `tech-stack-v1.md` | Markdown サマリー |
| `cost-projection.md` | Phase 別コスト試算（¥0 → 商用 SaaS） |

## 主要決定（一覧）

| 領域 | 採用 |
|---|---|
| 全体 Orchestrator | **LangGraph**（MIT） |
| Multi-agent SDK | **不採用**（LangGraph で代替）|
| LLM Gateway | **LiteLLM**（MIT・self-host）|
| Plan/Gen/Eval | Anthropic Agent Teams（Claude Code 内部のみ）|
| 実装 CLI | **Claude Code + claude-agent-sdk**（MIT） |
| 実装エンジン切替 | **C-13 Phase 2**（Codex CLI / Gemini CLI 等）|
| 参考 OSS | **Codex CLI**（Apache 2.0・コードロジック参考のみ・依存なし） |
| HTML Editor（P1.5） | **GrapesJS core**（BSD-3-Clause・無料） / Studio SDK は不採用 |
| Workspace Isolation | **git worktree**（git 標準） |
| Memory 3 層 | Mem0 + ChatThread + Obsidian + 自前統合（M-30） |
| Knowledge Graph（P2） | **Apache AGE**（Postgres 拡張・MIT） |
| Frontend | Next.js 15 + shadcn + React Flow + Recharts + Tailwind |
| Backend | FastAPI + SQLAlchemy 2.0 + Pydantic + uv + ruff + pyright |
| DB | Supabase Postgres + RLS + pgvector + pg_trgm + pgsodium + pg_cron |
| Auth | Supabase Auth + 2FA + OAuth |
| Realtime | Supabase Realtime + 自前 WebSocket（2 系統）|
| Storage | Supabase Storage |
| 観測 | Langfuse self-host（MIT）+ Sentry + Better Stack |
| Hosting P1 | Vercel Hobby + Oracle Cloud Free Tier + Supabase Free（**¥0**）|
| Hosting P1.5 | Vercel Pro + Coolify on VPS + Supabase Pro |
| CI/CD | GitHub Actions |
| Test | pytest + vitest + Playwright（P2 で MCP 統合）|
| Container | Docker Compose |

## 重要なライセンス確認

✅ **AGPL 混入なし**（CI で license-checker + pip-licenses による継続防御）

⚠️ **要注意 4 件（全クリア）**：
- Sentry（BSL 1.1）→ 自社運用 OK・SaaS 再販 NG・Build-Factory は再販しない
- Obsidian → 各ユーザ個別契約・我々は連携のみ
- Vercel Hobby → 個人 use・Phase 1.5 で Pro 移行
- Docker Desktop → 大企業有料・ENGINE BASE は対象外

## Phase 別コスト

| Phase | 月額（運用） | 備考 |
|---|---|---|
| Phase 1（dogfood）| **¥125 + Claude Max ¥30,000（個人負担）** | 実質運用コスト ¥125（ドメインのみ）|
| Phase 1.5（社内拡張） | ¥17,525-21,025 | + 各メンバー Claude プラン |
| Phase 2（β試用） | ¥40,000-80,000 | + 顧客課金で相殺可能 |
| Phase 3（商用 SaaS） | ¥120,000-200,000 | MAU 100 で採算 |

## 開発スタック決定根拠（差分）

### LangGraph 採用（OpenAI Agents SDK 不採用）
- LangGraph は state machine + handoff + guardrails + sessions を全部実装可能
- OpenAI Agents SDK と機能重複 → 依存削減で運用負荷低減
- Klarna / Uber / J.P. Morgan の本番採用実績

### Codex CLI（Apache 2.0）参考方針
- 実装エンジンとして使うのではなく**コードを読んで設計を参考**
- M-27 Intent Router / M-28 Context Builder / M-30 Memory / M-12 OS sandbox に活用
- 依存に入れない（言語が Rust + TS のため Python 移植）
- ライセンス遵守：Apache 2.0 はコード断片の流用 OK・著作権表示明記

### GrapesJS core 採用（Studio SDK 不採用）
- core は BSD-3-Clause で無料
- Studio SDK は $79+/mo で過剰
- 25.5k stars / 97k weekly DL の充実度

## 関連ファイル

- `../../requirements/2026-05-09_v1/` — 要件定義 v1.0
- `../../architecture/2026-05-09_v1/` — アーキ設計 v1.0（v1.1 更新は本 README 反映後）
- `../../functional-breakdown/2026-05-09_v1/` — 機能分解 v1.0
- `../../feature-decomposition/2026-05-09_v1/` — 機能分解実装 v1.0
- `../../hearing/2026-05-09_re-hearing/` — ヒアリング v2.1

## 改訂履歴
- **v1.0**（2026-05-09）：tech-stack 選定完了・全 OSS ライセンス + コスト確定
