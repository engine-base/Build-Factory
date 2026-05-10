# ADR-002: AI スタック 5 層構成

- **Status**: ⚠️ **Superseded by [ADR-010](ADR-010-ai-stack-anthropic-native.md)** (2026-05-10)
- **Date**: 2026-05-09
- **Deciders**: 高本まさと

> **このADRは ADR-010 で置き換えられた**。masato から「Agent ランタイム精度 (会話状態 / コンテキスト管理 / 履歴保持) を最高にしたい」要望を受け、5 層 → 3 層 (Anthropic 純正中心 + LiteLLM サブ復活) に再構成。
> **新スタックは [ADR-010](ADR-010-ai-stack-anthropic-native.md) を参照**。
> このファイルは履歴として保存する。

## Context

AI 社員 (BMAD 10 ペルソナ) を実行する基盤を選ぶ必要があった。要件:

- **複数プロバイダ対応** (Anthropic / OpenAI / 将来 Gemini など)
- **handoff** (秘書 → 社員 AI への引き継ぎ)
- **guardrails** (ロール権限・レッドライン違反検知)
- **subprocess 実行** (Claude Code 自体を起動)
- **Multi-Agent** (Plan / Gen / Eval の役割分担)
- **過剰設計を避ける** (1 人で運用)

候補ライブラリ:
- LangChain / LangGraph
- OpenAI Agents SDK (handoff / guardrails / sessions あり)
- claude-agent-sdk
- crewAI / autogen
- 自作 (FastAPI で全て手書き)

## Decision

**5 層構成** で組み合わせる:

```
┌─────────────────────────────────────────────────────────┐
│ Layer 5: openai/codex (Apache 2.0) ← 参照のみ依存しない │
├─────────────────────────────────────────────────────────┤
│ Layer 4: Anthropic Agent Teams ← Claude Code 内 P/G/E   │
├─────────────────────────────────────────────────────────┤
│ Layer 3: claude-agent-sdk ← subprocess で Claude Code   │
├─────────────────────────────────────────────────────────┤
│ Layer 2: LiteLLM ← プロバイダ抽象化                     │
├─────────────────────────────────────────────────────────┤
│ Layer 1: LangGraph ← オーケストレーション (handoff/etc) │
└─────────────────────────────────────────────────────────┘
```

各層の責務:
1. **LangGraph**: 全体のフロー制御 (秘書 → mary → winston → devon → quinn の handoff)
2. **LiteLLM**: モデル切替 (claude-opus-4-7 / claude-sonnet-4-6 / gpt-4 など)
3. **claude-agent-sdk**: 実装タスクのみ Claude Code を subprocess で起動
4. **Anthropic Agent Teams**: Claude Code 内部で Plan → Gen → Eval を回す
5. **openai/codex**: ランタイムロジック (M-27/28/30/12) のパターン参照のみ、依存はしない

## Consequences

### 得られるもの
- ✅ プロバイダ非依存: 将来 Gemini や OSS LLM (Llama 等) に切替可能
- ✅ Claude Code をフル活用: 実装は強力な Claude Code に任せる
- ✅ 段階的に組み立てられる: Phase 1 は LangGraph + LiteLLM のみで動く
- ✅ OpenAI Agents SDK の機能 (handoff/guardrails) は LangGraph で十分カバー

### 諦めるもの
- ❌ 学習コスト: 5 層を理解する必要がある → CLAUDE.md / ADR で明文化
- ❌ debug が複雑化 (どの層で失敗したか) → 各層で audit_log に記録
- ❌ OpenAI Agents SDK / openai-python に直接依存しない (LiteLLM 経由のみ)
  - → OpenAI 専用機能 (Assistants API 等) は使えない、現状デメリットなし

### 検討した代替案
- **OpenAI Agents SDK 直採用** = プロバイダ縛り + handoff/guardrails が独自仕様 → 不採用
- **crewAI / autogen** = 過剰設計、学習コスト高 → 不採用
- **自作** = 工数大、車輪の再発明 → 不採用

### 関連
- 影響を受けるタスク: T-S0-08 (claude-runner) / T-021-03 (swarm) / T-M12-01 (litellm router)
