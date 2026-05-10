# ADR-006: タスクラベル REUSE / REFACTOR / NEW / ARCHIVE

- **Status**: Accepted
- **Date**: 2026-05-09
- **Deciders**: 高本まさと

## Context

Build-Factory は **bootstrap 実装** が既に存在する状態でタスク分解した:
- 40 routers
- 50 services
- 8 Supabase migrations
- 一部の React コンポーネント

そのため、新規開発と同じやり方でタスクを切ると:
- **152 タスク** に膨れ上がる
- **既存実装の再活用が漏れる**
- **重複実装でコスト二重**

要件:
- 既存実装 (bootstrap) を最大限活用したい
- ただし「動く ≠ 仕様通り」なので、適合チェックも必要
- 不要な実装 (onlook 等) は削除する

## Decision

全 113 タスクに **4 種類のラベル** を必ず付ける:

### REUSE (14 件)
- **既存実装をそのまま使う**
- 変更なし、テスト追加のみ
- 例: `T-001-01` FastAPI モジュラーモノリス基盤 (bootstrap 済み)

### REFACTOR (50 件)
- **既存実装をベースに修正・拡張する**
- 必須: **v2.1 適合チェック** (9 項目) で「仕様通りか」確認
  1. 仕様書の AC を全て満たすか
  2. EARS 形式で AC が書かれているか
  3. テストカバレッジ ≥ 70%
  4. shadcn/ui 使用 (独自 UI なら許容理由を明記)
  5. Lucide Icons のみ (絵文字なし)
  6. ENGINE BASE green (#1a6648) を主色に使用
  7. RLS が正しく設定されているか (DB タスクの場合)
  8. audit_log への記録があるか
  9. エラーハンドリング (ユーザーフレンドリーなメッセージ)
- 例: `T-002-01` Supabase Auth 統合 (既存に 2FA + OAuth 追加)

### NEW (49 件)
- **完全新規実装**
- 既存に無い、または既存を捨てて作り直すべきもの
- 例: `T-008b-01` EARS パーサ (新規)

### ARCHIVE (9 件)
- **既存実装を削除する**
- 仕様変更で不要になった or 別技術に切替
- 例: `T-019-01` onlook フォルダ削除 (Codex CLI 採用しないため)

## Consequences

### 得られるもの
- ✅ タスク数 152 → 113 に圧縮 (REUSE/REFACTOR で再活用)
- ✅ AI 社員 (devon) が「既存をどう扱うか」即座に判断可能
- ✅ v2.1 適合チェックで品質担保 (REFACTOR の落とし穴回避)
- ✅ ARCHIVE で技術的負債を計画的に削除

### 諦めるもの
- ❌ ラベル付け作業のコスト → 1 回限りなので許容
- ❌ ラベル誤り (REUSE のつもりが要修正) → REFACTOR に格上げで対応

### ラベル統計 (2026-05-09 時点)
```
REUSE     : 14 (12.4%)
REFACTOR  : 50 (44.2%)
NEW       : 49 (43.4%)
ARCHIVE   :  9 (8.0%)
─────────────────
合計       : 113 + 9 = 113 (ARCHIVE は完了タスクとしてカウント)
```

### 関連
- 影響を受けるタスク: 全 113 件
- 詳細: `docs/task-decomposition/2026-05-09_v1/tickets.json` (各タスクに `label` フィールド)
- 適合チェック詳細: `docs/task-decomposition/2026-05-09_v1/decision-log.json` の `v2.1_compliance_rule`
