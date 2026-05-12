# ADR-010: AI スタック再設計 (5 層 → 3 層 / Anthropic 純正中心 + マルチプロバイダ柔軟性)

- **Status**: Accepted (supersedes ADR-002)
- **Date**: 2026-05-10
- **Deciders**: 高本まさと

## Context

ADR-002 で確定した 5 層 AI スタック (LangGraph + LiteLLM + claude-agent-sdk + Anthropic Agent Teams + openai/codex 参照) を実装フェーズ着手前 (T-S0-08 直前) に再評価した。

### 再評価のきっかけ
masato から「**会話状態 / コンテキスト管理 / 過去履歴保持 / 最適化のロジック実装精度を最高にしたい**」と要望。
これは LLM の精度ではなく、**Agent ランタイム周辺ロジックの精度**を求める要望。

### 候補 4 つの比較

| 機能 | LangGraph (旧 L1) | claude-agent-sdk (公式) | OpenAI Agents SDK | 自作 |
|---|---|---|---|---|
| 会話履歴 | 自前 MessagesState | **SDK 内蔵 session** | SDK 内蔵 | 自前 |
| Cross-session 状態 | checkpointer (PostgresSaver) | **SDK 内蔵 session resume** | sessions API | 自前 |
| 長期記憶 | なし (別途 Mem0) | **公式 Memory API 統合** | なし | 自前 |
| Prompt cache | 手動設定 | **自動適用 (5min ephemeral)** | × Claude 非対応 | 手動 |
| コンテキスト圧縮 | 自前 trim_messages | **3-tier compaction が公式実装** | 手動 | 自前 |
| Tool result trim | 自前 | **自動** | 自動 | 自前 |
| 95% 構造化サマリー | 自前 (9 セクション) | **公式 Best Practice 内蔵** | × | 自前 |
| Subagent (handoff) | ノード分岐 | **Task tool 内蔵** | handoff API | 自前 |
| Claude 特化最適化 | × (provider-agnostic) | **◎ (Claude 専用設計)** | × | 設定次第 |

→ **Agent ランタイム精度では claude-agent-sdk が圧倒的に優位**。

### 但し他プロバイダ柔軟性も必要
masato から「他の ChatGPT や Gemini API も使えるようにしたい」要望もあり。
画像生成 (Gemini Image / DALL-E) / 音声 (Whisper) / 安価バッチ (Gemini Flash) などサブ用途で必要。

## Decision

**3 層 + マルチプロバイダ二刀流** に再構成する:

```
┌──────────────────────────────────────────────────────┐
│ Layer 3: claude-agent-sdk + Subagent (Anthropic 公式) │
│   - Subagent (Task tool) = handoff (mary→devon→quinn) │
│   - Session resume (checkpoint)                      │
│   - 3-tier compaction (auto)                         │
│   - Memory tool 統合                                 │
│   - MCP server で外部ツール統合                      │
├──────────────────────────────────────────────────────┤
│ Layer 2a (メイン): anthropic-python (Claude 専用)    │
│   - extended thinking                                │
│   - prompt caching (cache_control: ephemeral 5min)   │
│   - Memory API / Files API / Citations / Batch API   │
│   - Computer Use (必要時)                            │
│                                                      │
│ Layer 2b (サブ): LiteLLM (マルチプロバイダ抽象化)    │
│   - 安価バッチ → Gemini 1.5 Flash                    │
│   - 画像生成 → Gemini Image / OpenAI DALL-E          │
│   - 音声認識 → OpenAI Whisper                        │
│   - 緊急代替 → Anthropic 障害時のフォールバック     │
├──────────────────────────────────────────────────────┤
│ Layer 1: PostgreSQL + Mem0 + Obsidian                │
│   - sessions / chat_threads / chat_messages          │
│   - audit_logs / cost_logs                           │
│   - Mem0 (Memory API の補完、ベクトル検索)           │
│   - Obsidian (人間可読 Markdown 永続記憶)            │
│   - Constitution (松本の判断基準、system prompt 注入)│
└──────────────────────────────────────────────────────┘
```

### 削除
- **LangGraph** (旧 Layer 1) → claude-agent-sdk Subagent + 自前 PostgreSQL session で代替
- **Anthropic Agent Teams** (旧 Layer 4) → claude-agent-sdk に統合済み
- **openai/codex** (旧 Layer 5) → 参照のみだったが、明示的に依存リストから外す

### 保持・強化
- **claude-agent-sdk** → Layer 3 の中核に昇格
- **anthropic-python** → Layer 2a として直接呼び出し
- **LiteLLM** → Layer 2b としてサブ用途に縮退 (削除しない)
- **Mem0 + Obsidian + Constitution** → Layer 1 で長期記憶を補完

