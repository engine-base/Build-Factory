/**
 * T-V3-C-50 / S-024 — Ticket-mandated path alias for the component_catalog
 * TanStack Query hook. The canonical implementation lives at
 * `frontend/src/hooks/useComponentCatalog.ts` (co-located with other src/hooks
 * hooks), so this module re-exports the public surface to satisfy the
 * work_package_boundary path in tickets-group-c-ui-part2.json.
 */

export {
  COMPONENTS_QUERY_KEY,
  COMPONENT_USAGE_QUERY_KEY,
  useComponentCatalog,
  type UseComponentCatalogArgs,
  type UseComponentCatalogResult,
} from "../../src/hooks/useComponentCatalog";
