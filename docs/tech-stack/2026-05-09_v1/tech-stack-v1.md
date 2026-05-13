# Build-Factory tech-stack v1.0

**作成日**：2026-05-09
**前提**：要件定義 v1.0 + アーキ v1.0 + functional-breakdown v1.0
**ライセンス方針**：Apache 2.0 / MIT / BSD / Elastic 2.0 / BSL（self-host のみ）/ PostgreSQL License・**AGPL 完全除外**

## 1. AI / LLM スタック（5 層・簡素化版）

```
LangGraph (MIT)
   ↓ 全体 state machine + handoff + checkpoint + human-in-the-loop
LiteLLM (MIT・self-host)
   ↓ Provider 抽象化（Claude / OpenAI / Gemini / 拡張）
claude-agent-sdk (MIT)
   ↓ ▶︎ 再生時の subprocess 起動
Anthropic Agent Teams (Claude Code 内部のみ)
   Plan/Gen/Eval

📚 参考：openai/codex (Apache 2.0)
   コードロジック参考のみ・依存なし・M-27/28/30/12 の実装パターン流用
```

**不採用**：OpenAI Agents SDK / openai-python（直接利用なし）/ GrapesJS Studio SDK（core で十分）

## 2. Frontend

| 項目 | 採用 | ライセンス |
|---|---|---|
| Framework | Next.js 15 (App Router) | MIT |
| UI | shadcn/ui + Tailwind CSS 4 | MIT |
| Graph | React Flow | MIT |
| Chart | Recharts | MIT |
| State | Zustand + TanStack Query | MIT |
| HTML Editor (P1.5) | **GrapesJS core** | BSD-3-Clause |
| Package | pnpm | MIT |

## 3. Backend

| 項目 | 採用 | ライセンス |
|---|---|---|
| Framework | FastAPI（モジュラーモノリス）| MIT |
| Lang | Python 3.13 + uv | MIT/Apache 2.0 |
| ORM | SQLAlchemy 2.0 + Pydantic + Supabase Python SDK | MIT/Apache 2.0 |
| Subprocess | claude-agent-sdk | MIT |
| MCP Server | Anthropic MCP Python SDK | MIT |
| Worker | asyncio.Semaphore + Queue | 標準 |
| Lint | ruff | MIT |
| Type Check | pyright | MIT |
| Logging | structlog | MIT/Apache 2.0 |

## 4. DB / 認証 / Realtime / Storage

| 項目 | 採用 | ライセンス |
|---|---|---|
| DB | Supabase Postgres | PostgreSQL License |
| Auth | Supabase Auth | Apache 2.0 |
| Realtime | Supabase Realtime + 自前 WebSocket（2 系統）| Apache 2.0 |
| Storage | Supabase Storage | Apache 2.0 |
| Vector | pgvector | PostgreSQL License |
| FTS | Postgres FTS + pg_trgm | PostgreSQL License |
| 暗号化 | pgsodium | BSD-2-Clause |
| 定期実行 | pg_cron | PostgreSQL License |
| Partition (P2) | pg_partman | PostgreSQL License |
| Knowledge Graph (P2 / C-12) | Apache AGE | Apache 2.0 |
| Migration | Supabase CLI | Apache 2.0 |

## 5. Memory / Knowledge

| 層 | 実装 | OSS |
|---|---|---|
| 短期 | ChatThread + ChatMessage（current session）| 自前 + pgvector |
| 中期 | ChatMessage 圧縮済 + audit_logs + 9-section summary | 自前 + pgvector |
| 長期 | Mem0 + Obsidian Vault + Constitution | Mem0 (Apache 2.0) + Obsidian (各ユーザ契約) |
| Compaction | Claude 流 3-tier（tool result trim + prompt cache + 9-section）| 自前 + Anthropic prompt cache |

## 6. 観測

| 項目 | 採用 | ライセンス | 備考 |
|---|---|---|---|
| LLM 観測 | Langfuse self-host | MIT | $50-80/mo for 5M spans/day |
| エラー | Sentry | BSL 1.1 | 自社運用 OK・SaaS 再販 NG |
| Uptime | Better Stack | SaaS | 無料 10 monitors |

## 7. インフラ（Phase 1 = ¥0）

| 項目 | 採用 | コスト |
|---|---|---|
| Frontend | Vercel Hobby | ¥0 |
| Backend / Worker / Langfuse | Oracle Cloud Free Tier（永久無料 4 vCPU + 24GB RAM）| ¥0 |
| DB / Auth / Storage | Supabase Free（500MB） | ¥0 |
| エラー | Sentry Free | ¥0 |
| Uptime | Better Stack Free | ¥0 |
| CI/CD | GitHub Actions Free（2000 min/mo public） | ¥0 |
| DNS | Vercel DNS or Cloudflare Free | ¥0 |
| ドメイン | .com 年契約 | ¥125/月 |
| **小計** | | **¥125/月** |
| ユーザ Claude Max（個人負担）| | ¥30,000/月 |

## 8. ライセンス警告（4 件・全クリア）

