# Build-Factory v3 Phase 1 — Group D (Drift fix) タスク分解

> 作成日: 2026-05-16
> profile: `skills/task-decomposition/references/profiles/build-factory.md`
> output: `docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-d-drift.json`
> 上流: `docs/functional-breakdown/2026-05-16_v3/{entity,api,screen}-drift-summary.md`

## サマリー

| metric | 値 |
|---|---|
| 総 task 数 | 15 |
| group 内訳 | D-1 (entity drift) 4 / D-2 (RLS 補完) 4 / D-3 (API drift) 2 / D-4 (screen drift) 1 / D-NEW (new entity formalization) 3 / D-CLOSE (validation) 1 |
| category | db 8 / backend 3 / frontend 1 / cleanup 1 / infra 2 |
| label | REFACTOR 11 / FIX 3 / ARCHIVE 1 |
| deliverable_layer | backend 9 / ui 1 / polish 5 |
| 推定総工数 | 56h |
| 並列実時間 | ~12h (parallel capacity 6 想定) |
| Wave | 4 (Phase 1 末尾 single wave / Group A/B/C 完了後に開始) |
| 想定 PR 数 | 15 |

## drift 対応マッピング

| drift type | 件数 | 対応 task |
|---|---|---|
| entity rename / spec alignment (高 3 件) | 3 | T-V3-D-01 |
| bf_ prefix decision (中 4 件) | 4 | T-V3-D-02 |
| 型/enum drift (中 6 件) | 6 | T-V3-D-03 |
| twin tables ARCHIVE (中 4 件) | 4 | T-V3-D-04 |
| RLS 補完 (new 25 件) | 25 | T-V3-D-05 (3) + T-V3-D-06 (9) + T-V3-D-07 (6) + T-V3-D-08 (7) |
| API method mismatch (5 件) | 5 | T-V3-D-09 |
| API high non-method + medium (3 件) | 3 | T-V3-D-10 |
| screen h1/KPI drift (9 件) | 9 | T-V3-D-11 |
| entity critical (impl 無し 3 件) | 3 | T-V3-D-12 |
| Screen-Component pair (E-022/23/24) | 3 | T-V3-D-13 |
| AuditLog 二重実装統合 (E-037/55) | 2 | T-V3-D-14 |
| 全 drift closure 検証 | — | T-V3-D-15 |

## 各タスク一覧

| ID | タイトル | category | label | layer | est_hr | depends_on |
|---|---|---|---|---|---:|---|
| T-V3-D-01 | Entity rename + spec alignment (E-008/021/012) | db | REFACTOR | backend | 4 | [] |
| T-V3-D-02 | bf_ prefix decision (E-014/15/16/17) | db | REFACTOR | backend | 5 | [] |
| T-V3-D-03 | Enum/PK 型 drift (E-002/03/04/05/20/25) | db | REFACTOR | backend | 6 | [] |
| T-V3-D-04 | Twin tables ARCHIVE (E-014L/07L/27L/32L) | cleanup | ARCHIVE | polish | 4 | [T-V3-D-01, T-V3-D-03] |
| T-V3-D-05 | RLS batch1: AI clone family (E-044/45/46) | db | REFACTOR | backend | 3 | [] |
| T-V3-D-06 | RLS batch2: auth & profile family (E-047〜E-055) | db | REFACTOR | backend | 5 | [] |
| T-V3-D-07 | RLS batch3: bf_project family (E-056〜E-061) | db | REFACTOR | backend | 4 | [] |
| T-V3-D-08 | RLS batch4: design & infra (E-062〜E-068) | db | REFACTOR | backend | 4 | [] |
| T-V3-D-09 | API method mismatch fix (5 endpoints PUT/PATCH/GET 統一) | backend | FIX | backend | 3 | [] |
| T-V3-D-10 | API high non-method (3 endpoints: api-tokens / exports / design-tokens) | backend | FIX | backend | 4 | [] |
| T-V3-D-11 | Screen h1/KPI drift (9 hint-match screens) | frontend | REFACTOR | ui | 6 | [] |
| T-V3-D-12 | Critical new entities (E-009/13/10) | db | FIX | backend | 5 | [] |
| T-V3-D-13 | Screen-Component pair + Screen-vs-BFMock merge (E-022/23/24) | db | FIX | backend | 4 | [] |
| T-V3-D-14 | AuditLog 二重実装統合 (E-037 + E-055) | db | REFACTOR | backend | 3 | [T-V3-D-06] |
| T-V3-D-15 | Drift closure validation (final gate) | infra | FIX | polish | 3 | [T-V3-D-01〜14] |

## 着手プロトコル (各 task 共通)

1. `cp docs/audit/2026-05-13_v2/_template.md docs/audit/2026-05-16_v3/T-V3-D-NN.md`
2. tickets-group-d-drift.json から該当 task の 3-tier AC を逐語コピーして audit MD に貼り付け
3. branch 作成: `git checkout -b claude/T-V3-D-NN`
4. work_package_boundary.editable 配下のみ編集 (forbidden / readonly を尊重)
5. drift summary の対象 entity / API / screen を **1 つずつ** 確認しながら実装
6. 完了後 3-tier AC × audit MD impl line × CI gate を 1:1 で確認
7. PR 作成 → CI gate (8 件) auto-merge

## Wave 配置 / 並列実行

- 全 task は `wave: 4` (Phase 1 末尾)
- 前提: Group A (Foundation Phase 0) / Group B / Group C (Wave 1-3) が **全件 done** に到達
- T-V3-D-15 を除く 14 task は (depends_on を尊重して) **並列実行可能**
- 直列必須:
  - T-V3-D-04 ← (T-V3-D-01, T-V3-D-03)
  - T-V3-D-14 ← T-V3-D-06
  - T-V3-D-15 ← T-V3-D-01〜14 全件
- parallel capacity 6 を想定し、3 batch (= 1 batch 4-5 task) で消化 → 実時間 ~12h

## 重要 (慎重に扱う事項)

- **本 task の対象外**: 既存 backend ~340 endpoint legacy (impl あるが spec なし) → 別 audit phase で個別判定
- **破壊的変更**: T-V3-D-01 (ALTER TABLE RENAME), T-V3-D-03 (enum CHECK + PK 型), T-V3-D-04 (legacy table _archived_ prefix), T-V3-D-14 (auth_audit_log → audit_logs 統合) は audit MD で **「破壊的変更」明記**, ADR 起票必須.
- **security_critical**: T-V3-D-06 (2FA + encrypted_secrets), T-V3-D-10 (api_token display-once)
- ADR 新規起票: ADR-013 (entity-table-naming alignment), ADR-014 (bf_ prefix decision), ADR-015 (legacy twin archive), ADR-016 (API method alignment PUT/PATCH), ADR-017 (Screen vs BFMock merge), ADR-018 (audit_log unification)

## 関連ファイル

- 構造化 JSON: `tickets-group-d-drift.json`
- audit MD 15 件: `docs/audit/2026-05-16_v3/T-V3-D-01.md` 〜 `T-V3-D-15.md`
- 上流 drift summary: `docs/functional-breakdown/2026-05-16_v3/{entity,api,screen}-drift-summary.md`
- 上流 entities.json: `docs/functional-breakdown/2026-05-16_v3/entities.json`
- profile: `skills/task-decomposition/references/profiles/build-factory.md`
