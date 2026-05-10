# Architecture Decision Records (ADR)

Build-Factory プロジェクトの主要な技術判断・設計判断を時系列で記録する。

## 形式

各 ADR は次の構造:
- **Status**: Proposed / Accepted / Superseded
- **Context**: なぜこの判断が必要だったか
- **Decision**: 何を決めたか
- **Consequences**: 結果として得られるもの・諦めるもの

## 一覧

| ADR | テーマ | Status | 作成日 |
|---|---|---|---|
| [ADR-001](ADR-001-modular-monolith.md) | モジュラーモノリス採用 (vs マイクロサービス) | Accepted | 2026-05-09 |
| [ADR-002](ADR-002-ai-stack-5-layer.md) | AI スタック 5 層構成 | ⚠️ Superseded by ADR-010 | 2026-05-09 |
| [ADR-003](ADR-003-memory-3-tier.md) | Memory 3 tier 構成 | Accepted | 2026-05-09 |
| [ADR-004](ADR-004-phase1-zero-cost-hosting.md) | Phase 1 ¥0 ホスティング | Accepted | 2026-05-09 |
| [ADR-005](ADR-005-lucide-icons-only.md) | アイコンは Lucide のみ (絵文字禁止) | Accepted | 2026-05-09 |
| [ADR-006](ADR-006-task-labels.md) | タスクラベル REUSE/REFACTOR/NEW/ARCHIVE | Accepted | 2026-05-09 |
| [ADR-007](ADR-007-ears-notation.md) | EARS notation 必須 | Accepted | 2026-05-09 |
| [ADR-008](ADR-008-kanban-by-feature.md) | Kanban を機能別アコーディオン (4 列) | Accepted | 2026-05-10 |
| [ADR-009](ADR-009-project-bootstrap-enforcement.md) | 各案件への強制レイヤー自動展開 | Accepted | 2026-05-10 |
| [ADR-010](ADR-010-ai-stack-anthropic-native.md) | AI スタック再設計 (5層→3層 / Anthropic 純正中心 + マルチプロバイダ柔軟性) | Accepted | 2026-05-10 |

## 新しい ADR を書くとき

1. 連番でファイル作成 (`ADR-XXX-short-title.md`)
2. このテーブルに 1 行追加
3. CLAUDE.md §6 の「直近セッションで決まったこと」にも追記
