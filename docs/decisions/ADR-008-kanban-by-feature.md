# ADR-008: Kanban を機能別アコーディオン (4 列)

- **Status**: Accepted (supersedes initial Hermes-style 6-column)
- **Date**: 2026-05-10
- **Deciders**: 高本まさと

## Context

S-027 タスク Kanban の構造について、初期モックは [Hermes](https://hermes.app) 流のフラット 6 列だった:

```
[Triage] [Todo] [Ready] [In Progress] [Blocked] [Done]
```

→ 113 タスクをフラットで並べると **横スクロール地獄**、特に「機能 X の進捗だけ見たい」が困難。

masato からの指摘:
> "tritageとかTODOとかREADYとかに分けるのが正解かな？
> 機能ごとに分けてそこから開ける（カテゴリかタスクかで分けてその中でtriageとかTODOとかにした方がいいのでは？)"

要件:
- **機能 (F-XXX) 単位で進捗を見たい** (どの機能がどこまで進んだか)
- **状態列はシンプルに** (4 列で十分)
- **完了済み機能は折りたたみ** で視界からどける
- **進行中の機能は展開** で詳細が見える

## Decision

**機能別アコーディオン → 4 列ミニ Kanban** の 2 段構造に変更:

### 1 段目: 機能 (F-XXX) アコーディオン
```
▼ F-005 ヒアリング (5/8 完了) ━━━━━━━━━━━━ 62%
  [4 列ミニ Kanban]
▼ F-006 仕様生成 (7/12 完了) ━━━━━━━━━━━━ 58%
  [4 列ミニ Kanban]
▶ F-013 GitHub PR (折りたたみ)
▶ F-001 platform-base ✓ 完了 (折りたたみ)
```

### 2 段目: 4 列ミニ Kanban (各機能内)
```
| TODO | IN PROGRESS | REVIEW | DONE |
| 2件   | 1件 (pulse) | 1件 (PR)| 4件 |
```

### 状態の意味
- **TODO**: 着手前 (Triage / Ready 統合)
- **IN PROGRESS**: AI 実行中 (pulse-dot で表現)
- **REVIEW**: PR 作成済み、レビュー待ち
- **DONE**: マージ済み

### Blocked は別扱い
- 失敗・依存待ちは別列ではなく、**該当機能に赤いバナー** で警告
- 全機能横断で "Blocked タスク一覧" は別画面 (S-028 task_list) で見る

### デフォルト動作
- 進行中の機能 (IN PROGRESS タスクあり) のみ展開
- 完了済み (100%) と未着手 (0%) は折りたたみ
- ユーザー操作: 「全て展開」「全て折りたたみ」ボタン

## Consequences

### 得られるもの
- ✅ 機能単位で進捗が一目で分かる (進捗バー + X/Y 完了)
- ✅ 113 タスクでも縦スクロールで全機能を俯瞰可能
- ✅ 4 列に簡素化で各カラム幅が広い → 情報量増 (担当 / 経過時間 / PR 番号など)
- ✅ Sprint 内の関連タスクが横並びになる
- ✅ Hermes 流の俯瞰性は S-029 DAG ビューで補完

### 諦めるもの
- ❌ 全タスクのフラット俯瞰 → S-028 task_list / S-029 DAG で補完
- ❌ Blocked 列の独立性 → 件数が多くなれば再導入を検討

### 検討した代替案
- **A 案 (Hermes 流フラット 6 列)** = 113 タスクで横スクロール地獄、却下
- **B 案 (今回採用) 機能別アコーディオン → 4 列**
- **C 案 担当者別グループ** = 担当が devon に集中する Phase 1 では機能しない、却下
- **D 案 Sprint 別グループ** = Sprint またぎのタスクを表示できない、却下

### 関連
- 影響を受けるタスク: T-007-01 (Kanban UI 基盤) / T-007-02 (フィルタ・ソート)
- モック: `docs/mocks/2026-05-09_v1/task/S-027-task-kanban.html`
- 参考: GitHub Projects の "Group by status" + "Group by milestone"
