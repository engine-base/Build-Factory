# ADR-012: Anthropic Memory Tool / Context Editing / Subagent Memory 採用

- **Date**: 2026-05-13
- **Status**: Accepted
- **Author**: masato (高本まさと) / 株式会社 ENGINE BASE
- **Supersedes**: なし (ADR-010 amend)
- **Related**: ADR-003 (Memory 3-tier), ADR-010 (AI スタック Anthropic native)

---

## 背景

Anthropic は 2025-08〜2026-05 にかけて以下の公式機能を GA / public beta で提供:

| 公式機能 | 公開日 | 用途 |
|---|---|---|
| **Memory Tool** (`memory_20250818`) | 2025-08 GA | client-side file CRUD (`/memories/` directory) |
| **Context Editing** (`clear_tool_uses_20250919`) | 2025-09 GA (beta header) | 古い tool_result を自動 clear |
| **Compaction** (`compact_20260112`) | 2026-01 GA (beta header) | 会話全体を server-side 要約 |
| **Subagent Memory** | 2026-02 (Claude Code v2.1.33) | subagent ごと persistent knowledge store |
| **Managed Agents Memory** | 2026-04 public beta | Claude Platform 側 memory file system |
| **Memory Import** | 2026-03 | 他 AI ツールからの memory 移植 |
| **Dreaming** | 2026-05 research preview | 過去 session の background review |

Build-Factory ではこれまで `services/context_builder.py` (Mem0 + Obsidian + Constitution unified API), `services/mid_term_layer.py` (9-section structured summary), `services/tier1_tool_trim.py` (tool result audit wrapper) を自前実装してきた. これらは公式機能と機能が重なる. ADR-010 の方針 (claude-agent-sdk + anthropic-python 中心) と整合させ, **再実装 (NIH) を避け公式機能を最大活用する** ことを本 ADR で明文化する.

---

## 決定

### Decision 1: Memory Tool (`memory_20250818`) を一級市民として採用

- backend/services/anthropic_memory_tool.py に `BetaAbstractMemoryTool` subclass の純 file-backed handler を実装.
- `/memories` 仮想 root → Obsidian Vault dir (env `OBSIDIAN_VAULT_DIR`) にマップ. Build-Factory の Obsidian Vault を Claude が **自動で read/write** できる状態にする (人間編集も並存可だが必須でない).
- claude-agent-sdk / anthropic-python から tool 経由で呼ばれる. application 直接呼出も `MemoryToolHandler` のメソッドとして expose.
- path traversal 防止 (pathlib.Path.resolve + relative_to) は client-side 実装の責任 (公式 doc 要件).

### Decision 2: Context Editing を SDK config で明示有効化

- backend/services/anthropic_context_editing.py に `default_context_management_config()` を実装.
- 既定 strategy:
  1. `clear_tool_uses_20250919` (trigger 30K tokens / keep 4 tool_uses / `exclude_tools: ["memory"]` で Memory tool 結果は保護)
  2. `compact_20260112` (trigger 180K tokens / custom instructions)
  3. `clear_thinking_20251015` (trigger 50K tokens, **最初** に配置必須)
- claude-agent-sdk / anthropic-python `client.beta.messages.create(..., context_management=...)` に渡す.
- Beta headers: `context-management-2025-06-27` + `compact-2026-01-12`.

### Decision 3: Subagent Memory を handoff の引継ぎ知識保管に活用

- backend/services/handoff_service.py に `SubagentMemoryStore` を追加.
- `request_handoff(source, target, message, ...)` 実行時:
  - source persona の memory snapshot (`/memories/<source>/handoff/<timestamp>.md`) を Memory Tool 経由で書く.
  - target persona の memory pre-load を `register_handoff_backend` の payload に含める.
- subagent ごとの scope (user / project) は env / workspace_id で切替.

### Decision 4: 既存自前モジュールは「公式機能の薄い wrapper」として残す

- context_builder / mid_term_layer / tier1_tool_trim はそのまま保持. ただし内部実装を **公式機能 (Memory Tool / Context Editing / SDK auto-compaction) の delegation** に segueway する.
- Build-Factory 固有要件 (audit_logs テーブル / RLS / cost tracking / 構造化 summary 9-section) は wrapper 側に残す.
- ADR-010 自前実装必須 8 項目 (T-AI-01〜08) の T-AI-04 (Constitution 注入) は **Memory Tool で `/memories/constitution/` 配下に注入する形** で再構成する (新規実装は不要 / Memory Tool の標準動作で達成).

