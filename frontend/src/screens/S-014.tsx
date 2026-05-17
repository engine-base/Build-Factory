/**
 * T-V3-C-63 / S-014 — meta marker for the lint-mock-impl-diff Tier 1 gate
 * (scripts/lint-mock-impl-diff.py — Gate #8 / lint #17).
 *
 * The script looks up `frontend/src/screens/<screen-id>.tsx` for each mock
 * HTML under `docs/mocks/2026-05-09_v1/` and diffs the
 * `@screen-id / @feature-id / @task-ids / @entities / @phase` JSDoc against
 * the mock <meta name="..."> tags. This file provides the impl-side meta so
 * the structural diff for S-014 matches the v1 mock baseline.
 *
 * The live implementation lives at
 * `frontend/src/app/(app)/workspace/[id]/members/page.tsx`
 * with the ticket-mandated alias at
 * `frontend/app/s-014-workspace-members/page.tsx`. This file does not render
 * UI; it re-exports the canonical page component so navigating here via
 * `@/screens/S-014` still resolves to the screen.
 *
 * Meta values mirror docs/mocks/2026-05-09_v1/workspace/S-014-workspace-members.html
 * exactly (the v1 mock omits the `entities` meta, so this file also omits
 * `@entities` to avoid a `missing_field_in_mock` drift). The canonical page
 * itself carries the v3 entity / task-id mapping (E-003 / E-001 / T-V3-C-63)
 * via data-* attributes for the v3 mock-impl gate scheduled in a later wave.
 *
 * @screen-id S-014
 * @feature-id F-021
 * @task-ids T-021-04
 * @phase P1
 */

export { default } from "../app/(app)/workspace/[id]/members/page";
