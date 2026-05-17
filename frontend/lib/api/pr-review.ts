/**
 * T-V3-C-44 / S-033 — Ticket-mandated path alias for the pr_review typed API
 * client. The canonical implementation lives at
 * `frontend/src/api/pr-review.ts` (co-located with the other src/api/* clients,
 * resolvable via the `@/api/pr-review` TS path alias). This module re-exports
 * the public surface to satisfy
 * `tickets-group-c-ui-part2.json::work_package_boundary.editable[3]`.
 */

export {
  PR_GET_ENDPOINT_PATTERN,
  PR_APPROVE_ENDPOINT_PATTERN,
  PR_COMMENTS_ENDPOINT_PATTERN,
  PR_MERGE_ENDPOINT_PATTERN,
  PrReviewApiError,
  approvePr,
  getWorkspacePr,
  mergePr,
  postPrComment,
  prApproveEndpoint,
  prCommentsEndpoint,
  prMergeEndpoint,
  workspacePrEndpoint,
  type ApprovePrRequest,
  type ApprovePrResponse,
  type MergePrRequest,
  type MergePrResponse,
  type PostPrCommentRequest,
  type PostPrCommentResponse,
  type PrComment,
  type PrFileChange,
  type PrMergeMethod,
  type PrReviewRequestOptions,
  type PullRequestView,
  type WorkspacePrResponse,
} from "../../src/api/pr-review";
