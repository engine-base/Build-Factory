# Build-Factory 主要 API インターフェース定義 v1.0

distributed-dev で Claude Code に渡す前提・全 API のフォーマット契約。

## 共通エラーレスポンス

```ts
ErrorResponse: {
  code: 'INSUFFICIENT_PERMISSION' | 'RLS_VIOLATION' | 'VALIDATION_ERROR' |
        'CIRCULAR_DEPENDENCY' | 'RED_LINE_BLOCKED' | 'PROVIDER_ERROR' | ...
  message: string
  details?: object
  trace_id?: string  // Langfuse + Sentry
}
```

## 認証・認可レイヤー（全 API 共通）

```
Request → Supabase Auth JWT 検証 (T-S0-08)
       → RLS context 設定 (T-S0-09・workspace_members 経由)
       → permission middleware (T-021-03)
       → 赤線リスト middleware (T-012-02)
       → ハンドラー
       → audit_logs trigger (T-018-01)
```

---

## 1. 認証・テナント

### POST /api/accounts
- Request: `{ name, type: 'company'|'individual', plan: 'free'|'pro'|'team' }`
- Response: `{ id, name, type, plan, owner_user_id, created_at }`
- 機能: F-004 / 権限: 認証済ユーザ

### POST /api/workspaces
- Request: `{ account_id, name, slug, project_meta?, is_confidential? }`
- Response: `{ id, account_id, name, slug, ... }`
- 機能: F-004 / 権限: account_owner

### POST /api/workspaces/{id}/invitations
- Request: `{ email, role, custom_permissions?, visible_tabs?, expires_in_days? }`
- Response: `{ id, token, expires_at, invitation_url }`
- 機能: F-004 / 権限: invite_member or invite_client

### PATCH /api/workspace_members/{id}/permissions
- Request: `{ custom_permissions, visible_tabs? }`
- Response: `{ ...workspace_member }`
- 機能: F-021 / 権限: change_role + 自己権限剥奪 block

### POST /api/profile/clone-opt-in
- Request: `{ opt_in: bool }`
- Response: `{ ok, deleted_log_count?: int }`
- 機能: F-022 / 効果: false 時、user_interaction_log 全削除

---

## 2. AI 社員 / Runtime

### POST /api/agents/invoke
- Request:
  ```ts
  {
    employee_id: uuid,
    intent_hint?: string,
    user_message: string,
    thread_id?: uuid,
    context_overrides?: { skills?: uuid[], tier_strategy?: string }
  }
  ```
- Response (streaming): `{ trace_id, thread_id, sender, content_chunk, final?, artifact_ids? }`
- 機能: F-003 / M-27 / M-28 / M-30 / 権限: run_session

### POST /api/runtime/intent-route （内部）
- Request: `{ message, thread_id?, workspace_id }`
- Response: `{ intent, target_employee_id }`
- 機能: M-27

### POST /api/runtime/context-build （内部）
- Request: `{ thread_id, target_agent_id, current_query }`
- Response:
  ```ts
  {
    cached_system: string,         // cache_control: ephemeral 5min
    recent_full: ChatMessage[],     // 直近 N=20
    structured_summary: NineSectionSummary,
    retrieved_long_term: KnowledgeSnippet[],
    workspace_context: object,
    rules: ConstitutionMd,
    tool_history: ToolResultSummary[]
  }
  ```
- 機能: M-28

### GET /api/agents/org-chart?account_id=...
- Response: `{ nodes: AIEmployee[], edges: { parent_id, child_id }[] }`
- 機能: F-022 / 権限: manage_ai_employees

---

## 3. タスク・フェーズ・依存

### POST /api/tasks
- Request:
  ```ts
  {
    workspace_id, phase_id, title, description,
    assigned_employee_id?, screen_id?,
    acceptance_criteria: { ears_type, trigger, response, condition? }[],
    dependencies?: { parent_task_id, type }[]
  }
  ```
- Response: `{ ...task, embedding, tsv }`
- 機能: F-006 / 権限: edit_task

