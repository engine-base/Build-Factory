# Group C (UI / Vertical Slice) — Part 2 タスク一覧

> Build-Factory v3 Phase 1 / 後半 8 category (moat / onboarding / ops / review / spec / system / task / workspace = 28 mock).
> **S-027 タスク Kanban** は workspace-dashboard 級の複雑画面のため 3 task に分割 (core / drag&drop / filter)。
> Part 1 (前半 11 category / 36 mock = T-V3-C-01..36) と合わせて Group C 全 66 task 構成。

---

## サマリ

| 項目 | 値 |
|---|---|
| 担当 category | moat / onboarding / ops / review / spec / system / task / workspace |
| mock 数 (実 screens.json ベース) | **28** |
| 実 task 数 (S-027 分割 +2 込) | **30** |
| ID range | T-V3-C-37 〜 T-V3-C-64 (S-027 のみ T-V3-C-57-1/2/3) |
| Label 構成 | NEW 27 / REFACTOR 3 (S-040 / S-041 / S-028 = impl_status=exists) |
| 合計工数見積 | 122h / 30 session |
| group / wave / phase | C / 1 / Phase 1 (UI vertical slice) |
| deliverable_layer | ui (全件) |
| branch | `claude/T-V3-C-<NN>` (各 task 1 branch) |
| Foundation 依存 | Phase 0 完成 (T-FOUNDATION-01〜08 全 merged) |
| Group B 依存 | 各 task の `depends_on` に backend stub (T-V3-B-<feature_num>) で参照 |

---

## category × task

### moat (2 task / 8h)

| ID | screen | feature | label | est | depends_on |
|---|---|---|---|---|---|
| T-V3-C-37 | S-016 フェーズ管理 | F-008 | NEW | 4h | T-V3-B-008 |
| T-V3-C-38 | S-017 依存グラフ (DAG) | F-009 | NEW | 4h | T-V3-B-009 |

### onboarding (3 task / 12h)

| ID | screen | feature | label | est | depends_on |
|---|---|---|---|---|---|
| T-V3-C-39 | S-048 Build-Factory へようこそ | — | NEW | 4h | — (leaf) |
| T-V3-C-40 | S-049 最初の案件を作成 (wizard) | — | NEW | 4h | — (leaf) |
| T-V3-C-41 | S-050 AI 社員チームと一緒に | — | NEW | 4h | — (leaf) |

### ops (2 task / 8h, REFACTOR 多め)

| ID | screen | feature | label | est | depends_on |
|---|---|---|---|---|---|
| T-V3-C-42 | S-040 コスト ダッシュボード | F-017 | REFACTOR | 4h | T-V3-B-017 |
| T-V3-C-43 | S-041 監査ログ | F-018 | REFACTOR | 4h | T-V3-B-018 |

### review (2 task / 8h)

| ID | screen | feature | label | est | depends_on |
|---|---|---|---|---|---|
| T-V3-C-44 | S-033 PR レビュー | F-013 | NEW | 4h | T-V3-B-013 |
| T-V3-C-45 | S-035 納品承認 | F-013 / F-015 | NEW | 4h | T-V3-B-013, T-V3-B-015 |

### spec (7 task / 28h)

| ID | screen | feature | label | est | depends_on |
|---|---|---|---|---|---|
| T-V3-C-46 | S-020 ヒアリングセッション | F-005 | NEW | 4h | T-V3-B-005 |
| T-V3-C-47 | S-021 要件エディタ | F-006 / F-025 | NEW | 4h | T-V3-B-006, T-V3-B-025 |
| T-V3-C-48 | S-022 仕様書ビューア | F-005 / F-015 | NEW | 4h | T-V3-B-005, T-V3-B-015 |
| T-V3-C-49 | S-023 画面モックビューア | F-005b | NEW | 4h | T-V3-B-005b |
| T-V3-C-50 | S-024 コンポーネントカタログ | F-005b | NEW | 4h | T-V3-B-005b |
| T-V3-C-51 | S-025 画面遷移マップ | F-005b | NEW | 4h | T-V3-B-005b |
| T-V3-C-52 | S-026 HTML エディタ | F-005b | NEW | 4h | T-V3-B-005b |

