# Build-Factory タスク分解結果（クライアント・PM 向け）

## 分解の方針

Phase 1 Must の 34 機能を **113 タスク**に分解しました（既存 bootstrap 実装を活用して 152 → 113 に圧縮）。

**主要原則：**
1. 1 タスク = 人間 0.5-2 日 / Claude Code 0.5-3 時間（並列実行で実質短縮）
2. 単一責務（FE / BE / DB / WK / TST レイヤー別）
3. Claude Code が単独実装できる self-contained 単位
4. EARS notation で受け入れ条件統一
5. **既存実装は「動いている = OK」ではなく「v2.1 仕様通り = OK」を強制検証**

## タスク種別ラベル

| ラベル | 件数 | 説明 |
|---|---|---|
| 🟢 REUSE | 14 | 既存実装そのまま活用 + 接続確認 |
| 🟡 REFACTOR | 50 | 既存基礎 + v2.1 仕様に改修 |
| 🔴 NEW | 49 | 全面新規実装 |
| ⚫ ARCHIVE | 9 ファイル（タスクではなく対象ファイル）| 経営系を `_archived/` 移動 |

## Sprint 別工数

| Sprint | 期間 | タスク | 工数（人間日）| Claude Code 並列 |
|---|---|---|---|---|
| Sprint 0（基盤 + 監査）| W1-2 | 36 | 11.0 | 3-4 日 |
| Sprint 1（認可 + UX）| W2-3 | 10 | 4.6 | 1.5 日 |
| Sprint 2（AI 基盤 + Runtime）| W3-4 | 26 | 9.7 | 3 日 |
| Sprint 3（仕様化）| W4-5 | 17 | 6.7 | 2 日 |
| Sprint 4（管理層 + UX）| W5-6 | 16 | 6.4 | 2 日 |
| Sprint 5（実行コア）| W6-7 | 21 | 6.7 | 2 日 |
| Sprint 6（並列 swarm）| W7-8 | 13 | 6.1 | 2 日 |
| Sprint 7（連携・観測）| W8-9 | 16 | 6.4 | 2 日 |
| **合計** | | **113** | **57.6 日** | **17.5 日** |

→ **人間単独：9-10 週間 / Claude Code 並列：4-5 週間**

## Critical Path（12 ブロッカー）

最優先で固める 12 タスク・約 6 日（人間）/ 1.5 日（Claude Code 並列）：
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

## dogfood 開始ライン

| 段階 | タイミング | 達成内容 |
|---|---|---|
| 部分 dogfood | **Week 5-6** | ヒアリング AI + 仕様書 HTML + 単発 ▶︎ + 壁打ちが回る |
| フル dogfood | **Week 8** | 並列 swarm + git worktree + 連携完備 |
| Phase 1 完成 | **Week 9-10** | 自社 1 案件 End-to-End 完走 |

## v2.1 仕様適合性検証（重要）

各 REFACTOR タスクは追加 AC として：
- 既存実装と requirements / architecture / functional-breakdown の照合
- 不足列 / RLS / index / enum 値の検出 + migration / patch
- M-21 custom_permissions / M-28 Context Builder / F-026 Constitution 連携確認
- 単体テストで v2.1 仕様の振る舞いを検証

→ 古い仕様で書かれた既存実装が、v2.1 で求める仕様に確実に準拠することを担保。

## 次のステップ

```
✅ task-decomposition v1.0  ← イマココ完了
  ↓
画面モック作成（43 screens の HTML モック・F-005b・M-5b 適用）★ 次の作業
  ↓
distributed-dev（各タスクを Claude Code 実装パッケージ化）
  ↓
Sprint 0 から実装開始（dogfooding）
```

## 関連ファイル

- `tickets.json` — 113 タスク + 依存 DAG + ラベル + 既存ファイル参照
- `tickets.html` — Kanban 風タスクカード一覧
- `interfaces.md` — 主要 API インターフェース定義
- `decision-log.json` — 12 主要決定 + 既存活用マッピング + リサーチ
