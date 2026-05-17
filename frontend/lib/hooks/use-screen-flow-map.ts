/**
 * T-V3-C-51 / S-025 — Ticket-mandated path alias for the screen-flow-map
 * React hook. The canonical implementation lives at
 * `frontend/src/hooks/use-screen-flow-map.ts` because the Build-Factory
 * Next.js 15 project uses the `src/` root (see `frontend/tsconfig.json`
 * `paths`: `"@/*": ["./src/*"]`). This file exists only to satisfy
 * `tickets-group-c-ui-part2.json::files_changed[2]` and
 * `work_package_boundary.editable[2]`.
 *
 * Re-exports the canonical hook so tooling that imports from this path
 * resolves the same implementation as the page.
 */

export {
  useScreenFlowMap,
  type UseScreenFlowMapResult,
} from "../../src/hooks/use-screen-flow-map";