### POST /api/dependencies
- Request: `{ parent_task_id, child_task_id, type: 'blocks'|'related'|'subtask_of' }`
- Response: `{ ...dependency }`
- エラー: 422 (循環依存 trigger 検出)
- 機能: F-009 / 権限: edit_dependency

### GET /api/dependencies/impact?task_id=...
- Response: `{ affected_tasks: { task_id, impact_reason, suggested_action }[] }`
- 機能: F-009 影響分析 / M-28 Context Builder 連携

### GET /api/phases/{workspace_id}/gantt
- Response: `{ phases: Phase[], gates: PhaseGate[] }`
- 機能: F-008

### POST /api/phase-gates/{id}/approve
- Request: `{ approver_id }`
- Response: `{ ...gate, status: 'passed' }`
- 機能: F-008 / 効果: 次 phase auto unlock

---

## 4. MCP サーバー（F-010a・5 ツール）

stdio + HTTP transport via Anthropic MCP Python SDK・workspace scope token 認証

### bf_get_spec(task_id)
```python
Returns: {
  task: Task,
  acceptance_criteria: AC[],     # EARS notation
  related_screen?: Screen,
  related_artifacts: Artifact[],
  constitution: ConstitutionSnapshot,
  knowledge_snippets: KnowledgeSnippet[]
}
```

### bf_post_progress(task_id, status, message, tokens?)
```python
Returns: { ok: bool }
```

### bf_attach_artifact(task_id, artifact)
```python
artifact: { type, format, content_or_url, title }
Returns: { artifact_id }
```

### bf_request_review(task_id, generator_output, evaluator_result)
```python
Returns: { review_id }
```

### bf_get_review_feedback(review_id)
```python
Returns: {
  status: 'pass' | 'fail' | 'pending',
  feedback?: string,
  turn_count: int,
  escalated: bool
}
```

---

## 5. セッション・スポナー / WebSocket

### POST /api/sessions/spawn
- Request: `{ task_id, oauth_token_id, parallel_priority?: 1-10 }`
- Response: `{ session_id, ws_channel, status: 'starting' }`
- 機能: F-010b / 権限: run_session

### POST /api/sessions/play-all
- Request: `{ task_ids: uuid[] }`
- Response: `{ spawned: { task_id, session_id, queued?: bool }[] }`
- 機能: F-010c / 権限: run_parallel_swarm

### WS ws://api/sessions/{id}/stream
- ServerEvents:
  ```ts
  {
    type: 'stdout'|'stderr'|'status_change'|'tool_call'|'tool_result'|'crash'|'token_update',
    timestamp, content, metadata?
  }
  ```
- ClientCommands: `{ type: 'pause'|'resume'|'kill'|'rerun_from_checkpoint'|'manual_fix' }`
- 機能: F-010d

### POST /api/sessions/{id}/resume
- Request: `{ mode: 'from_checkpoint'|'rerun_full'|'cancel'|'manual_fix', manual_diff? }`
- Response: `{ session_id, status }`
- 機能: F-010c crash detection + resume

### GET /api/sessions/swarm?workspace_id=...&max=16
- Response: `{ sessions: Session[], queue_size: int, parallel_limit: int }`
- 機能: F-010d swarm grid

---

## 6. レビュー・承認・安全

### POST /api/reviews
- Request: `{ task_id, generator_output, evaluator_result }`
- Response: `{ review_id, turn: 1, status: 'pending' }`
- 機能: F-011 / 権限: approve_pr or AI 内部呼出

### POST /api/red-line-violations/{id}/approve
- Request: `{ reason, mark_false_positive? }`
- Response: `{ ...violation, status: 'approved' }`
- 機能: F-012 / 権限: approve_red_line

### PATCH /api/constitutions/{workspace_id}
- Request: `{ content_md, version }`
- Response: `{ ...constitution, is_current: true }`
- 機能: F-026 / 権限: manage_red_lines

### POST /api/delivery/{task_id}/approve
- Request: `{ approver_id, comment? }`
- Response: `{ delivery_id, status: 'approved' }`
- 機能: F-011 / 権限: approve_delivery

---

## 7. 仕様化・モック・ヒアリング