### Decision 5: マルチプロバイダ provider-adapter (任意切替 + 障害時 fallback の両対応)

ADR-010 (LiteLLM サブ) + T-AI-08 (Anthropic 障害時 fallback) + 既存 `provider_adapter.select_provider` / `byok_store` (BYOK 持ち込みキー) と整合させるため, **Memory Tool / Context Editing / Subagent Memory に provider-adapter を被せる**. これにより以下の **2 つの切替経路** を同一インターフェースで提供する.

#### 5.1 切替経路 (両方サポート必須)

| 経路 | トリガ | ユースケース |
|---|---|---|
| **(A) 任意切替** | ユーザ / 運用者 / workspace 設定 / per-session header / per-task config | コスト最適化 (Gemini Flash 安価バッチ) / モデル選好 (画像生成は Gemini Image) / A/B test (同 task を 2 provider で比較) / BYOK (ユーザ持ち込みキー) |
| **(B) 障害時 fallback** | Anthropic 障害検知 (T-AI-08 / circuit_breaker) で自動 | 緊急代替 (Claude → GPT-4o / Gemini 2.5 Pro 自動切替) |

#### 5.2 切替決定のレイヤ (precedence)

```
per-request override (header X-LLM-Provider)
  ↓
per-session active_route (chat session 内で固定)
  ↓
per-workspace preference (workspaces.preferred_provider)
  ↓
per-user BYOK key 有無 (byok_store, ユーザが持ち込んだキー優先)
  ↓
ADR-010 既定 (Anthropic main / LiteLLM サブ)
  ↓
障害時 fallback (T-AI-08 circuit_breaker 発火時)
```

最終的に解決された provider に対して **同一の MemoryToolHandler / Subagent Memory / Context Editing 設定** が適用される (filesystem は provider 非依存 = Obsidian Vault は全 provider 共有).

#### 5.3 機能ごとの adapter 挙動

| 機能 | Anthropic 経路 | OpenAI (GPT-4o 等) | Gemini (2.5 Pro / Flash 等) |
|---|---|---|---|
| Memory Tool (file CRUD) | `memory_20250818` server tool | OpenAI tools `type: "function"` × 6 commands → 同 HTTP API | Gemini `function_declarations` × 6 commands → 同 HTTP API |
| Context Editing (clear) | `clear_tool_uses_20250919` (beta header) | `truncation_strategy=auto` + 自前 keep N | 自前 keep N (Gemini に該当 server 機能なし) |
| Compaction | `compact_20260112` (server-side) | client-side 自前 summarizer (conversation_summarizer.generate_summary, G9 ハッチ) | client-side 自前 summarizer (同上) |
| Subagent Memory | `/memories/subagent/<persona>/...` | provider 非依存 (filesystem + HTTP API) | provider 非依存 (同上) |
| Extended Thinking clearing | `clear_thinking_20251015` (beta header) | skip (該当機能なし, warning log) | skip (同上) |

#### 5.4 実装範囲 (T-AI-MEM-04 + T-024-04 で別途タスク化)

> **関連 ticket**: T-AI-MEM-04 (provider-adapter 本体) / T-024-04 (workspaces.preferred_provider column migration; precedence の workspace 層 source)

- backend/services/provider_adapter_memory.py 新規:
  - `tool_spec_for(provider: Literal["anthropic","openai","gemini"]) -> dict | list[dict]`
    - anthropic → `{"type": "memory_20250818", "name": "memory"}`
    - openai    → 6 commands を OpenAI function spec で expose
    - gemini    → 6 commands を Gemini function_declarations で expose
  - `resolve_active_provider(request_ctx) -> str` (precedence 5.2 を実装)
  - `context_editing_for(provider: str) -> dict` (Anthropic native config / OpenAI fallback / Gemini fallback の 3 経路)
- 既存 `routers/provider_adapter.py` 拡張:
  - GET  /api/provider/active                ← 現在のアクティブ provider 取得
  - POST /api/provider/active                ← per-session / per-workspace 任意切替
  - POST /api/provider/fallback/trigger      ← 障害検知時の自動 fallback 発火 (circuit_breaker 連携)
- 既存 `byok_store` / `byok.py` 経路を **任意切替経路の優先 source** として活用 (ユーザ持ち込みキーがある provider はその provider を使うのが既定).
- 既存 `litellm_router.py` を OpenAI / Gemini 呼出 transport として活用 (新規追加なし).

#### 5.5 BYOK + workspace 切替の UX