### 自前実装が必須なもの (絶対やる)
SDK が自動で面倒見ない領域は、以下を必ず自前実装する:

1. **Cross-session memory recall** = Mem0 ベクトル検索 + Obsidian + Memory API の統合 API
2. **Past conversation 全文検索** = `chat_messages` を pg_trgm + pgvector で検索
3. **Constitution 自動注入** = 全 AI 社員のシステムプロンプトに常時注入
4. **Cost tracking (案件別 / AI 別 / 日次)** = `cost_logs` テーブル + Anthropic Usage API + LiteLLM cost callback
5. **Rate limit 自動 retry** = tenacity による指数バックオフ (2s/4s/8s/16s)
6. **Streaming UI (WebSocket)** = SDK の streaming → WS 経由でフロントへ流す
7. **Anthropic 障害時のフォールバック** = Layer 2b の LiteLLM に自動切替 (Gemini / GPT-4)
8. **Memory API 容量管理** = Anthropic Memory API の上限管理 + Mem0 へのオフロード

## Consequences

### 得られるもの
- ✅ **Agent ランタイム精度**: Anthropic Best Practice (3-tier compaction / Subagent / Memory API) を SDK 内蔵で享受
- ✅ **コンテキスト管理**: session 内は SDK 自動、cross-session は Memory 3 tier で復元
- ✅ **新機能採用速度**: Anthropic 新機能 (Memory API / Computer Use / Batch API / Citations) をすぐ使える
- ✅ **マルチプロバイダ柔軟性**: LiteLLM Layer 2b で残す → Gemini / GPT を必要時に
- ✅ **コスト最適化**: Claude prompt cache (50%+ 削減) + 安価タスクは Gemini Flash
- ✅ **シンプルさ**: 5 層 → 3 層、自前実装を最小化
- ✅ **障害耐性**: Anthropic 障害時 LiteLLM 経由でフォールバック

### 諦めるもの
- ❌ LangGraph の柔軟な graph orchestration → Subagent + 自前 state で代替
- ❌ LangGraph の checkpointer 機能 → claude-agent-sdk session resume + DB で代替
- ❌ マルチエージェントの A/B 実験容易性 → Phase 2 で必要時に再評価
- ❌ Subagent デバッグの可視性 (LangGraph の方が graph 可視化が成熟) → audit_log + Sentry で補完

### 主要変更タスク (tickets.json)

#### 削除 / 縮退
- `T-M12-01` LiteLLM Router → **縮退**: メイン経路から外し、サブ用途に限定
- 旧 LangGraph 関連タスク (該当があれば) → ARCHIVE

#### 書き直し / 強化
- `T-S0-08` claude-runner: claude-agent-sdk + Subagent ベースで再実装
- `T-020-02` memory: claude-agent-sdk + Memory API + Mem0 ハイブリッド
- `T-021-03` swarm: Subagent (Task tool) + git worktree

#### 新規追加 (T-AI-01 〜 T-AI-08)
- `T-AI-01` Anthropic Memory API 統合 (NEW)
- `T-AI-02` Mem0 ベクトル検索 + Memory API ブリッジ (NEW)
- `T-AI-03` chat_messages 全文検索 (pg_trgm + pgvector) (NEW)
- `T-AI-04` Constitution 自動注入エンジン (NEW)
- `T-AI-05` Cost tracking (Anthropic Usage API + LiteLLM callback) (NEW)
- `T-AI-06` Rate limit 自動 retry (tenacity 指数バックオフ) (NEW)
- `T-AI-07` Streaming UI (WebSocket bridge) (NEW)
- `T-AI-08` Anthropic 障害時 LiteLLM フォールバック (NEW)

### 検討した代替案
- **A. Anthropic 純正シンプル (LiteLLM 完全削除)** = マルチプロバイダ柔軟性失う、却下
- **B. (採用) Anthropic 純正中心 + LiteLLM サブ復活**
- **C. 現状維持 + Anthropic 新機能追加** = 5 層維持で複雑、却下
- **D. 現状維持** = 「精度最高」要望に応えられず、却下

### 関連
- 影響を受ける要件: M-32 (新規) anthropic-native + multi-provider
- 影響を受けるタスク: T-S0-08 / T-020-02 / T-021-03 / T-M12-01 / T-AI-01〜08 (新規 8 件)
- supersedes: ADR-002

## 参考

- Anthropic Engineering Blog: "Effective context engineering for AI agents" (3-tier compaction)
- Anthropic Engineering Blog: "How we built our multi-agent research system"
- claude-agent-sdk Python リファレンス
- Anthropic Memory API ドキュメント (2025)

## Amendments

### 2026-05-12: tickets.json 更新漏れ監査 + 7 タスク仕様修正 (PR #131)