### POST /api/hearing/start
- Request: `{ workspace_id, project_seed? }`
- Response: `{ thread_id, current_step: 1 }`
- 機能: F-005

### POST /api/hearing/{thread_id}/advance
- Request: `{ step_responses }`
- Response: `{ thread_id, current_step, artifact_id?, completed?: bool }`
- 機能: F-005

### POST /api/specs/generate
- Request: `{ workspace_id, hearing_thread_id }`
- Response: `{ spec_artifact_id, html_url }`
- 機能: F-005

### POST /api/mocks/generate
- Request: `{ workspace_id, screen_ids: uuid[], design_tokens? }`
- Response: `{ mock_artifact_ids: uuid[], catalog_artifact_id, flow_map_artifact_id }`
- 機能: F-005b / M-5b

### POST /api/acceptance-criteria/parse-ears
- Request: `{ raw_text }`
- Response: `{ ears_type, trigger, response, condition?, suggestions?: string[] }`
- 機能: F-025

---

## 8. 検索・観測

### POST /api/search
- Request: `{ query, scope?: 'workspace'|'account', categories?: string[] }`
- Response: `{ results: { category, items: SearchResult[] }[], total }`
- 機能: F-024（FTS + pgvector + pg_trgm hybrid）

### GET /api/cost/dashboard?tab=daily|monthly|by_provider|by_model|by_user|by_workspace|by_session|alerts
- Response: `{ tab, data: ChartData }`
- 機能: F-017 / 権限: view_costs

### GET /api/audit-logs?filter=...
- Response: `{ logs: AuditLog[], total, next_cursor? }`
- 機能: F-018 / 権限: view_audit_log

### POST /api/audit-logs/export?format=csv|json
- Response: ファイルダウンロード
- 機能: F-018 / 権限: export_data

---

## 9. 連携

### POST /api/integrations/github/connect
- Request: `{ workspace_id, oauth_code }`
- Response: `{ repo_url_options: string[] }`
- 機能: F-013

### POST /api/integrations/github/select-repo
- Request: `{ workspace_id, repo_url, default_branch? }`
- Response: `{ ok }`
- 機能: F-013

### POST /api/integrations/slack/webhook
- Request: `{ workspace_id, webhook_url, default_channel }`
- Response: `{ ok, encrypted_id }`
- 機能: F-014

### POST /api/integrations/obsidian/configure
- Request: `{ workspace_id, vault_path, sync_mode, frequency, storage_backend }`
- Response: `{ ok, last_synced_at }`
- 機能: F-016

### POST /api/integrations/obsidian/export-now
- Request: `{ workspace_id }`
- Response: `{ exported_count, last_synced_at }`
- 機能: F-016

---

## 10. 課金・プラン（Phase 3）

### GET /api/billing/usage
- Response: `{ workspace_id, current_period_cost, limit, threshold_state }`
- 機能: F-017 / 権限: view_costs

### POST /api/billing/limits
- Request: `{ workspace_id, amount, currency, threshold_warn?, threshold_fallback?, threshold_stop? }`
- Response: `{ ...token_limits }`
- 機能: F-017 / 権限: set_token_limits

---

## ステータスコード規約

| Code | 用途 |
|---|---|
| 200 | 成功 |
| 201 | 作成成功 |
| 204 | 成功（body なし） |
| 400 | バリデーションエラー |
| 401 | 未認証 |
| 403 | 権限なし（RLS or permission middleware） |
| 404 | リソースなし |
| 409 | 競合（duplicate / circular dependency） |
| 422 | ビジネスルール違反（red line / constitution / opt-in trigger） |
| 429 | レート制限超過 |
| 500 | サーバエラー |

## レート制限

- API（per user）: 1000 req / 5min
- API（per IP・Cloudflare）: 10000 req / 5min
- LLM 呼出（per workspace）: token_limits の amount に従う
- MCP セッション: workspace ごと 5 並列・circuit breaker

## 認証ヘッダー

```
Authorization: Bearer <supabase_jwt>
X-MCP-Token: <mcp_scope_token>  # MCP 呼出時のみ
```
