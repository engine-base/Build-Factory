# v1 → v3 移行マッピング

> **作成日**: 2026-05-15
> **目的**: v1 (`docs/task-decomposition/2026-05-09_v1/tickets.json`, 187 task) の各 task が v3 でどう扱われるか / 何が新規追加か / 何が削除かを 1 ファイルで追える

## サマリ

| 分類 | v1 件数 | v3 での扱い |
|---|---:|---|
| Pre-flight audit 済 (厳密検証 30 件) | 30 | v3 REFACTOR で 3-tier AC に書き直し / 既存 impl は REUSE |
| Post-hoc auto audit (健全 ~80 件) | 80 | v3 REFACTOR + audit MD retrofit (Group H-1) |
| 怪しい 63 件 (impl 不明 / test pass のみ) | 63 | v3 Group H-1 (T-V3-AUDIT-S01..S63) で 1:1 再検証 |
| Audit MD 不在 36 件 | 36 | v3 Group H-2 (T-V3-AUDIT-M01..M36) で手動執筆 |
| 確定 gap (T-008-04 / T-013-04b / T-007-03b / T-BTSTRAP-04) | 4 | v3 Group G (T-V3-FIX-01..04) で実装完了 |
| Indirect coverage 7 件 | 7 | v3 Group H で個別検証 |

**v3 で完全新規** (v1 に対応する task が無い):

| Group | 内容 | 件数 |
|---|---|---:|
| A. Infrastructure | ADR-013/014/015 + lint #17/18/19 + AC validator + pyright/coverage gate | 8 |
| B. AUTH | S-001〜S-005 + 6 endpoint + 7 backend / 5 frontend / 3 test | 15 |
| C. DB + RLS (gap 分) | 4 不在 entity + 28 RLS policy | 28 |
| D. 重大 drift 修正 | S-006 root rewrite + accounts dashboard API + S-036/040 統一 | 5 |
| E. 未実装 15 画面 | S-008/010/011/015/020〜025/030/033/037/042/043 | 15 |
| I. Cleanup | dead table + dead router | 5 |
| J. Rename migration | bf_ prefix 廃止 + codegen | 10 |

合計 v3 = **211 task** (= 既存 v1 改修 ~150 + 完全新規 ~61 + Phase 0 infra 8)

## 詳細マッピング (v1 task → v3 task)

### Critical Path 12 件 (v1 で pre-flight audit 済)

| v1 task | v1 状態 | v3 マッピング |
|---|---|---|
| T-019-01 | 完璧 pre-flight | T-V3-CLEANUP-05 (確認 task) |
| T-S0-13 | post-hoc OK | T-V3-AUDIT-S?? (再検証) |
| T-001-01 | post-hoc OK | T-V3-AUDIT-S?? (再検証) |
| T-001-02 | 完璧 | T-V3-RF-?? (REFACTOR with 3-tier AC) |
| T-001-04 | 完璧 | T-V3-RF-?? (同上) |
| T-001-06 | 完璧 | T-V3-RF-?? (同上) |
| T-S0-08 | 完璧 | (T-V3 で REFACTOR + audit retrofit) |
| T-S0-09 | post-hoc | T-V3-AUDIT-M?? (audit MD 新規) |
| T-021-03 | 完璧 | T-V3-SCR-06 (S-021 requirements_editor) と統合 |
| T-020-02 | 完璧 | T-V3-SCR-05 (S-020 hearing) と統合 |
| T-003-02 | 完璧 | T-V3-RF-03 (S-012 workspace_dashboard) と統合 |
| T-M28-01 | post-hoc | T-V3-AUDIT-M?? (audit MD 新規) |

### 確定 gap 4 件

| v1 task | v1 状態 | v3 マッピング |
|---|---|---|
| T-008-04 | 確定 gap (UI 無し) | **T-V3-FIX-01** |
| T-013-04b | 確定 gap (Phase 1.5 切り出し空) | **T-V3-FIX-02** |
| T-007-03b | 確定 gap (audit MD すら無し) | **T-V3-FIX-03** |
| T-BTSTRAP-04 | 確定 gap (Phase 9 review で admit) | **T-V3-FIX-04** |

### 怪しい 63 件 (Group H-1 で再検証 = T-V3-AUDIT-S01..S63)

