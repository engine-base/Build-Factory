# Pre-flight AC Audit Workflow

「速 × 徹底」を両立するための **タスク着手前監査 (pre-flight audit)** ワークフロー。
事後監査ループ (PR レビュー時に gap 発見 → 修正 commit → 再 review) を廃止し、
**着手前に AC × test × impl × lint の 1 表を完成させてから実装** する。

---

## なぜ必要か (反省)

PR #247 (T-M30-03) で 3 周の事後 self-audit を行い、累計 6 件の gap (HIGH 1 / MEDIUM 3 / LOW 2) を発見・閉鎖した。徹底度は最終的に 12/12 AC まで上げたが、コスト構造は以下:

- 1 周目 (PR 作成時): G1-G6 + 主要 AC ✅、ただし lint #14 hard-coded / cross-module invariant 2/3 / docstring 部分対応 etc. が漏れた
- 2 周目 (post-audit `b20af62`): HIGH 1 + MEDIUM 1 + LOW 2 を閉鎖
- 3 周目 (final-audit `799e81a`): MEDIUM 2 を閉鎖 (service docstring / caplog)

各周は 30-45 分。**着手前に網羅していれば 1 周で済んだ**。

---

## ワークフロー (4 ステップ)

### Step 1 (着手前): pre-flight audit doc を作成

`docs/audit/<TASK-ID>.md` を `docs/audit/_template.md` から複製して作る。
全 AC を spec から逐語コピーし、対応列を埋める:

| 列 | 中身 |
|---|---|
| **spec 文** | tickets.json から逐語コピー (改変禁止) |
| **impl** | 実装ファイル:行 (`backend/services/foo.py:42`) |
| **test** | 1:1 対応 test 関数名 |
| **lint** | 該当する scripts/lint-mock.sh check 番号 (任意) |
| **status** | `PLANNED` → `IMPL_DONE` → `TEST_PASS` → `VERIFIED` |

**Step 1 完了基準**: 全 AC 文 (UBIQUITOUS / EVENT-DRIVEN / STATE-DRIVEN / UNWANTED の 4 文 + 補足文) について impl/test 欄に少なくとも計画値が入っている。空欄禁止 (N/A の場合は理由明記)。

### Step 2 (実装中): 行ごとに status 更新

impl を書いたら `IMPL_DONE`、test が通ったら `TEST_PASS`、lint 通過後 `VERIFIED`。
**「VERIFIED 以外の行があるうちは PR を出さない」** を原則とする。

### Step 3 (PR 作成): audit doc を PR description にリンク

PR の Test plan セクションに `docs/audit/<TASK-ID>.md` を貼る。
PR コメントは表 1 つ + 数字 + 監査 link のみ。長文説明禁止。

### Step 4 (PR 後): post-audit を 1 回だけ

ユーザに「完璧か」と聞かれたら、audit doc を再 grep して 1 周だけ追加監査。
2 周目以降は **やらない** (誤発見が増える + コストが嵩む)。

---

## 適用ルール

| 対象 | pre-flight audit 必須か |
|---|---|
| REUSE / REFACTOR / NEW (全タスク) | **必須** |
| ARCHIVE | 不要 (削除のみ) |
| 緊急 hotfix (本番影響) | 事後 audit でも可 (24h 以内) |
| Phase 2 以降 | (まだ運用しない / Phase 1 完走後に検討) |

---

## 関連

- `_template.md` : 空テンプレ (同フォルダ内)
- `T-M30-03.md` : first filled example (post-mortem として retrofit、同フォルダ内)
- `../2026-05-10_v1/` : 旧 audit 成果物 (ac-coherence-report.md, existing-inventory) — 別目的 (codebase inventory) なので別系統

## バージョニング方針

このフォルダ (`2026-05-13_v2/`) は **workflow snapshot**. workflow を改訂する際は
`2026-MM-DD_v3/` を作り CLAUDE.md の link を切り替える。旧 v2 は履歴として温存。
個別 task の audit doc (`T-XXX-YY.md`) は **現行 v フォルダの直下** に配置する.

---

**運用開始: 2026-05-13 (T-M30-03 post-mortem を契機に確立)**
**v2 snapshot 保管: 2026-05-13 (commit 304eb59 後、別 commit で版管理)**