- workspace 設定画面で `preferred_provider` を選択 (anthropic / openai / gemini / auto).
- `auto` は ADR-010 既定 (Anthropic main).
- ユーザが BYOK で OpenAI / Gemini キーを登録すると, 自動で provider 候補に加わる.
- chat UI 上で per-session の override (drop-down で provider 一時切替) も可能.
- API caller は `X-LLM-Provider: openai` header で per-request override.

---

## 結果 (Consequences)

### Positive

- **NIH 削減**: tool trim / compaction / memory CRUD の自前実装を停止. 公式機能の改善が自動で取り込まれる.
- **chat 自動更新**: Obsidian Vault が Claude から自動 read/write される. 人間編集の頻度を下げられる.
- **Subagent handoff の知識継承**: mary → devon → quinn の handoff で persona 固有 memory が自然に引き継がれる.
- **Cost reduction**: prompt cache + context editing + compaction の組合せで long-running workflow のコスト削減 (公式 doc 主張: 最大 90%).

### Negative

- **Vendor lock-in 増 (限定的)**: Memory Tool / Context Editing / Compaction の **server tool spec は Anthropic 専用** (OpenAI / Gemini に同等機能なし). Decision 5 の provider-adapter で degradation を保証するが, server-side compaction は失われ自前 summarizer に切替が必要.
- **Provider parity gap**: GPT-4o / Gemini fallback 時は context window 管理を自前で行う必要があり, Anthropic 経路と比べてコスト効率 / 精度が劣化する可能性.
- **Beta header 管理**: `context-management-2025-06-27` / `compact-2026-01-12` の GA 移行に追随する運用負荷.
- **Memory file の sensitive data 漏洩リスク**: Vault に PII / 鍵が書かれないよう memory handler 側で validation 必須.

### Neutral

- ADR-010 の「メイン経路 = claude-agent-sdk + anthropic-python のみ」方針と整合 (LangGraph / LiteLLM を増やすわけではない).
- ADR-003 (Memory 3-tier) の概念モデルは保持. Tier 1 (short) は SDK Memory tool / Tier 2 (mid) は SDK compaction / Tier 3 (long) は Mem0 + Obsidian の構図に再配置.

---

## 採否判断のための実装ゲート

| ゲート | 判定基準 |
|---|---|
| Memory Tool wrapper unit test | path traversal 防止 + 6 commands 全網羅 + 4 AC 1:1 |
| Context Editing config unit test | 3 strategy 全網羅 + Memory tool exempt + Beta header 明示 |
| Subagent Memory integration test | handoff source/target persona の memory pre-load 検証 |
| 既存自前モジュールの非劣化 | 既存 6000+ pytest が全 pass / coverage >= 70% |

---

## Migration Plan

1. **Phase 1 (本 ADR と同時)**:
   - 新規 module 3 件 (anthropic_memory_tool / anthropic_context_editing / SubagentMemoryStore)
   - 既存 context_builder の Obsidian read/write を Memory Tool 経由に置換 (OBSIDIAN_VAULT_DIR を `/memories` 仮想 root にマップ)
   - REST endpoint 新設 (POST `/api/memory/{command}`)

2. **Phase 1.5 (T-S0-08 SDK 接続後)**:
   - claude-agent-sdk runner で Memory Tool を tools list に追加
   - Context Editing config を default で activate
   - Subagent Memory を handoff 経路で activate

3. **Phase 2 (Managed Agents Memory 公開後)**:
   - Anthropic Platform 側の Memory storage と Build-Factory 側の dual-write を検討
   - Memory Import で他 LLM からの移植経路を整備

---

## 機械的強制レイヤー (lint)

- `scripts/lint-mock.sh` に新規 check 追加:
  - app code が `BetaAbstractMemoryTool` を経由せずに `/memories` 直接 path 操作したら fail
  - claude-agent-sdk 経路 (services/anthropic_memory_tool.py 以外) で `memory_20250818` raw tool spec を組み立てたら fail (重複定義防止)
- 自前 trim / compaction 関連の禁止語 lint (T-M28-02 / T-M30-03 で実装済) は本 ADR でも有効.

---

## Open Questions

- Managed Agents Memory への移行タイミング (Phase 2 のいつ?)
- Memory file の暗号化 (pgsodium ベース vs filesystem 暗号化)
- Memory file の sensitive data validation policy (T-AI-04 / Constitution と整合)

---

**Approved by**: masato (高本まさと)
**Implementation owner**: Build-Factory 開発工場 OS チーム
