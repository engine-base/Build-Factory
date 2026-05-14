# Pre-flight AC Audit — T-XXX-YY

- **Task**: T-XXX-YY (タイトル)
- **Sprint**: N / **Feature**: F-XXX / **Layer**: BE/FE/DB/TST
- **Label**: NEW / REUSE / REFACTOR / ARCHIVE
- **Spec link**: docs/task-decomposition/2026-05-09_v1/tickets.json#T-XXX-YY
- **ADR refs**: ADR-NNN
- **Status legend**: ⬜ PLANNED → 🟡 IMPL_DONE → 🟢 TEST_PASS → ✅ VERIFIED

---

## AC × 実装 × test × lint 対応表

### AC-1 UBIQUITOUS

> spec から逐語コピー (改変禁止):
> "The system shall ..."

| # | spec 中の sub-clause | impl (file:line) | test 関数名 | lint | status |
|---|---|---|---|---|---|
| 1.1 | (sub-clause 1) | `backend/.../foo.py:NN` | `test_ac1_xxx` | - | ⬜ |
| 1.2 | (sub-clause 2) | ... | ... | #N | ⬜ |

### AC-2 EVENT-DRIVEN

> "When [event], the system shall ..."

| # | spec 中の sub-clause | impl | test | lint | status |
|---|---|---|---|---|---|
| 2.1 | ... | ... | ... | - | ⬜ |

### AC-3 STATE-DRIVEN

> "While [state], the system shall ..."

| # | spec 中の sub-clause | impl | test | lint | status |
|---|---|---|---|---|---|
| 3.1 | ... | ... | ... | - | ⬜ |

### AC-4 UNWANTED

> "If [unwanted condition], the system shall ..."

| # | spec 中の sub-clause | impl | test | lint | status |
|---|---|---|---|---|---|
| 4.1 | ... | ... | ... | - | ⬜ |

---

## 補足項目 (タスク固有)

- **REUSE/REFACTOR 適合 9 項目** (REFACTOR 必須): 別表 or skip-with-reason
- **既存 module 不変** (REFACTOR 必須): G9 相当 test list
- **cross-module invariant** (該当時): cross-ref test list
- **lint guard** (UNWANTED 系で「lint shall fail」がある場合): check 番号
- **audit emit** (audit 必須の場合): event_type / detail schema

---

## 完了判定 (Step 6 / ADR-011)

- [ ] 全行 status = ✅ VERIFIED
- [ ] `bash scripts/pre-commit-check.sh` exit_code=0
- [ ] 関連 test suite 全 PASS (skip 数明記)
- [ ] PR description にこの audit doc へのリンク
- [ ] (post-merge) post-audit 1 周のみ実施