| 項目 | 警告 | 対応 |
|---|---|---|
| Sentry（BSL 1.1）| SaaS 再販禁止 | OK・自社運用のみ |
| Obsidian | プロプライエタリ | 各ユーザ個別契約 |
| Vercel Hobby | 個人 use 推奨 | P1.5 で Pro $20/mo 移行 |
| Docker Desktop | >250 名 / >$10M revenue で有料 | ENGINE BASE は対象外 |

## 9. AI 社員構成（10 体メンバー → 4 体リーダー → 1 体 COO）

| Phase | 数 | 構成 |
|---|---|---|
| Phase 1 | 10（メンバー）| Mary BA / Preston PM / Winston Architect / Sally PO / Devon Dev / Quinn QA / Reviewer / Brand / Mockup / Curator |
| Phase 1.5 | +4（部署リーダー）| Sam (Eng Lead) / Dani (Design Lead) / Quinn-Lead (QA Lead) / Logan (Knowledge Lead) |
| Phase 2 | +1（COO）| 全部署統括 |
| Future | +N（個人クローン）| ユーザ別の分身（別サービス C-11） |

→ 全 AI 社員は **LangGraph node** として動作・**LiteLLM** 経由で LLM 呼出・**既存 96 スキル**から選定された persona prompt + skills で構成

## 10. 開発エンジン（実装層）

| 項目 | 採用 | 備考 |
|---|---|---|
| デフォルト | **Claude Code**（Pro/Max・各ユーザ OAuth） | dogfooding の主軸 |
| 切替対応 | **C-13 Phase 2**（Codex CLI / Gemini CLI 等）| 必要時に adapter 追加 |
| 参考実装 | **Codex CLI**（Apache 2.0）| コードロジック参考のみ・依存なし |

## 関連
- `selected-stack.json` — 後続スキル入力用
- `cost-projection.md` — Phase 別詳細試算
- `tech-stack-v1.html` — クライアント提示用

---

## 2026-05-13 Addendum — ADR-012 反映 (Anthropic 公式 Memory / Provider-adapter)

### Anthropic 公式 Memory / Context 機能を一級市民として採用

| 公式機能 | 公式名 | Beta header | 採用方針 |
|---|---|---|---|
| Memory Tool | `memory_20250818` | (不要) | client-side handler 自前実装 (`anthropic_memory_tool.py`). Obsidian Vault 共有 |
| Context Editing (tool clearing) | `clear_tool_uses_20250919` | `context-management-2025-06-27` | `client.beta.messages.create(..., context_management=...)` |
| Compaction | `compact_20260112` | `compact-2026-01-12` | server-side summarization (50K 以上) |
| Extended Thinking clearing | `clear_thinking_20251015` | (上記 beta) | opt-in, 必ず先頭配置 |
| Subagent Memory | `/memories/subagent/*` | (Memory Tool 経由) | persona 別 working memory |
| Dreaming | (research preview) | (未確定) | Phase 2 で評価 |

### Provider 切替経路 (任意 + 障害時 両対応)

| 経路 | 既存 stack 要素 | 追加実装 (T-AI-MEM-04) |
|---|---|---|
| 任意切替 (BYOK) | `services/byok_store.py` + `routers/byok.py` | precedence source として REUSE |
| 任意切替 (workspace 設定) | `entities/workspaces` (新規 column `preferred_provider`) | T-024-04 migration |
| 任意切替 (per-session) | `entities/chat_sessions.active_route` (既存) | provider_adapter 拡張 |
| 任意切替 (per-request header) | (新規 `X-LLM-Provider` 受領) | provider_adapter 拡張 |
| 障害時 fallback | `services/circuit_breaker.py` (既存) + T-AI-08 | provider_adapter 拡張 |
| LiteLLM transport | `services/litellm_router.py` (既存) | REUSE |

### License 確認 (ADR-012 採用機能)

- `anthropic` (Python SDK): MIT ✅
- `mem0ai` (>= 0.1.50, 既存): Apache-2.0 ✅
- `python-frontmatter` (既存): MIT ✅
- Anthropic Memory Tool / Context Editing: Anthropic API (proprietary, 利用契約に従う)
- AGPL なし (`scripts/lint-mock.sh --agpl` で機械検知, ADR-004)

### Cost 影響 (Phase 1 ¥0/月 構成)

- Memory Tool / Context Editing / Subagent Memory: **追加課金なし** (Anthropic API 内蔵 / prompt cache 効果)
- BYOK 使用時: ユーザ側 API キー課金 (Build-Factory に課金発生せず)
- LiteLLM fallback 時: 切替先 provider の従量課金 (T-AI-05 cost tracking で監視)

### selected-stack.json 同期

`ai_stack.anthropic_native_features` / `ai_stack.provider_switch` に追加 (別 commit で json 同期).

### 関連 ADR

- ADR-010 (AI Stack Anthropic native) — Amended by ADR-012
- ADR-012 (Anthropic Memory Tool / Context Editing / Subagent Memory 採用 / Provider-adapter)
- ADR-004 (Phase 1 ¥0 hosting) — 影響なし
