/**
 * Build-Factory v3 API — TypeScript surface (thin wrapper)
 *
 * This file is a **hand-written re-export layer** that sits on top of the
 * machine-generated `openapi-typescript` output. The actual type generation
 * is performed by:
 *
 *   npx openapi-typescript \
 *     docs/api-design/2026-05-16_v3/openapi.yaml \
 *     -o frontend/src/api/openapi-generated.ts
 *
 * Steps once generated:
 *  1. Run the command above (Foundation phase / CI gate #7 verifies drift-free).
 *  2. Commit `frontend/src/api/openapi-generated.ts` (生成物 / 編集禁止).
 *  3. Import the named aliases below in application code.
 *
 * Why not generate this file directly?
 *  - The generator emits `paths` (per-endpoint contract) and `components`
 *    (entity schemas). Application code wants short, ergonomic names like
 *    `User`, `Workspace`, `LoginRequest`, `LoginResponse`. This file pins
 *    those names to the generator output so refactors of the generator
 *    config don't ripple through 100+ call sites.
 *
 * Status: 2026-05-16, v3 (140 endpoints / 35 features / 68 entities)
 * Profile: skills/api-design/references/profiles/build-factory.md
 */

// =============================================================================
// Generated module (placeholder import path)
// =============================================================================
// Generator output lives here. Run `openapi-typescript` to materialise.
import type { paths, components, operations } from "./openapi-generated";

export type { paths, components, operations };

// =============================================================================
// Convenience aliases — components.schemas.*
// =============================================================================
type Schemas = components["schemas"];

// Core entities (subset — full list = 68 entities)
export type User = Schemas["User"];
export type Account = Schemas["Account"];
export type AccountMember = Schemas["AccountMember"];
export type Workspace = Schemas["Workspace"];
export type WorkspaceMember = Schemas["WorkspaceMember"];
export type WorkspaceInvitation = Schemas["WorkspaceInvitation"];
export type AIEmployee = Schemas["AIEmployee"];
export type Skill = Schemas["Skill"];
export type SkillExecution = Schemas["SkillExecution"];
export type Task = Schemas["Task"];
export type TaskDependency = Schemas["TaskDependency"];
export type AcceptanceCriterion = Schemas["AcceptanceCriterion"];
export type Phase = Schemas["Phase"];
export type PhaseGate = Schemas["PhaseGate"];
export type Constitution = Schemas["Constitution"];
export type RedLine = Schemas["RedLine"];
export type RedLineViolation = Schemas["RedLineViolation"];
export type Artifact = Schemas["Artifact"];
export type ArtifactVersion = Schemas["ArtifactVersion"];
export type Screen = Schemas["Screen"];
export type Component = Schemas["Component"];
export type Session = Schemas["Session"];
export type SessionLog = Schemas["SessionLog"];
export type PR = Schemas["PR"];
export type PRReview = Schemas["PRReview"];
export type LLMProvider = Schemas["LLMProvider"];
export type APIKey = Schemas["APIKey"];
export type AuditLog = Schemas["AuditLog"];
export type Notification = Schemas["Notification"];
export type CostLog = Schemas["CostLog"];
export type ChatThread = Schemas["ChatThread"];
export type ChatMessage = Schemas["ChatMessage"];
export type AuthSession = Schemas["AuthSession"];
export type OAuthConnection = Schemas["OAuthConnection"];
export type User2FASecret = Schemas["User2FASecret"];

