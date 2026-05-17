/**
 * T-V3-C-51 / S-025 — Ticket-mandated path alias for the screen-flow-map
 * typed API client. The canonical implementation lives at
 * `frontend/src/api/screen-flow.ts` because the Build-Factory Next.js 15
 * project uses the `src/` root (see `frontend/tsconfig.json` `paths`:
 * `"@/*": ["./src/*"]`). This file exists only to satisfy
 * `tickets-group-c-ui-part2.json::files_changed[3]` and
 * `work_package_boundary.editable[3]`.
 *
 * Re-exports the canonical typed client so tooling that imports from this
 * path resolves the same module as the hook + page.
 */

export {
  getMockHtml,
  getScreenFlow,
  mockHtmlEndpoint,
  screenFlowEndpoint,
  ScreenFlowApiError,
  type MockHtmlResponse,
  type ScreenFlowClientOptions,
  type ScreenFlowEdge,
  type ScreenFlowNode,
  type ScreenFlowResponse,
} from "../../src/api/screen-flow";
