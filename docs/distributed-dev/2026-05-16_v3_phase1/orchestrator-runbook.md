# Orchestrator Runbook — Phase 1 distributed-dev (v3)

> Audience: orchestrator (Build-Factory v3 Phase 1 swarm manager).
> Inputs: `.claude/branches/T-V3-*.json` (100 files) + `.claude/branches/_index.json`.
> Outputs: 100 Claude Code sessions (one per task) executed across 6 Waves (W1-W6).
> Profile: `skills/distributed-dev/references/profiles/build-factory.md` (parallel capacity 30-50 / 8 CI gate).

## 0. Pre-flight check (run once before W1)

```bash
# 1. Verify branch-package count
test "$(ls .claude/branches/T-V3-*.json | wc -l)" -eq 100 || exit 1

# 2. Verify _index.json sanity
python3 - <<'PY'
import json, pathlib
idx = json.loads(pathlib.Path('.claude/branches/_index.json').read_text())
assert idx['total_tasks'] == 100
assert sum(idx['by_wave'].values()) == 100
assert sum(idx['by_group'].values()) == 100
print('index OK')
PY

# 3. Verify Phase 1 tickets exist (generator stub assumes they will)
for f in tickets-group-b-backend.json tickets-group-c-ui-part1.json \
         tickets-group-c-ui-part2.json tickets-group-d-drift.json; do
  test -f "docs/task-decomposition/2026-05-16_v3_phase1/${f}" || \
    echo "WARN missing: ${f}"
done

# 4. Verify audit MDs are seeded (pre-flight audit MD is required by Gate #4)
for tid in $(jq -r '.tasks[]' .claude/branches/_index.json); do
  test -f "docs/audit/2026-05-16_v3/${tid}.md" || \
    echo "TODO seed audit MD: ${tid}"
done

# 5. Foundation gate green? (Phase 0 must be complete)
bash scripts/audit-md-check.sh --all || exit 1
```

## 1. Wave execution loop

```text
for wave in W1 W2 W3 W4 W5 W6:
    tasks = filter(.claude/branches/T-V3-*.json where wave == $wave)
    schedule(tasks, parallel_session_count = min(len(tasks), 50))
    wait_until_all_complete(tasks)
    aggregate_summary(wave)
    if any task.final_state == "escalated":
        human_review_block()
        resume_or_abort()
```

## 2. Per-task session bootstrap

For each `T-V3-XX-NN.json`:

```bash
TASK_ID="T-V3-B-01"           # example
PKG=".claude/branches/${TASK_ID}.json"
BRANCH=$(jq -r .branch "$PKG")
AUDIT=$(jq -r .audit_md_path "$PKG")

# 1. Create worktree (isolation: worktree)
git worktree add ".claude/worktrees/${TASK_ID}" -b "$BRANCH" origin/main

# 2. Seed pre-flight audit MD if missing
if [ ! -f "$AUDIT" ]; then
  cp docs/audit/2026-05-13_v2/_template.md "$AUDIT"
fi

# 3. Wave mutex check (file-level; v3-core lint #16)
python3 scripts/check-wave-mutex.py --task "$TASK_ID"

# 4. Spawn Claude Code session inside the worktree
#    - subagent_type:  general-purpose
#    - model:          sonnet (per session_meta.model_preference)
#    - required_reads: from $PKG.session_meta.required_reads
claude code --worktree ".claude/worktrees/${TASK_ID}" \
            --branch-package "$PKG"
```

The session reads `$PKG.session_meta.required_reads` in order and starts from the pre-flight audit MD.

## 3. Done-criteria & auto-merge (Gate #1-#8)

When the session reports done, the orchestrator runs the 8 BF CI gates (see profile):

```bash
TASK_ID="$1"
PKG=".claude/branches/${TASK_ID}.json"

# Gate 1: lint-mock (19 check)
bash scripts/lint-mock.sh

# Gate 2: AC validator
python3 scripts/validate-tickets.py

# Gate 3: RLS coverage
python3 scripts/verify-rls-coverage.py

# Gate 4: audit MD existence + content
bash scripts/audit-md-check.sh "$TASK_ID"

# Gate 5: pytest cov >= 70%
(cd backend && pytest --cov --cov-fail-under=70)

# Gate 6: pyright strict
(cd backend && pyright)

# Gate 7: tsc strict (UI / drift tasks)
(cd frontend && pnpm tsc --noEmit)

# Gate 8: mock-impl-diff
python3 scripts/lint-mock-impl-diff.py

# Boundary check (lint #16)
python3 scripts/check-work-package-boundary.py --task "$TASK_ID"
```

All 8 green → push branch → open PR → auto-merge to main → set `final_state = "auto-merged"`.

## 4. Failure handling (consecutive_failure_threshold = 3)

```text
on gate failure:
    failure_count++
    update branch-package.json: failure_count
    if failure_count < 3:
        final_state = "retried"
        retry_with_fix(session)
    else:
        final_state = "escalated"
        human_review_queue.push(TASK_ID)
        block_dependent_tasks(TASK_ID)
```

`rolled_back` is used when an already-merged PR is reverted (e.g., breaks W6 drift fix).

## 5. Wave dependency graph

```
W1 (21 backend, independent)
  ↓
W2 (8 backend, deps on W1)
  ↓
W3 (1 backend, deps on W2)
  ↓
W4 (25 UI part1, deps on specific backend tasks)
  ↓
W5 (30 UI part2, deps on specific backend tasks)
  ↓
W6 (15 drift fix, deps on W4+W5 settling)
```

Each UI task lists its dependent backend task in `depends_on`. The orchestrator must verify all `depends_on` task_ids have `final_state == "auto-merged"` before starting the dependent task.

## 6. State transitions (final_state)

| from      | to            | trigger                                       |
|-----------|---------------|-----------------------------------------------|
| pending   | retried       | gate failure with failure_count < 3           |
| retried   | retried       | further failure with failure_count < 3        |
| retried   | auto-merged   | all 8 gates green after retry                 |
| retried   | escalated     | failure_count >= 3                            |
| pending   | auto-merged   | all 8 gates green on first try                |
| pending   | escalated     | unrecoverable error (e.g., environment fail)  |
| auto-merged | rolled_back | downstream PR reverts this change             |

## 7. Wave completion summary template

After each Wave:

```json
{
  "wave": "W1",
  "completed_at": "2026-05-16T18:00:00Z",
  "totals": {"auto-merged": 19, "retried": 1, "escalated": 1, "rolled_back": 0},
  "drift_detected_count": 3,
  "next_wave_unblocked": true
}
```

## 8. Re-generation

If `docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-*.json` are committed
later with shape changes, regenerate the 100 branch-package.json files:

```bash
python3 scripts/_generate_branch_packages.py
git diff .claude/branches/ docs/distributed-dev/2026-05-16_v3_phase1/
```

The generator is idempotent — output diffs only on input change.

## 9. References

- `skills/distributed-dev/references/v3-core.md` — 3-tier AC, mutex, CLAUDE.md schema
- `skills/distributed-dev/references/profiles/build-factory.md` — BF specifics (gate list, paths)
- `docs/task-decomposition/2026-05-16_v3_phase0/` — Phase 0 foundation (CI gates this Phase 1 consumes)
- `scripts/_generate_branch_packages.py` — source of truth for the 100 packages
- `.claude/branches/_index.json` — wave / group totals + ordered task list
