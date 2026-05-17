/**
 * T-V3-C-60 / S-030 — meta marker for the lint-mock-impl-diff Tier 1 gate
 * (scripts/lint-mock-impl-diff.py — Gate #8 / lint #17).
 *
 * The script looks up `frontend/src/screens/<screen-id>.tsx` for each mock
 * HTML under `docs/mocks/2026-05-09_v1/` and diffs the
 * `@screen-id / @feature-id / @task-ids / @entities / @phase` JSDoc against
 * the mock <meta name="..."> tags. This file provides the impl-side meta so
 * the structural diff for S-030 matches the v1 mock baseline.
 *
 * The live implementation lives at
 * `frontend/src/app/(app)/task/[id]/page.tsx`
 * with the ticket-mandated alias at
 * `frontend/app/s-030-task-detail/page.tsx`. This file does not render UI; it
 * re-exports the canonical page component so navigating here via
 * `@/screens/S-030` still resolves to the screen.
 *
 * Meta values mirror docs/mocks/2026-05-09_v1/task/S-030-task-detail.html
 * exactly. The canonical page itself carries the v3 entity / task-id mapping
 * (E-018,E-016,E-019,E-025 / T-V3-C-60) via data-* attributes for the v3
 * mock-impl gate scheduled in a later wave.
 *
 * @screen-id S-030
 * @feature-id F-006,F-010b
 * @task-ids T-010b-04
 * @entities tasks,acceptance_criteria,task_dependencies,sessions
 * @phase P1
 */

export { default } from "../app/(app)/task/[id]/page";
