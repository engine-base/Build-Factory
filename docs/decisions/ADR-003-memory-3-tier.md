# ADR-003: Memory 3 tier 構成

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: 高本まさと

## Context

AI 社員 (特に秘書 AI = 松本の複製) が **長期記憶** を持つ必要がある。
要件:

- **数ヶ月にわたる対話** をまたいで「松本が何を判断したか」を覚えている
- **コンテキスト窓制限** (Claude Opus 4.7 1M tokens) を超える情報量
- **プロンプトキャッシュ** で API コストを抑える
- **検索可能** (過去の決定理由をすぐ引ける)

候補:
- **全部生ログ** = 検索不能、コンテキスト溢れ
- **全部要約** = 詳細失われる
- **ベクトル DB のみ** = 構造化された決定が引きづらい
- **Mem0 / LangMem 等のフルライブラリ** = ロックイン、過剰

## Decision

**3 tier 構成 + Claude API 流 compaction** で組み立てる:

### Tier 1: Short (生ログ)
- DB: `chat_threads` / `chat_messages`
- 内容: 直近の対話 (生)
- TTL: 90 日 (Phase 1) / 7 年 (Phase 2)
- 用途: 直近のコンテキストとしてそのまま入力

### Tier 2: Mid (圧縮 + 構造化)
- DB: `chat_messages` (compressed フラグ) + `audit_logs`
- 圧縮タイミング: コンテキスト 95% 到達時に自動
- 構造化サマリー: 9 セクション
  1. Primary Request and Intent
  2. Key Technical Concepts
  3. Files and Code Sections
  4. Errors and fixes
  5. Problem Solving
  6. All user messages
  7. Pending Tasks
  8. Current Work
  9. Optional Next Step

### Tier 3: Long (永続記憶)
- **Mem0** = ベクトル DB (pgvector)、検索用
- **Obsidian** = Markdown ファイル、人間が読める形
- **Constitution** (`docs/decisions/` + `~/Documents/会社運営DB/constitution/`) = 松本の判断基準

### Claude API 流 compaction (3 段階)
1. **tool result trim**: 不要なトークン削除
2. **prompt cache friendly**: `cache_control: ephemeral` (5 min TTL)
3. **9-section structured summary**: 95% 時に自動生成

## Consequences

### 得られるもの
- ✅ 数ヶ月の対話をまたいで秘書 AI が松本を再現できる
- ✅ プロンプトキャッシュで API コストを大幅削減 (5 min TTL)
- ✅ 検索可能 (Mem0 ベクトル + Obsidian テキスト + Constitution)
- ✅ 人間 (masato) が Obsidian を直接編集して記憶を矯正可能

### 諦めるもの
- ❌ 3 tier 同期の複雑さ → 専用サービス (memory-service) で隠蔽
- ❌ Mem0 の依存 → MIT ライセンスで OSS、ロックインリスク低
- ❌ 完全な audit (全対話を生で残す) は 90 日のみ → Phase 2 で 7 年化

### 関連
- 影響を受けるタスク: T-020-02 (memory) / T-M28-01 (memory 3 tier)
- 参考: Anthropic Engineering Blog "Effective context engineering for AI agents"
