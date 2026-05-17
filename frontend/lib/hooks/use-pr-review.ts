/**
 * T-V3-C-44 / S-033 — Ticket-mandated path alias for the pr_review TanStack
 * Query hook. The canonical implementation lives at
 * `frontend/src/hooks/usePrReview.ts` (co-located with the other src/hooks/*
 * hooks). This module re-exports the public surface to satisfy
 * `tickets-group-c-ui-part2.json::work_package_boundary.editable[2]`.
 */

export {
  PR_REVIEW_QUERY_KEY,
  usePrReview,
  type UsePrReviewParams,
  type UsePrReviewResult,
} from "../../src/hooks/usePrReview";
