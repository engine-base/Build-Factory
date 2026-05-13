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

### Decision 5: マルチプロバイダ fallback (Gemini / GPT-4o) の provider-adapter

ADR-010 + T-AI-08 (Anthropic 障害時 LiteLLM フォールバック) と整合させるため, **Memory Tool / Context Editing / Subagent Memory は Anthropic 障害時に degrade 動作する provider-adapter** を用意する.

| 機能 | Anthropic 経路 | Gemini / GPT-4o fallback (T-AI-08) |
|---|---|---|
| Memory Tool (file CRUD) | `memory_20250818` server tool | `/api/anthropic-memory/*` HTTP endpoint を **provider-agnostic function calling tool** として再定義. GPT-4o / Gemini からは function calling 経由で同 HTTP API を呼ぶ. filesystem 実装が client-side なので Build-Factory 側 Obsidian Vault は共有可能. |
| Context Editing (clear/compact) | `clear_tool_uses_20250919` + `compact_20260112` | GPT-4o: `truncation_strategy=auto` / Gemini: `system_instruction` + 自前 summarizer (既存 conversation_summarizer.generate_summary 経路 = G9 backwards-compat ハッチを活用). |
| Subagent Memory | `/memories/subagent/<persona>/...` (Anthropic SDK) | provider 非依存 (filesystem 永続化 + HTTP API 経路). GPT-4o / Gemini も同じ Vault に書ける. |

**実装範囲 (T-AI-MEM-04 で別途タスク化)**:
- backend/services/provider_adapter_memory.py : function calling spec → MemoryToolHandler.dispatch() の adapter.
- OpenAI tools (`type: "function"`) / Gemini tools (`function_declarations`) の両 spec を export する factory.
- LiteLLM 経由で fallback された時に自動で adapter を差し替える経路 (既存 `routers/provider_adapter.py` 拡張).

**degradation の正確な挙動**:
- `clear_thinking_20251015` (extended thinking) は GPT/Gemini に該当機能なし → degradation 時は skip (warning log).
- `compact_20260112` (server-side summarization) は GPT/Gemini で client-side 自前 summarizer に切替 (T-AI-08 + 既存 conversation_summarizer).
- `memory_20250818` の "automatic memory check on session start" prompting は **provider 非依存の system prompt 注入** で代替.

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