### system (4 task / 16h)

| ID | screen | feature | label | est | depends_on |
|---|---|---|---|---|---|
| T-V3-C-53 | S-044 404 Not Found | F-system | NEW | 4h | — (no API dep) |
| T-V3-C-54 | S-045 500 Server Error | F-system | NEW | 4h | — (no API dep) |
| T-V3-C-55 | S-046 403 Forbidden | — | NEW | 4h | — (leaf) |
| T-V3-C-56 | S-047 メンテナンス中 | — | NEW | 4h | — (leaf) |

### task (6 task — S-027 を 3 分割 / 26h)

| ID | screen | feature | label | est | depends_on |
|---|---|---|---|---|---|
| **T-V3-C-57-1** | **S-027 Kanban core** (accordion + columns + data fetch) | F-007 | NEW | 6h | T-V3-B-007 |
| **T-V3-C-57-2** | **S-027 Kanban drag&drop** (within-feature card move + optimistic update) | F-007 | NEW | 5h | T-V3-C-57-1, T-V3-B-007 |
| **T-V3-C-57-3** | **S-027 Kanban filter** (feature / status / assignee / text) | F-007 | NEW | 3h | T-V3-C-57-1, T-V3-B-007 |
| T-V3-C-58 | S-028 タスクリスト | F-007 | REFACTOR | 4h | T-V3-B-007 |
| T-V3-C-59 | S-029 タスク DAG | F-007 / F-009 | NEW | 4h | T-V3-B-007, T-V3-B-009 |
| T-V3-C-60 | S-030 タスク詳細 | F-006 / F-007 / F-025 | NEW | 4h | T-V3-B-006, T-V3-B-007, T-V3-B-025 |

### workspace (4 task / 16h)

| ID | screen | feature | label | est | depends_on |
|---|---|---|---|---|---|
| T-V3-C-61 | S-012 案件ダッシュボード (5 KPI critical) | F-006/007/008/026 | NEW | 4h | T-V3-B-006/007/008/026 |
| T-V3-C-62 | S-013 案件設定 | F-004 | NEW | 4h | T-V3-B-004 |
| T-V3-C-63 | S-014 案件メンバー | F-004 / F-021 | NEW | 4h | T-V3-B-004, T-V3-B-021 |
| T-V3-C-64 | S-015 メンバーを招待 | F-004 | NEW | 4h | T-V3-B-004 |

---

## file mutex / work_package_boundary 設計

