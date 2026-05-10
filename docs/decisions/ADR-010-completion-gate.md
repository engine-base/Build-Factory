# ADR-010: 完了判定の単一ゲート (`pre-commit-check.sh`) と「N/A 禁止」原則

- **Status**: Accepted
- **Date**: 2026-05-10
- **Deciders**: 高本まさと
- **Trigger**: T-019-01 完了報告時に「v2.1 適合チェックの大半を N/A で埋め、リグレッションテストを実行せず PR を出した」状態が発生したため。

## Context

`docs/task-decomposition/IMPLEMENTATION_PROTOCOL.md` Step 6 / 7 は「テスト実行」「v2.1 適合チェック」を求めているが、運用上 2 つの抜け穴があった:

1. **「N/A」記入の濫用**: 削除タスクや UI 変更なしの場合に「該当なし」で項目を埋め、判定の根拠が言語化されない。
2. **テスト未実行のまま完了報告**: 「静的解析だけ」「ARCHIVE は削除のみだから動作確認不要」という自己判断で `pytest` / `tsc` / アプリ起動 smoke を省略する。

T-019-01 では `backend/routers/design_frames.py` から `_inject_preload` / `Path` import を削除しており、削除タスクであっても他所からの参照や app 起動への影響を確認せずに完了とするのは危険だった (実際には大丈夫だったが、検証なしの「大丈夫」は再現性のあるプロセスではない)。

## Decision

### 1. 単一の完了ゲートを `scripts/pre-commit-check.sh` に集約する

このスクリプトは 4 段階の検査を機械的に実行し、結果を `.last-precommit-check` (JSON) に記録する:

| # | 検査 | 失敗の意味 |
|---|---|---|
| 1 | `lint-mock` (絵文字 / AGPL / ARCHIVE 残留 / tickets メタ) | CLAUDE.md §5 の絶対ルール違反 |
| 2 | `python-syntax` (backend 全 .py を `ast.parse`) | 構文破壊 |
| 3 | `backend-smoke` (`main:app` import + 削除済 ARCHIVE routes 残存ゼロ) | アプリ起動不能 / 残骸 |
| 4 | `frontend-tsc` (`tsc --noEmit` のエラー数 ≤ `.tsc-baseline`) | 型エラー新規導入 |

スクリプトは FAIL があれば `exit 1`、SKIP がある場合は理由を出力する。`.tsc-baseline` は技術的負債としての既知エラー数を記録し、それを超えたら新規エラーとして検出する。

### 2. `git commit` に対して機械的に強制する

`.claude/settings.json` の `PostToolUse` Bash hook が `git commit` を検出した時点で:

- `.last-precommit-check` 不在 → BLOCK 警告 (「完了判定が未実行です」)
- mtime > 30 分 → WARN (「再実行推奨」)
- `exit_code != 0` → BLOCK 警告 (「直近の check が FAIL」)

(claude-code は hook の stderr で警告される。明示無視には新たな commit メッセージが必要。)

### 3. 「N/A 禁止」原則

完了報告に `N/A` を書かない。必ず以下のいずれかに分類する:

- **PASS**: 検査が通った (機械検査の場合) / 仕様 AC を満たすことを確認した (人間確認の場合)
- **SKIP-WITH-REASON**: 「このタスクは UI 変更なしのため shadcn/ui 項目は対象外」のように、なぜ対象外かを 1 行で書く
- **TBD**: 環境上実行できない (例: pytest スイート未整備) — 別タスクとして follow-up を切る

### 4. 削除タスクほど smoke は必要

ARCHIVE / REFACTOR で「コード削除のみ」だからと smoke を省略しない。**削除参照が他所から触られているかは静的解析だけでは検出できない**。`backend-smoke` は削除タスクにこそ実行する。

## Consequences

### Positive
- 完了報告の判断が機械化され、自己評価のブレがなくなる
- 削除タスクのリグレッションを `main:app` 起動 smoke で検出できる
- ベースラインエラー数を明示することで、技術的負債の可視化と「増やさない」運用が可能

### Negative
- pre-commit-check の実行コスト (現状 5〜30 秒、`--quick` で 5 秒以下)
- pytest/vitest スイートが Sprint 0 で整備されるまでは「テストカバレッジ ≥ 70%」は未充足のまま (本 ADR ではゲートの土台を整備する範囲)

### Follow-up
- Sprint 0 (T-S0-13 以降) で pytest/vitest が立ち上がったら本スクリプトに統合
- 既存の絵文字違反 (約 200 件) と tickets メタ不足 (147/165 件) は別タスクで段階的に解消

## Related
- `docs/task-decomposition/IMPLEMENTATION_PROTOCOL.md` Step 6
- `scripts/pre-commit-check.sh`
- `.claude/settings.json` (PostToolUse Bash hook)
- `.tsc-baseline` (現在 9)
- ADR-009 (project-bootstrap-enforcement) — 各案件にも同等のゲートを展開