ADR-010 改訂時 (2026-05-10) に tickets.json の対応更新が一部漏れていたことが
判明し、SDK auto 機能を「自前実装 (NEW)」として残していた 7 タスクを
ADR-010 準拠に書き直した。

#### きっかけ
セッション中に T-M28-02 (Tier 1 tool result trim) を `label: NEW` の記述に
従って自前 3 戦略 (size cap / age cap / dedup) で実装しかけた所、masato が
「これは claude-agent-sdk が auto で提供する機能 = 自作不要」と指摘。
さらに PR #128 (T-M28-04) も同じ誤りで keyword heuristic を自前実装して
いたことが判明。tickets.json と ADR-010 の整合性監査を実施した。

#### 監査範囲
tickets.json 全 178 タスクから SDK 関連キーワード 17 種で 17 候補を抽出し、
ADR-010 の規定 (`SDK 任せ` vs `自前実装必須 8 項目 T-AI-01〜08`) と照合。
加えて main にマージ済の 4 PR (#120/#121/#122/#126) の実装を確認、
本セッション未マージの 3 PR (#128/#129/#130) も検査。

#### 監査結果

| カテゴリ | 件数 | TIDs |
|---|---|---|
| 仕様修正必要 → PR #131 で修正 | 7 | T-M28-02/03/04, T-M27-01, T-M27-01b (新規), T-M27-03, T-003-02 |
| 仕様 OK (元から ADR-010 整合) | 9 | T-S0-08, T-020-02, T-021-03, T-AI-01〜08, T-M12-01 |
| マージ済実装 OK | 4 PRs | #120, #121, #122, #126 |
| マージ済 (未) → close | 1 PR | **#128 (T-M28-04 keyword heuristic 自前)** |

#### 修正内容 (PR #131)

- `T-M28-02` NEW → **REUSE** (SDK auto trim activation + audit_logs wrapper)
- `T-M28-03` NEW → **REUSE** (cache_control: ephemeral 有効化 + cost_logs に
  cache_read_input_tokens 記録)
- `T-M28-04` NEW → **REFACTOR** (SDK auto-generated 9-section summary を
  chat_messages.compressed_summary に persist する wrapper のみ; summarization
  ロジック自前禁止)
- `T-M27-01` NEW → **ARCHIVE** (LangGraph base setup; superseded by T-M27-01b)
- `T-M27-01b` **NEW** (新規追加) (claude-agent-sdk entry node)
- `T-M27-03` NEW → **REUSE** (SDK Task tool handoff wrapper)
- `T-003-02` title + AC cleanup (「+ LangGraph」削除 / claude-agent-sdk 明示)

各修正タスクの UNWANTED に「自前実装したら lint script が fail する」機械的
ガード文言を追加 (再発防止)。`scripts/lint-mock.sh --no-langgraph` で監視。

加えて `adr_link` フィールドを 7 タスクに追加し、ADR ↔ tickets の双方向
traceability を確立。

#### 教訓 (Lessons Learned)

1. **ADR 改訂時は必ず tickets.json の依存変更を同時に行う**。決定だけ書いて
   仕様 (tickets) を更新しないと、ADR 不読の実装者 (AI 含む) が古い仕様で
   走ってしまう。
2. **`label: NEW` の AC が "implement as specified" 等の generic 文言の場合は
   要警戒**。ADR で REUSE/REFACTOR に書き換わっているはず。
3. **機械的ガード (lint UNWANTED) を仕様に組み込む**。「lint fail させる」
   文言を AC の UNWANTED に明記することで、再発防止を仕様レベルで強制。
4. **既存実装 PR の事前監査**。新仕様で見直すと既存実装が違反していること
   がある (PR #128 の例)。PR 作成時に ADR cross-ref をレビュー必須化。

#### 影響範囲

- ❌ コード変更: なし (本 PR は tickets.json + ADR-010 のみ)
- ✅ tickets: 178 → 179 (T-M27-01b 追加)
- ✅ validate-tickets.py: 179/179 PASS
- ✅ lint-no-langgraph: PASS (実装側に LangGraph import 残骸なし)
- 既存マージ済実装は全て新仕様と整合 (修正不要)
- 未マージ PR #128 のみ閉鎖、他 PR は新仕様と元から整合

#### Follow-up (本 Amendment 範囲外)

T-S0-08 (claude-agent-sdk runner 基盤) マージ後に以下の実装 PR を作り直す:
- T-M28-04 SDK auto summary persist wrapper (~50 行)
- T-M28-02 SDK auto trim activation wrapper (~30 行)
- T-M28-03 cost_logs cache_read_tokens recorder (T-AI-05 と連携)
- T-M27-01b claude-agent-sdk entry node
- T-M27-03 SDK Task tool handoff wrapper (T-M27-02 + T-003-02 マージ後)
