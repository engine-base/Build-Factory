/**
 * T-V3-C-50 / S-024 — Ticket-mandated path alias for the component_catalog
 * typed API client. The canonical implementation lives at
 * `frontend/src/api/components.ts` (which co-locates with the other src/api/
 * clients), so this module re-exports the public surface to satisfy the
 * work_package_boundary path in tickets-group-c-ui-part2.json.
 */

export {
  ComponentsApiError,
  getComponentUsage,
  getComponents,
  workspaceComponentUsageEndpoint,
  workspaceComponentsEndpoint,
  type Component,
  type ComponentUsage,
  type ComponentsRequestOptions,
  type GetComponentUsageResponse,
  type GetComponentsResponse,
} from "../../src/api/components";