各 task の `work_package_boundary.editable` は **自タスク専用 path のみ** (frontend/app/<screen-id>-<name>/* + lib/hooks/use-<name>.ts + lib/api/<name>.ts) で固定。これにより Wave 1 で 30 並列実行しても conflict は発生しない。

| 区分 | 内容 |
|---|---|
| editable | `frontend/app/<sid>-<sname>/page.tsx` / `page.test.tsx` / `lib/hooks/use-<sname>.ts` / `lib/api/<sname>.ts` |
| shared_no_concurrent_edit | `frontend/app/layout.tsx` / `frontend/lib/api/client.ts` (順番にアクセス、Wave 内同時編集は禁止) |
| readonly | 対応 mock HTML / screens.json / features.json / DESIGN.md |
| forbidden | `data/migrations/` / `backend/` (Group C は frontend のみ) |

### S-027 分割タスクの境界

- T-V3-C-57-1 (core) が `frontend/app/s-027-task-kanban/page.tsx` を **新規作成** し、`components/kanban/AccordionBoard.tsx` `Column.tsx` を新規。
- T-V3-C-57-2 (drag&drop) は **page.tsx を modify** で touch (mutex は core 完了後 sequential)。新規 component は `DraggableCard.tsx` / `DropZone.tsx`。
- T-V3-C-57-3 (filter) も **page.tsx を modify** で touch (drag&drop と排他)。新規 component は `FilterBar.tsx` / `FeatureToggle.tsx`。

⇒ depends_on で `core → {dnd, filter}` の DAG を表現。dnd と filter は core 完了後に並列 OK だが、同じ page.tsx を 2 並列で触れない (file mutex)。よって **dnd → filter の sequential 化** を推奨 (or filter を先で OK)。

---

## 3-tier AC 設計方針

### Tier 1 (Structural — UI 必須)

各 task で必ず以下を含む:
1. `<h1>` テキスト完全一致 (`STATE-DRIVEN: While ... shall display h1 with exact text "<mock h1>"`)
2. KPI labels 集合一致 (kpi_labels > 0 の screen のみ; S-012 = 8 KPI / S-040 = 4 KPI 等)
3. section h2 集合一致 (section_h2_texts > 0 の screen のみ)
4. Lucide icons 限定 / emoji 禁止 (`UBIQUITOUS: ... shall use Lucide icons exclusively`)

### Tier 2 (Functional — EARS 5 形式)

各 task で必ず以下を含む:
1. **EVENT-DRIVEN**: page mount 時の `related_apis[0]` 呼び出し + 4xx 時の error toast
2. **UNWANTED**: 未認証時の /login redirect (public 以外の screen)
3. features.json の `ears_ac_seed` から該当 feature の AC 1〜2 件を逐語コピー
4. **UNWANTED**: 403 → S-046 page 表示
5. (条件次第で) loading skeleton + role="status" aria-live="polite"

### Tier 3 (Regression — CI gate 逐語)

全 task 共通 7 gate (Build-Factory CI Gate 1〜8 のうち frontend 該当分):
- `pnpm test --filter=<screen-id>` coverage >= 70%
- `tsc --noEmit` 0 errors
- `pnpm run lint` (ESLint + design-token lint) 0 violations
- `bash scripts/lint-mock.sh` 12/12 OK
- `bash scripts/lint-mock-impl-diff.sh <screen-id>` Tier 1 diff = 0
- `python3 scripts/validate-tickets.py --check-file ...` for this task
- `bash scripts/audit-md-check.sh <task_id>` audit MD pre-flight 緑

---

## 依存 (depends_on)

- Foundation (Phase 0 / T-FOUNDATION-01〜08) は **既に Wave 0 で完了済**。tickets には明示的に書かないが各 Tier 3 gate が依存している。
- Group B-1 backend stub (`T-V3-B-<feature_num>`) を `depends_on` に記載。並列 Group B session が同 ID を採番してくれる前提 (cross-group integrator が ID 整合性をチェック)。
- 個別 task 内依存 (例: S-027 分割の core → {dnd, filter}) は同 JSON 内の task_id を参照。

---

## audit MD

全 30 task に対して `docs/audit/2026-05-16_v3/T-V3-C-NN.md` を **pre-flight 状態** (全 checklist unchecked) で配置済。

- ✅ Tier 1 / 2 / 3 の 3 section header すべて存在
- ✅ tickets の AC を逐語コピー (generic phrase は 0)
- ✅ `bash scripts/audit-md-check.sh T-V3-C-<NN>` 30/30 PASS (実行確認済)

着手時の手順 (IMPLEMENTATION_PROTOCOL Step 1):

```bash
# 該当 task の audit MD を読む
cat docs/audit/2026-05-16_v3/T-V3-C-37.md
# branch checkout
git checkout -b claude/T-V3-C-37
# 実装中に audit MD の impl: Lxx-Lyy を埋める
# 完了時に全 checkbox を [x] にし、実行ログを貼る
```

---

## 想定 Wave 構成

- **Wave 1** (Phase 1 開始): 30 task 全て並列可 (file mutex 守られている)。ただし以下 4 セットだけ sequential:
  - T-V3-C-57-1 → T-V3-C-57-2 (page.tsx mutex)
  - T-V3-C-57-1 → T-V3-C-57-3 (page.tsx mutex)
  - T-V3-C-57-2 と T-V3-C-57-3 は順序自由だが page.tsx mutex なので **sequential** 推奨

実質並列度: 28 (S-027 が 3 task chain) → 30-50 並列 capacity に収まる。

---

## 関連 file

- `tickets-group-c-ui-part2.json` (本 task の主成果物 / 30 task / v3 schema PASS)
- `_generate_part2.py` / `_generate_audit_mds.py` (再現用ジェネレータ)
- `docs/audit/2026-05-16_v3/T-V3-C-37.md` 〜 `T-V3-C-64.md` (audit MD 30 件)

---

最終更新: 2026-05-16