v3 tickets.json の各 T-V3-AUDIT-S## task の `legacy_task_id` フィールドに v1 ID が記録されている (sort 順):

```
T-V3-AUDIT-S01 → T-001-11
T-V3-AUDIT-S02 → T-003-03
T-V3-AUDIT-S03 → T-003-04
...
T-V3-AUDIT-S63 → T-M28-03
```

詳細は `tickets.json` の `legacy_task_id` を参照。

### Audit MD 不在 36 件 (Group H-2 で執筆 = T-V3-AUDIT-M01..M36)

```
T-V3-AUDIT-M01 → T-001-09
T-V3-AUDIT-M02 → T-001-09b
T-V3-AUDIT-M03 → T-002-01
...
T-V3-AUDIT-M36 → T-S0-10
```

## v1 で削除予定の task / 機能

| v1 task / 概念 | 理由 | v3 での扱い |
|---|---|---|
| auto-generated audit MD 116 件 (`scripts/generate-audit-mds.py`) | gap の隠れ蓑になった | **廃止** / 手動執筆強制 |
| `bf_` prefix table (5 件) | 命名ドリフト | **rename** (Group J) |
| `ai_employee_config` (legacy) | E-040 AIEmployee に統合済 | **削除** (T-V3-CLEANUP-01) |
| `projects` (legacy) | spec では `phases` / `phase_gates` | **migrate + 削除** (T-V3-CLEANUP-02) |
| `threads` (legacy conversation) | E-041 ChatThread に統合済 | **migrate + 削除** (T-V3-CLEANUP-03) |
| 既存 root `/` の AI 社員 KPI (今月売上等) | cross-project bleed | **削除 or 退避** (T-V3-DRIFT-03 + ADR-015) |

## v1 から維持する asset

- mock HTML 43 件 (`docs/mocks/2026-05-09_v1/`) — 構造は変更なし、結合先 page.tsx 側を mock に合わせる方向
- functional-breakdown (`docs/functional-breakdown/2026-05-09_v1/`) — screens.json / entities.json / features.json は spec source of truth として維持
- 既存 backend router 40+ 件 — REFACTOR で適合させる (削除は dead code のみ)
- 既存 audit MD 146 件 — legacy 参照用に保持 (v3 audit MD は別ディレクトリ `docs/audit/2026-05-15_v3/`)

## v1 / v2 / v3 共存ルール

| 場所 | v1 (legacy) | v2 (legacy) | v3 (active) |
|---|---|---|---|
| tickets | `docs/task-decomposition/2026-05-09_v1/tickets.json` | `docs/task-decomposition/2026-05-14_v2/` | `docs/task-decomposition/2026-05-15_v3/tickets.json` |
| audit | `docs/audit/2026-05-13_v2/T-*.md` | (なし) | `docs/audit/2026-05-15_v3/T-V3-*.md` |
| 参照優先度 | 低 (legacy_task_id 経由のみ) | 低 (実験的) | **高 (single source of truth)** |
| 更新可否 | freeze (修正禁止) | freeze | active |

## CI / lint の関係

v3 で追加される lint / validator は、**v1 ディレクトリには適用しない** (legacy なので freeze):

- `scripts/lint-mock.sh` (既存 16 check) → v3 で 19 check に拡張、対象は repo 全体だが mock HTML lint は v1 dir も含む
- `scripts/validate-ears-ac.py` (v3 拡張) → 引数で対象 tickets.json を指定 (default: v3)
- `scripts/validate-audit-md.py` (新規) → 対象は `docs/audit/2026-05-15_v3/` のみ
- `scripts/lint-mock-impl-diff.sh` (新規) → 対象は全 frontend route + 全 v3 関連 mock
- `scripts/lint-screens-api.py` (新規) → 対象は screens.json (v1 / 共通) ↔ backend router
- `scripts/lint-entity-table-naming.py` (新規) → 対象は entities.json (v1 / 共通) ↔ supabase/migrations

## 過去経緯

- 2026-05-09: v1 作成 (187 task)
- 2026-05-13〜14: v1 完走宣言 + Phase 9 honest review (1 件 gap admit)
- 2026-05-14: v2 縦スライス試行
- 2026-05-15: dogfood 開始時に root `/` 画面 drift (S-006) を実機確認で発見 → 全 audit 再実施 → 漏れ 100+ 件発覚 → **v3 起票**