// Loose nested types referenced from outputs_2xx
export type AIEmployeeNode = Schemas["AIEmployeeNode"];
export type DAGEdge = Schemas["DAGEdge"];
export type TaskNode = Schemas["TaskNode"];
export type Spec = Schemas["Spec"];
export type RequirementItem = Schemas["RequirementItem"];
export type ScreenFlowNode = Schemas["ScreenFlowNode"];
export type ScreenFlowEdge = Schemas["ScreenFlowEdge"];
export type ComponentUsage = Schemas["ComponentUsage"];
export type PublicComment = Schemas["PublicComment"];
export type PublicWorkspaceView = Schemas["PublicWorkspaceView"];
export type Delivery = Schemas["Delivery"];
export type Export = Schemas["Export"];
export type Report = Schemas["Report"];
export type KnowledgeItem = Schemas["KnowledgeItem"];
export type KnowledgeHit = Schemas["KnowledgeHit"];
export type ApiToken = Schemas["ApiToken"];
export type McpToken = Schemas["McpToken"];
export type EmailTemplate = Schemas["EmailTemplate"];
export type DesignToken = Schemas["DesignToken"];
export type SearchHit = Schemas["SearchHit"];
export type UserSettings = Schemas["UserSettings"];
export type WorkspaceSummary = Schemas["WorkspaceSummary"];
export type ReviewTurn = Schemas["ReviewTurn"];
export type TaskGroup = Schemas["TaskGroup"];

// Error envelope (every 4xx / 5xx response shape)
export type ErrorBody = Schemas["ErrorBody"];

// EARS criterion (used by F-006 / F-025)
export type EARSCriterion = Schemas["EARSCriterion"];

// =============================================================================
// Request / response helpers — path-based extraction
// =============================================================================

/**
 * Extract the JSON request body of an endpoint by `paths` key + method.
 *
 * Example:
 *   type LoginReq = RequestBody<"/api/auth/login", "post">;
 *   //   ^? { email: string; password: string; mfa_code?: string }
 */
export type RequestBody<
  Path extends keyof paths,
  Method extends keyof paths[Path],
> = paths[Path][Method] extends {
  requestBody?: { content: { "application/json": infer Body } };
}
  ? Body
  : never;

/**
 * Extract the 2xx response body of an endpoint by `paths` key + method.
 * Falls back to 200 / 201 success.
 *
 * Example:
 *   type LoginRes = SuccessResponse<"/api/auth/login", "post">;
 *   //   ^? { access_token: string; refresh_token: string; user_id: string; mfa_required: boolean }
 */
export type SuccessResponse<
  Path extends keyof paths,
  Method extends keyof paths[Path],
> = paths[Path][Method] extends {
  responses: { 200: { content: { "application/json": infer Body } } };
}
  ? Body
  : paths[Path][Method] extends {
        responses: { 201: { content: { "application/json": infer Body } } };
      }
    ? Body
    : never;

/**
 * Extract path parameters for an endpoint.
 *
 * Example:
 *   type Params = PathParams<"/api/tasks/{id}", "get">;
 *   //   ^? { id: string }
 */
export type PathParams<
  Path extends keyof paths,
  Method extends keyof paths[Path],
> = paths[Path][Method] extends { parameters: { path: infer P } } ? P : never;

/**
 * Extract query parameters for an endpoint.
 */
export type QueryParams<
  Path extends keyof paths,
  Method extends keyof paths[Path],
> = paths[Path][Method] extends { parameters: { query?: infer Q } } ? Q : never;

// =============================================================================
// Auth role enum — mirrors x-bf-auth-role across all 140 ops
// =============================================================================
export type AuthRole =
  | "public"
  | "authenticated"
  | "member"
  | "workspace_admin"
  | "account_owner";

// =============================================================================
// API client helper interface (typed fetch wrapper)
// =============================================================================
//
// Application code should implement a TanStack-Query-aware wrapper:
//
//   import { paths } from "./types";
//   import createClient from "openapi-fetch";
//   const apiClient = createClient<paths>({ baseUrl: "/api" });
//
// or with a custom fetch:
//
//   async function api<P extends keyof paths, M extends keyof paths[P]>(
//     path: P,
//     method: M,
//     opts: { body?: RequestBody<P, M>; params?: PathParams<P, M> & QueryParams<P, M> },
//   ): Promise<SuccessResponse<P, M>>
//
// See `frontend/src/api/client.ts` for the canonical implementation (Phase 1.5).
