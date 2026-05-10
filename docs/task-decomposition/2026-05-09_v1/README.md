# Build-Factory task-decomposition v1.0（2026-05-09）

このフォルダは **task-decomposition スキルの最終出力**を保管します。

要件定義 + アーキ + functional-breakdown + tech-stack + feature-decomposition を入力に、**34 機能を 104 + 統合テスト 8 + 監査 1 = 113 タスクに分解**。既存 bootstrap 実装の活用ラベル（REUSE / REFACTOR / NEW / ARCHIVE）付き。

## ファイル一覧

| ファイル | 役割 | 想定読者 |
|---|---|---|
| `client-summary.md` | クライアント・PM 向け説明 | PM / クライアント |
| `tickets.json` | 113 タスク + 依存 DAG + REUSE/REFACTOR/NEW ラベル | distributed-dev / Claude Code 入力 |
| `tickets.html` | Kanban 風タスクカード一覧 | 開発者 |
| `interfaces.md` | 主要 API インターフェース定義 | 開発者 / 外部実装者 |
| `decision-log.json` | 判断ログ + 既存活用マッピング + リサーチ | MCP 連携 / 案件 DB 蓄積 |

## クイックビュー

### 数字
- **113 タスク** = 104 機能タスク + 8 Sprint 統合テスト + 1 既存実装監査
- **既存活用率：32% 削減**（152 → 104）
- **総工数（人間単独）：約 58 人日 → 9-10 週間**
- **総工数（Claude Code 並列）：約 17-18 日 → 4-5 週間**
- **dogfood 開始ライン：Week 5-6（部分） / Week 8-9（フル）**

### タスク種別分布
| ラベル | 件数 | 工数係数 |
|---|---|---|
| 🟢 REUSE（既存活用）| 約 15 | × 0.2-0.3 |
| 🟡 REFACTOR（既存基礎 + v2.1 改修）| 約 50 | × 0.5-0.7 |
| 🔴 NEW（全面新規）| 約 48 | × 1.0 |
| ⚫ ARCHIVE | 9 ファイル（タスクではなく対象ファイル） | - |

### Critical Path（12 ブロッカータスク）
1. T-019-01 bootstrap 整理
2. **T-S0-13 既存実装インベントリ監査**（最重要・新規）
3. T-001-01 Supabase init
4. T-001-02 認証 DDL refactor
5. T-001-04 プロジェクト DDL
6. T-001-06 RLS 全テーブル
7. T-S0-08 Supabase BE wrapper
8. T-S0-09 RLS helper
9. T-021-03 permission middleware
10. T-020-02 LiteLLM wrapper
11. T-003-02 AI 社員召喚
12. T-M28-01 Context Builder

### 重要ルール：v2.1 仕様適合性検証

各 REFACTOR タスクは「動いている = OK」ではなく「v2.1 仕様通り = OK」を強制。
追加 AC として：
- 既存実装と requirements / architecture / functional-breakdown の照合
- 不足列 / RLS / index / enum 値の検出 + migration / patch
- M-21 custom_permissions / M-28 Context Builder / F-026 Constitution 連携確認
- 単体テストで v2.1 仕様の振る舞いを検証

## Sprint 別集計

| Sprint | 期間 | タスク数 | 工数（人間日）| Claude Code 並列（日） |
|---|---|---|---|---|
| Sprint 0（基盤 + 監査） | W1-2 | 36 | 11.0 | 3-4 |
| Sprint 1（認可 + UX）| W2-3 | 10 | 4.6 | 1.5 |
| Sprint 2（AI 基盤 + Runtime）| W3-4 | 26 | 9.7 | 3 |
| Sprint 3（仕様化）| W4-5 | 17 | 6.7 | 2 |
| Sprint 4（管理層 + UX）| W5-6 | 16 | 6.4 | 2 |
| Sprint 5（実行コア）| W6-7 | 21 | 6.7 | 2 |
| Sprint 6（並列 swarm）| W7-8 | 13 | 6.1 | 2 |
| Sprint 7（連携・観測）| W8-9 | 16 | 6.4 | 2 |
| **合計** | | **155**（重複除き 113） | **57.6 人日** | **17-18 日** |

## 次のスキル進行順

```
✅ task-decomposition v1.0  ← イマココ完了
  ↓
distributed-dev（各タスクを Claude Code が単独実装できるブランチ実装パッケージ化）
  ↓
画面モック生成（43 screens の HTML モック・F-005b・M-5b 適用）★ 次の作業
  ↓
Phase 1 dogfooding 開始（Week 1-2 〜 Week 9-10）
```

## 関連
- `../../tech-stack/2026-05-09_v1/` — tech-stack v1.0
- `../../feature-decomposition/2026-05-09_v1/` — feature-decomposition v1.0
- `../../functional-breakdown/2026-05-09_v1/` — functional-breakdown v1.0
- `../../architecture/2026-05-09_v1/` — アーキ v1.0
- `../../requirements/2026-05-09_v1/` — 要件定義 v1.0

## 改訂履歴
- **v1.0**（2026-05-09）：113 タスク（104 機能 + 8 統合 + 1 監査）+ 既存活用ラベル + Critical Path + API インターフェース定義
