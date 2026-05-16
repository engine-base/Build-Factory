# CI Gate 構成 (v3)

> task-decomposition スキルが各タスクを done と判定する際の **8 ゲート**
> source of truth: `docs/task-decomposition/2026-05-15_v3/DEPENDENCIES.md` + `scripts/lint-mock.sh`

## 8 つの merge gate

各 PR は以下 8 ゲート **全 pass** したときのみ main にマージできる。1 つでも fail → auto-merge 不可。

| # | Gate | script / command | 検出する漏れ |
|---|---|---|---|
| 1 | mock lint (1-19) | `bash scripts/lint-mock.sh` | 絵文字 / AGPL / ARCHIVE / tickets メタ / secrets / langgraph / litellm-in-runner / domain-boundaries / self-provider-routing / self-tool-trim / template-skeleton / self-constitution-inject / mock-impl diff / screens-API / entity-table naming |
| 2 | 3-tier AC validator | `python3 scripts/validate-ears-ac.py docs/task-decomposition/2026-05-15_v3/tickets.json` | AC が 3-tier に分かれてないタスク / EARS 形式違反 |
| 3 | audit MD validator | `python3 scripts/validate-audit-md.py docs/audit/2026-05-15_v3/${TASK_ID}.md` | audit MD 不在 / generic 文言 / 3-tier 欠落 / impl 行範囲未記入 |
| 4 | RLS coverage | `python3 scripts/verify-rls-coverage.py` | entities.json の entity に対する RLS policy 不在 |
| 5 | pytest + coverage | `pytest --cov --cov-fail-under=70` | unit test 失敗 / カバレッジ < 70% |
| 6 | pyright strict | `pyright --strict` | Python 型エラー |
| 7 | TypeScript strict | `cd frontend && tsc --noEmit && pnpm run lint` | TS 型エラー / ESLint 違反 |
| 8 | mock-impl diff (structural AC nonempty 時のみ) | `bash scripts/lint-mock-impl-diff.sh ${SCREEN_IDS}` | mock h1 / KPI / section-h2 と impl の不一致 |

## 漏れ → gate の対応表

| 漏れの種類 | 検出 gate |
|---|---|
| 仕様 AC が満たされていない | #2 (3-tier AC validator: functional 必須) |
| Mock と画面が違う (drift) | #8 (mock-impl diff) |
| Spec API が backend に無い | #1 (lint #18 screens-API) |
| Entity 名前ドリフト / `bf_` 残留 | #1 (lint #19 entity-table naming) |
| RLS policy 不足 | #4 (RLS coverage) |
| audit MD が generic / 不在 | #3 (audit MD validator) |
| coverage < 70% | #5 (pytest --cov-fail-under=70) |
| Python 型エラー | #6 (pyright --strict) |
| TS 型エラー / ESLint | #7 |

**全 8 gate を merge gate にして、ひとつでも fail なら merge できない** → 漏れ構造的に発生不可能。

## task-decomposition スキルが生成すべき内容

各タスクが上記 8 gate を pass するためのチェック項目を、`acceptance_criteria.regression` 配列に **逐語的に書く**。

例:
```json
"regression": [
  "The system shall pass bash scripts/lint-mock.sh (19/19 OK).",
  "The system shall pass python3 scripts/validate-ears-ac.py for this task ID.",
  "The system shall pass python3 scripts/validate-audit-md.py docs/audit/2026-05-15_v3/T-V3-AUTH-01.md.",
  "The system shall pass python3 scripts/verify-rls-coverage.py for entities E-001, E-038.",
  "The system shall pass pytest backend/tests/test_T-V3-AUTH-01.py with coverage >= 70%.",
  "The system shall pass pyright --strict with 0 errors on touched .py files.",
  "The system shall pass cd frontend && tsc --noEmit && pnpm run lint.",
  "The system shall pass bash scripts/lint-mock-impl-diff.sh S-001."
]
```

`pytest test PASS` だけ書いて満足するのは v1 の失敗パターン。v3 は **8 gate 全項目を逐語的に regression AC として書く** ことで漏れを防ぐ。

## CI workflow テンプレート

```yaml
# .github/workflows/v3-gate.yml
on:
  pull_request:
    branches: [main]

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with: { python-version: '3.13' }
      - name: Install deps
        run: uv sync
      - name: Gate 1 — mock lint
        run: bash scripts/lint-mock.sh
      - name: Gate 2 — 3-tier AC validator
        run: python3 scripts/validate-ears-ac.py docs/task-decomposition/2026-05-15_v3/tickets.json
      - name: Gate 3 — audit MD validator
        run: |
          for f in docs/audit/2026-05-15_v3/T-V3-*.md; do
            python3 scripts/validate-audit-md.py "$f"
          done
      - name: Gate 4 — RLS coverage
        run: python3 scripts/verify-rls-coverage.py
      - name: Gate 5 — pytest + coverage
        run: pytest --cov --cov-fail-under=70
      - name: Gate 6 — pyright strict
        run: pyright --strict
      - name: Gate 7 — TS strict
        run: cd frontend && pnpm install --frozen-lockfile && tsc --noEmit && pnpm run lint
      - name: Gate 8 — mock-impl diff
        if: contains(github.event.pull_request.labels.*.name, 'has-frontend')
        run: |
          # extract screen_ids from PR description or task tickets.json
          bash scripts/lint-mock-impl-diff.sh ${SCREEN_IDS}
```

## 失敗時の retry プロトコル

各 task が gate 落ちた場合:
1. CI が PR コメントに失敗内容貼る
2. session orchestrator が同じ task の retry session を起動
3. 3 回連続失敗 → human エスカレーション

task-decomposition スキルは各タスクに `risk_flags` を付け、retry が想定される (依存 API 未完成 / 仕様曖昧) タスクに事前マークする。
