# Phase 1A Group B (Backend) Task Cards

> Generated: 2026-05-16 / source: features.json + api-drift-summary.md / total tasks: 30 / total endpoints covered: 94

## T-V3-B-01: Backend: Auth backend (login/signup/password-reset) (F-001)

- **feature**: F-001 / **screens**: S-001 login, S-002 signup, S-003 password_reset, S-004 mfa_setup, S-005 oauth_callback
- **entities**: E-002 User, E-005 Session, E-006 ApiKey
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 4.9h / 2 session(s)
- **endpoint paths** (3):
  - `POST /api/auth/login`
  - `POST /api/auth/signup`
  - `POST /api/auth/password-reset`
- **branch**: `claude/T-V3-B-01` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-01.md`

### files_changed
- backend/app/routers/auth.py (modify)
- backend/app/services/auth.py (modify)
- backend/app/schemas/auth.py (modify)
- backend/tests/routers/test_auth.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When valid email/password is submitted to POST /api/auth/login, the system shall return 200 with access_token + refresh_token + user_id.
- UNWANTED: If invalid credentials are submitted to POST /api/auth/login, the system shall return 401 with a generic message (no user enumeration).
- EVENT-DRIVEN: When POST /api/auth/password-reset is called with an email, the system shall always return 2xx (no account enumeration) and send reset email only if the account exists.
- EVENT-DRIVEN: When POST /api/auth/login is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-001 (incl. access_token).
- UNWANTED: If POST /api/auth/login is called without a valid auth token, the system shall return 401.
- (+8 more — see tickets.json)

### access_policies_required
- users:user_own_select
- sessions:user_own_select
- api_keys:user_own_select

---

## T-V3-B-02: Backend: Auth backend (MFA + OAuth callback) (F-001)

- **feature**: F-001 / **screens**: S-001 login, S-002 signup, S-003 password_reset, S-004 mfa_setup, S-005 oauth_callback
- **entities**: E-002 User, E-005 Session, E-006 ApiKey
- **wave**: 2 / **group**: B / **deliverable**: backend
- **estimate**: 4.9h / 2 session(s)
- **endpoint paths** (3):
  - `POST /api/auth/mfa/enroll`
  - `POST /api/auth/mfa/verify`
  - `GET /api/auth/oauth/{provider}/callback`
- **branch**: `claude/T-V3-B-02` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-02.md`

### files_changed
- backend/app/routers/auth.py (modify)
- backend/app/services/auth.py (modify)
- backend/app/schemas/auth.py (modify)
- backend/tests/routers/test_auth.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- STATE-DRIVEN: While MFA is enabled for the user, the system shall require POST /api/auth/mfa/verify with a valid TOTP code before issuing access_token.
- EVENT-DRIVEN: When OAuth callback GET /api/auth/oauth/{provider}/callback is invoked with a valid state token, the system shall complete the OAuth handshake and return access_token + refresh_token.
- EVENT-DRIVEN: When POST /api/auth/mfa/enroll is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-001 (incl. qr_code_url).
- UNWANTED: If POST /api/auth/mfa/enroll is called without a valid auth token, the system shall return 401.
- UNWANTED: If POST /api/auth/mfa/enroll receives a request body failing validation, the system shall return 422 with a field-level error map.
- (+7 more — see tickets.json)

### access_policies_required
- users:user_own_select
- sessions:user_own_select
- api_keys:user_own_select

---

## T-V3-B-03: Backend: Skill manager backend (test endpoint) (F-002)

- **feature**: F-002 / **screens**: S-038 skill_manager
- **entities**: E-021 Skill
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 2.3h / 1 session(s)
- **endpoint paths** (1):
  - `POST /api/skills/{id}/test`
- **branch**: `claude/T-V3-B-03` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-03.md`

### files_changed
- backend/app/routers/skills.py (modify)
- backend/app/services/skills.py (modify)
- backend/app/schemas/skills.py (modify)
- backend/tests/routers/test_skills.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- UNWANTED: If POST /api/skills/{id}/test is invoked more than 10 times per minute per user, the system shall return 429.
- EVENT-DRIVEN: When POST /api/skills/{id}/test is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-002 (incl. output).
- UNWANTED: If POST /api/skills/{id}/test is called without a valid auth token, the system shall return 401.
- UNWANTED: If POST /api/skills/{id}/test receives a request body failing validation, the system shall return 422 with a field-level error map.

### access_policies_required
- skills:workspace_member_select

---

## T-V3-B-04: Backend: AI employees backend (org-chart / test / clone-from-user) (F-003)

- **feature**: F-003 / **screens**: S-036 ai_employees_org_chart, S-037 ai_employee_detail, S-038 skill_manager
- **entities**: E-008 AIEmployee, E-021 Skill, E-022 SkillExecution
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 4.9h / 2 session(s)
- **endpoint paths** (3):
  - `GET /api/ai-employees/org-chart`
  - `POST /api/ai-employees/{id}/test`
  - `POST /api/ai-employees/{id}/clone-from-user`
- **branch**: `claude/T-V3-B-04` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-04.md`

### files_changed
- backend/app/routers/ai_employees.py (modify)
- backend/app/services/ai_employees.py (modify)
- backend/app/schemas/ai_employees.py (modify)
- backend/tests/routers/test_ai_employees.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When GET /api/ai-employees/org-chart is called, the system shall return a hierarchical tree of all non-archived employees in the workspace.
- STATE-DRIVEN: While clone opt-in is FALSE for the source user, the system shall return 403 for POST /api/ai-employees/{id}/clone-from-user.
- UNWANTED: If POST /api/ai-employees/{id}/test is called more than 20 times per minute per workspace, the system shall return 429.
- EVENT-DRIVEN: When GET /api/ai-employees/org-chart is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-003 (incl. tree).
- UNWANTED: If GET /api/ai-employees/org-chart is called without a valid auth token, the system shall return 401.
- (+7 more — see tickets.json)

### access_policies_required
- a_i_employees:workspace_member_select
- skills:workspace_member_select
- skill_executions:workspace_member_select

---

## T-V3-B-05: Backend: Account/workspace backend (transfer-owner / invitations CRUD) (F-004)

- **feature**: F-004 / **screens**: S-007 account_settings, S-008 account_members, S-013 workspace_settings, S-014 workspace_members, S-015 workspace_invite
- **entities**: E-001 Account, E-003 Workspace, E-004 WorkspaceMember, E-002 User
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 6.0h / 2 session(s)
- **endpoint paths** (4):
  - `POST /api/accounts/{id}/transfer-owner`
  - `POST /api/accounts/{id}/invitations`
  - `DELETE /api/accounts/{id}/members/{user_id}`
  - `GET /api/invitations/{token}`
- **branch**: `claude/T-V3-B-05` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-05.md`

### files_changed
- backend/app/routers/accounts.py (modify)
- backend/app/services/accounts.py (modify)
- backend/app/schemas/accounts.py (modify)
- backend/tests/routers/test_accounts.py (new)
- backend/app/routers/invitations.py (modify)
- backend/app/services/invitations.py (modify)
- backend/app/schemas/invitations.py (modify)
- backend/tests/routers/test_invitations.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- UNWANTED: If POST /api/accounts/{id}/transfer-owner is called for a user who is not an account member, the system shall return 409.
- EVENT-DRIVEN: When POST /api/accounts/{id}/invitations is called more than 20 times per hour for the same account, the system shall return 429.
- UNWANTED: If GET /api/invitations/{token} resolves a token past its expires_at, the system shall return 409 expired.
- EVENT-DRIVEN: When POST /api/accounts/{id}/transfer-owner is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-004 (incl. old_owner_id).
- UNWANTED: If POST /api/accounts/{id}/transfer-owner is called without a valid auth token, the system shall return 401.
- (+8 more — see tickets.json)

### access_policies_required
- accounts:workspace_member_select
- workspaces:workspace_member_select
- workspace_members:workspace_member_select
- users:workspace_member_select

---

## T-V3-B-06: Backend: Workspace member role + invitation revocation backend (F-004)

- **feature**: F-004 / **screens**: S-007 account_settings, S-008 account_members, S-013 workspace_settings, S-014 workspace_members, S-015 workspace_invite
- **entities**: E-001 Account, E-003 Workspace, E-004 WorkspaceMember, E-002 User
- **wave**: 2 / **group**: B / **deliverable**: backend
- **estimate**: 3.6h / 1 session(s)
- **endpoint paths** (2):
  - `PUT /api/workspaces/{id}/members/{user_id}/role`
  - `DELETE /api/workspaces/{id}/invitations/{token}`
- **branch**: `claude/T-V3-B-06` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-06.md`

### files_changed
- backend/app/routers/workspaces.py (modify)
- backend/app/services/workspaces.py (modify)
- backend/app/schemas/workspaces.py (modify)
- backend/tests/routers/test_workspaces.py (new)
- backend/app/routers/invitations.py (modify)
- backend/app/services/invitations.py (modify)
- backend/app/schemas/invitations.py (modify)
- backend/tests/routers/test_invitations.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When PUT /api/accounts/{id} is called by the owner with a valid plan upgrade, the system shall update plan and emit account_updated audit log.
- UNWANTED: If POST /api/accounts/{id}/transfer-owner is called for a user who is not an account member, the system shall return 409.
- UNWANTED: If DELETE /api/workspaces/{id}/members/{user_id} would leave the workspace with zero admin, the system shall return 409.
- EVENT-DRIVEN: When POST /api/accounts/{id}/invitations is called more than 20 times per hour for the same account, the system shall return 429.
- STATE-DRIVEN: While an account has reached the workspace cap of its plan, the system shall return 409 for POST /api/workspaces.
- (+6 more — see tickets.json)

### access_policies_required
- accounts:workspace_member_select
- workspaces:workspace_member_select
- workspace_members:workspace_member_select
- users:workspace_member_select

---

## T-V3-B-07: Backend: Hearing → spec backend (save / specs CRUD + comments) (F-005)

- **feature**: F-005 / **screens**: S-020 hearing_chat, S-022 spec_viewer
- **entities**: E-009 Hearing, E-010 Spec, E-030 Comment, E-027 ChatThread
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 6.0h / 2 session(s)
- **endpoint paths** (4):
  - `POST /api/workspaces/{id}/hearing/save`
  - `GET /api/workspaces/{id}/specs`
  - `GET /api/workspaces/{id}/specs/{spec_id}/comments`
  - `POST /api/workspaces/{id}/specs/{spec_id}/comments`
- **branch**: `claude/T-V3-B-07` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-07.md`

### files_changed
- backend/app/routers/hearing.py (modify)
- backend/app/services/hearing.py (modify)
- backend/app/schemas/hearing.py (modify)
- backend/tests/routers/test_hearing.py (new)
- backend/app/routers/specs.py (modify)
- backend/app/services/specs.py (modify)
- backend/app/schemas/specs.py (modify)
- backend/tests/routers/test_specs.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When POST /api/workspaces/{id}/hearing/save is called, the system shall persist slot_state with a monotonically increasing version.
- STATE-DRIVEN: While a hearing session is in 'paused' state, the system shall accept POST /api/workspaces/{id}/hearing/save to resume from last checkpoint.
- UNWANTED: If POST /api/workspaces/{id}/specs/{spec_id}/comments body exceeds 10000 chars, the system shall return 422.
- EVENT-DRIVEN: When POST /api/workspaces/{id}/hearing/save is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-005 (incl. hearing_id).
- UNWANTED: If POST /api/workspaces/{id}/hearing/save is called without a valid auth token, the system shall return 401.
- (+10 more — see tickets.json)

### access_policies_required
- hearings:workspace_member_select
- specs:workspace_member_select
- comments:workspace_member_select_insert
- chat_threads:workspace_member_select

---

## T-V3-B-08: Backend: Mocks backend (mocks list / detail / html GET/PUT) (F-005b)

- **feature**: F-005b / **screens**: S-023 mock_browser, S-024 component_catalog, S-025 screen_flow_map, S-026 mock_editor
- **entities**: E-011 Screen, E-012 Component, E-013 ScreenComponent, E-014 Artifact
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 6.0h / 2 session(s)
- **endpoint paths** (4):
  - `GET /api/workspaces/{id}/mocks`
  - `GET /api/workspaces/{id}/mocks/{screen_id}`
  - `GET /api/workspaces/{id}/mocks/{screen_id}/html`
  - `PUT /api/workspaces/{id}/mocks/{screen_id}/html`
- **branch**: `claude/T-V3-B-08` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-08.md`

### files_changed
- backend/app/routers/mocks.py (modify)
- backend/app/services/mocks.py (modify)
- backend/app/schemas/mocks.py (modify)
- backend/tests/routers/test_mocks.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When GET /api/workspaces/{id}/mocks/{screen_id}/html is called, the system shall return the latest version of the mock HTML.
- EVENT-DRIVEN: When PUT /api/workspaces/{id}/mocks/{screen_id}/html is called with a new HTML body, the system shall increment the version and persist a snapshot.
- UNWANTED: If PUT /api/workspaces/{id}/mocks/{screen_id}/html receives html body > 1MB, the system shall return 422.
- UNWANTED: If POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit is called more than 30 times per minute per workspace, the system shall return 429.
- STATE-DRIVEN: While a mock is locked for editing by another user, the system shall return 409 for PUT /api/workspaces/{id}/mocks/{screen_id}/html.
- (+11 more — see tickets.json)

### access_policies_required
- screens:workspace_member_select
- components:workspace_member_select
- screen_components:workspace_member_select
- artifacts:workspace_member_select

---

## T-V3-B-09: Backend: Mocks backend (ai-edit / components / screen-flow) (F-005b)

- **feature**: F-005b / **screens**: S-023 mock_browser, S-024 component_catalog, S-025 screen_flow_map, S-026 mock_editor
- **entities**: E-011 Screen, E-012 Component, E-013 ScreenComponent, E-014 Artifact
- **wave**: 2 / **group**: B / **deliverable**: backend
- **estimate**: 6.0h / 2 session(s)
- **endpoint paths** (4):
  - `POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit`
  - `GET /api/workspaces/{id}/components`
  - `GET /api/workspaces/{id}/components/{id}/usage`
  - `GET /api/workspaces/{id}/screen-flow`
- **branch**: `claude/T-V3-B-09` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-09.md`

### files_changed
- backend/app/routers/mocks.py (modify)
- backend/app/services/mocks.py (modify)
- backend/app/schemas/mocks.py (modify)
- backend/tests/routers/test_mocks.py (new)
- backend/app/routers/components.py (modify)
- backend/app/services/components.py (modify)
- backend/app/schemas/components.py (modify)
- backend/tests/routers/test_components.py (new)
- backend/app/routers/screen_flow.py (modify)
- backend/app/services/screen_flow.py (modify)
- backend/app/schemas/screen_flow.py (modify)
- backend/tests/routers/test_screen_flow.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- UNWANTED: If POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit is called more than 30 times per minute per workspace, the system shall return 429.
- EVENT-DRIVEN: When POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-005b (incl. diff).
- UNWANTED: If POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit is called without a valid auth token, the system shall return 401.
- UNWANTED: If POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit receives a request body failing validation, the system shall return 422 with a field-level error map.
- UNWANTED: If POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit is called above the rate limit (30/min/workspace), the system shall return 429.
- (+9 more — see tickets.json)

### access_policies_required
- screens:workspace_member_select
- components:workspace_member_select
- screen_components:workspace_member_select
- artifacts:workspace_member_select

---

## T-V3-B-10: Backend: Requirements backend (CRUD / versions / task comments) (F-006)

- **feature**: F-006 / **screens**: S-021 requirements_editor, S-030 task_detail
- **entities**: E-015 Requirement, E-016 Task, E-017 TaskDependency, E-019 AcceptanceCriterion
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 6.0h / 2 session(s)
- **endpoint paths** (4):
  - `GET /api/workspaces/{id}/requirements`
  - `PUT /api/workspaces/{id}/requirements`
  - `POST /api/workspaces/{id}/requirements/versions`
  - `POST /api/tasks/{id}/comments`
- **branch**: `claude/T-V3-B-10` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-10.md`

### files_changed
- backend/app/routers/requirements.py (modify)
- backend/app/services/requirements.py (modify)
- backend/app/schemas/requirements.py (modify)
- backend/tests/routers/test_requirements.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When PUT /api/workspaces/{id}/requirements is called with EARS-conformant items, the system shall persist them and return version+1.
- UNWANTED: If PUT /api/workspaces/{id}/requirements is called with items that fail EARS form validation, the system shall return 422 with offending item indices.
- EVENT-DRIVEN: When POST /api/workspaces/{id}/requirements/versions is called, the system shall snapshot the current requirements and return a new version_id.
- EVENT-DRIVEN: When GET /api/workspaces/{id}/requirements is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-006 (incl. requirements).
- UNWANTED: If GET /api/workspaces/{id}/requirements is called without a valid auth token, the system shall return 401.
- (+10 more — see tickets.json)

### access_policies_required
- requirements:workspace_member_select
- tasks:workspace_member_select
- task_dependencies:workspace_member_select
- acceptance_criterions:workspace_member_select

---

## T-V3-B-11: Backend: Tasks backend (bulk-play / bulk-archive / export.csv / dag) (F-007)

- **feature**: F-007 / **screens**: S-012 workspace_dashboard, S-027 kanban_accordion, S-028 task_list, S-029 dag_view, S-030 task_detail
- **entities**: E-016 Task, E-017 TaskDependency
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 6.0h / 2 session(s)
- **endpoint paths** (4):
  - `POST /api/workspaces/{id}/tasks/bulk-play`
  - `POST /api/workspaces/{id}/tasks/bulk-archive`
  - `GET /api/workspaces/{id}/tasks/export.csv`
  - `GET /api/workspaces/{id}/tasks/dag`
- **branch**: `claude/T-V3-B-11` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-11.md`

### files_changed
- backend/app/routers/tasks.py (modify)
- backend/app/services/tasks.py (modify)
- backend/app/schemas/tasks.py (modify)
- backend/tests/routers/test_tasks.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When POST /api/workspaces/{id}/tasks/bulk-play is called with a list of task_ids, the system shall spawn sessions in dependency order.
- UNWANTED: If POST /api/workspaces/{id}/tasks/bulk-play exceeds max_parallel_per_ws_default, the system shall queue overflow and return 200 with queued count.
- EVENT-DRIVEN: When POST /api/workspaces/{id}/tasks/bulk-play is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-007 (incl. session_ids).
- UNWANTED: If POST /api/workspaces/{id}/tasks/bulk-play is called without a valid auth token, the system shall return 401.
- UNWANTED: If POST /api/workspaces/{id}/tasks/bulk-play receives a request body failing validation, the system shall return 422 with a field-level error map.
- (+8 more — see tickets.json)

### access_policies_required
- tasks:workspace_member_select
- task_dependencies:workspace_member_select

---

## T-V3-B-12: Backend: Tasks backend (play single / play-all) (F-007)

- **feature**: F-007 / **screens**: S-012 workspace_dashboard, S-027 kanban_accordion, S-028 task_list, S-029 dag_view, S-030 task_detail
- **entities**: E-016 Task, E-017 TaskDependency
- **wave**: 2 / **group**: B / **deliverable**: backend
- **estimate**: 4.9h / 2 session(s)
- **endpoint paths** (3):
  - `POST /api/tasks/{id}/play`
  - `POST /api/workspaces/{id}/tasks/play-all`
  - `POST /api/workspaces/{id}/play-all`
- **branch**: `claude/T-V3-B-12` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-12.md`

### files_changed
- backend/app/routers/tasks.py (modify)
- backend/app/services/tasks.py (modify)
- backend/app/schemas/tasks.py (modify)
- backend/tests/routers/test_tasks.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- UNWANTED: If POST /api/tasks/{id}/play is called for a task with unsatisfied dependencies, the system shall return 409.
- EVENT-DRIVEN: When POST /api/tasks/{id}/play is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-007 (incl. session_id).
- UNWANTED: If POST /api/tasks/{id}/play is called without a valid auth token, the system shall return 401.
- UNWANTED: If POST /api/tasks/{id}/play receives a request body failing validation, the system shall return 422 with a field-level error map.
- UNWANTED: If POST /api/tasks/{id}/play is called above the rate limit (30/min/user), the system shall return 429.
- (+4 more — see tickets.json)

### access_policies_required
- tasks:workspace_member_select
- task_dependencies:workspace_member_select

---

## T-V3-B-13: Backend: Phase management backend (phases list/create/gate) (F-008)

- **feature**: F-008 / **screens**: S-016 phase_management
- **entities**: E-020 Phase, E-016 Task
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 4.9h / 2 session(s)
- **endpoint paths** (3):
  - `GET /api/workspaces/{id}/phases`
  - `POST /api/workspaces/{id}/phases`
  - `POST /api/workspaces/{id}/phases/{phase_id}/gate`
- **branch**: `claude/T-V3-B-13` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-13.md`

### files_changed
- backend/app/routers/phases.py (modify)
- backend/app/services/phases.py (modify)
- backend/app/schemas/phases.py (modify)
- backend/tests/routers/test_phases.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When POST /api/workspaces/{id}/phases/{phase_id}/gate is called and all gate_conditions evaluate true, the system shall unlock the next phase.
- UNWANTED: If POST /api/workspaces/{id}/phases/{phase_id}/gate is called and gate_conditions are not met, the system shall return 409 with failing conditions listed.
- UNWANTED: If POST /api/workspaces/{id}/phases would create more than 10 phases for the workspace, the system shall return 409.
- EVENT-DRIVEN: When GET /api/workspaces/{id}/phases is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-008 (incl. phases).
- UNWANTED: If GET /api/workspaces/{id}/phases is called without a valid auth token, the system shall return 401.
- (+7 more — see tickets.json)

### access_policies_required
- phases:workspace_member_select
- tasks:workspace_member_select

---

## T-V3-B-14: Backend: Dependency graph backend (edges + impact-analysis) (F-009)

- **feature**: F-009 / **screens**: S-017 dependency_graph, S-029 dag_view
- **entities**: E-017 TaskDependency, E-016 Task
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 4.9h / 2 session(s)
- **endpoint paths** (3):
  - `GET /api/workspaces/{id}/dependencies`
  - `POST /api/workspaces/{id}/dependencies`
  - `POST /api/workspaces/{id}/dependencies/impact-analysis`
- **branch**: `claude/T-V3-B-14` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-14.md`

### files_changed
- backend/app/routers/dependencies.py (modify)
- backend/app/services/dependencies.py (modify)
- backend/app/schemas/dependencies.py (modify)
- backend/tests/routers/test_dependencies.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When POST /api/workspaces/{id}/dependencies is called with a valid edge, the system shall persist it and return 200.
- UNWANTED: If POST /api/workspaces/{id}/dependencies would create a cycle in the task DAG, the system shall return 409 with cycle path included.
- EVENT-DRIVEN: When POST /api/workspaces/{id}/dependencies/impact-analysis is called for a task, the system shall return all downstream affected tasks within blast_radius.
- EVENT-DRIVEN: When GET /api/workspaces/{id}/dependencies is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-009 (incl. dependencies).
- UNWANTED: If GET /api/workspaces/{id}/dependencies is called without a valid auth token, the system shall return 401.
- (+6 more — see tickets.json)

### access_policies_required
- task_dependencies:workspace_member_select
- tasks:workspace_member_select

---

## T-V3-B-15: Backend: Sessions backend (list / detail / kill / kill-all) (F-010)

- **feature**: F-010 / **screens**: S-031 swarm_grid, S-032 session_detail
- **entities**: E-024 Session, E-025 SessionLog
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 6.0h / 2 session(s)
- **endpoint paths** (4):
  - `GET /api/workspaces/{id}/sessions`
  - `GET /api/sessions/{id}`
  - `POST /api/sessions/{id}/kill`
  - `POST /api/workspaces/{id}/sessions/kill-all`
- **branch**: `claude/T-V3-B-15` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-15.md`

### files_changed
- backend/app/routers/sessions.py (modify)
- backend/app/services/sessions.py (modify)
- backend/app/schemas/sessions.py (modify)
- backend/tests/routers/test_sessions.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When POST /api/sessions/{id}/pause is called for a running session, the system shall save a checkpoint and transition status to 'paused' within 5 seconds.
- UNWANTED: If POST /api/sessions/{id}/resume is called for a session that is not in paused or crashed state, the system shall return 409.
- EVENT-DRIVEN: When POST /api/sessions/{id}/rollback is called by workspace_admin, the system shall restore the session state to the given checkpoint and emit audit log.
- EVENT-DRIVEN: When GET /api/workspaces/{id}/sessions is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-010 (incl. sessions).
- UNWANTED: If GET /api/workspaces/{id}/sessions is called without a valid auth token, the system shall return 401.
- (+8 more — see tickets.json)

### access_policies_required
- sessions:workspace_member_select
- session_logs:workspace_member_select

---

## T-V3-B-16: Backend: Sessions backend (pause / resume / rollback) (F-010)

- **feature**: F-010 / **screens**: S-031 swarm_grid, S-032 session_detail
- **entities**: E-024 Session, E-025 SessionLog
- **wave**: 2 / **group**: B / **deliverable**: backend
- **estimate**: 4.9h / 2 session(s)
- **endpoint paths** (3):
  - `POST /api/sessions/{id}/pause`
  - `POST /api/sessions/{id}/resume`
  - `POST /api/sessions/{id}/rollback`
- **branch**: `claude/T-V3-B-16` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-16.md`

### files_changed
- backend/app/routers/sessions.py (modify)
- backend/app/services/sessions.py (modify)
- backend/app/schemas/sessions.py (modify)
- backend/tests/routers/test_sessions.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When POST /api/sessions/{id}/pause is called for a running session, the system shall save a checkpoint and transition status to 'paused' within 5 seconds.
- UNWANTED: If POST /api/sessions/{id}/resume is called for a session that is not in paused or crashed state, the system shall return 409.
- EVENT-DRIVEN: When POST /api/sessions/{id}/rollback is called by workspace_admin, the system shall restore the session state to the given checkpoint and emit audit log.
- EVENT-DRIVEN: When POST /api/sessions/{id}/pause is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-010 (incl. paused_at).
- UNWANTED: If POST /api/sessions/{id}/pause is called without a valid auth token, the system shall return 401.
- (+4 more — see tickets.json)

### access_policies_required
- sessions:workspace_member_select
- session_logs:workspace_member_select

---

## T-V3-B-17: Backend: Red-lines backend (CRUD + test) (F-012)

- **feature**: F-012 / **screens**: S-019 red_lines_editor, S-034 violations_inbox
- **entities**: E-031 RedLine, E-032 RedLineViolation
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 4.9h / 2 session(s)
- **endpoint paths** (3):
  - `GET /api/workspaces/{id}/red-lines`
  - `POST /api/workspaces/{id}/red-lines`
  - `POST /api/workspaces/{id}/red-lines/test`
- **branch**: `claude/T-V3-B-17` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-17.md`

### files_changed
- backend/app/routers/red_lines.py (modify)
- backend/app/services/red_lines.py (modify)
- backend/app/schemas/red_lines.py (modify)
- backend/tests/routers/test_red_lines.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- UBIQUITOUS: The system shall evaluate every AI-initiated action against active red_line patterns before execution.
- EVENT-DRIVEN: When an action matches a red_line with action='block', the system shall halt execution and create a pending violation record.
- UNWANTED: If a violation is in 'pending' state, the system shall not allow the originating AI session to continue without admin approval.
- EVENT-DRIVEN: When POST /api/violations/{id}/approve is called by a workspace_admin, the system shall resume the originating session.
- UNWANTED: If POST /api/violations/{id}/approve is called for an already-resolved violation, the system shall return 409.
- (+9 more — see tickets.json)

### access_policies_required
- red_lines:workspace_member_select
- red_line_violations:workspace_member_select

---

## T-V3-B-18: Backend: Violations backend (list / approve / reject) (F-012)

- **feature**: F-012 / **screens**: S-019 red_lines_editor, S-034 violations_inbox
- **entities**: E-031 RedLine, E-032 RedLineViolation
- **wave**: 2 / **group**: B / **deliverable**: backend
- **estimate**: 4.9h / 2 session(s)
- **endpoint paths** (3):
  - `GET /api/workspaces/{id}/violations`
  - `POST /api/violations/{id}/approve`
  - `POST /api/violations/{id}/reject`
- **branch**: `claude/T-V3-B-18` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-18.md`

### files_changed
- backend/app/routers/violations.py (modify)
- backend/app/services/violations.py (modify)
- backend/app/schemas/violations.py (modify)
- backend/tests/routers/test_violations.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When POST /api/violations/{id}/approve is called by a workspace_admin, the system shall resume the originating session.
- UNWANTED: If POST /api/violations/{id}/approve is called for an already-resolved violation, the system shall return 409.
- EVENT-DRIVEN: When GET /api/workspaces/{id}/violations is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-012 (incl. violations).
- UNWANTED: If GET /api/workspaces/{id}/violations is called without a valid auth token, the system shall return 401.
- UNWANTED: If GET /api/workspaces/{id}/violations receives a request body failing validation, the system shall return 422 with a field-level error map.
- (+4 more — see tickets.json)

### access_policies_required
- red_lines:workspace_member_select
- red_line_violations:workspace_member_select

---

## T-V3-B-19: Backend: PR review backend (get / approve / comments / merge) (F-013)

- **feature**: F-013 / **screens**: S-033 pr_review, S-035 delivery_pack, S-042 client_workspace_view, S-043 client_comment_thread
- **entities**: E-033 PullRequest, E-034 Delivery, E-030 Comment
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 6.0h / 2 session(s)
- **endpoint paths** (4):
  - `GET /api/workspaces/{id}/prs/{pr_number}`
  - `POST /api/prs/{id}/approve`
  - `POST /api/prs/{id}/comments`
  - `POST /api/prs/{id}/merge`
- **branch**: `claude/T-V3-B-19` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-19.md`

### files_changed
- backend/app/routers/comments.py (modify)
- backend/app/services/comments.py (modify)
- backend/app/schemas/comments.py (modify)
- backend/tests/routers/test_comments.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When POST /api/prs/{id}/merge is called by a workspace_admin with valid merge_method, the system shall merge the PR via GitHub API and emit pr_merged audit log.
- UNWANTED: If POST /api/prs/{id}/merge is called for a PR with unresolved conflicts, the system shall return 409.
- EVENT-DRIVEN: When GET /api/workspaces/{id}/prs/{pr_number} is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-013 (incl. pr).
- UNWANTED: If GET /api/workspaces/{id}/prs/{pr_number} is called without a valid auth token, the system shall return 401.
- EVENT-DRIVEN: When POST /api/prs/{id}/approve is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-013 (incl. approved_at).
- (+7 more — see tickets.json)

### access_policies_required
- pull_requests:workspace_member_select
- deliveries:workspace_owner_select
- comments:workspace_member_select_insert

---

## T-V3-B-20: Backend: Client portal backend (workspaces / spec / comments) (F-013)

- **feature**: F-013 / **screens**: S-033 pr_review, S-035 delivery_pack, S-042 client_workspace_view, S-043 client_comment_thread
- **entities**: E-033 PullRequest, E-034 Delivery, E-030 Comment
- **wave**: 2 / **group**: B / **deliverable**: backend
- **estimate**: 6.0h / 2 session(s)
- **endpoint paths** (5):
  - `GET /api/client/workspaces/{token}`
  - `GET /api/client/workspaces/{token}/spec`
  - `GET /api/client/comments/{thread_id}`
  - `POST /api/client/comments`
  - `POST /api/comments/{id}/resolve`
- **branch**: `claude/T-V3-B-20` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-20.md`

### files_changed
- backend/app/routers/comments.py (modify)
- backend/app/services/comments.py (modify)
- backend/app/schemas/comments.py (modify)
- backend/tests/routers/test_comments.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- STATE-DRIVEN: While a client token has expired, the system shall return 409 for GET /api/client/workspaces/{token}.
- UNWANTED: If POST /api/client/comments exceeds 20 requests per hour per token, the system shall return 429.
- EVENT-DRIVEN: When GET /api/client/workspaces/{token} is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-013 (incl. workspace).
- UNWANTED: If GET /api/client/workspaces/{token} is called without a valid auth token, the system shall return 401.
- EVENT-DRIVEN: When GET /api/client/workspaces/{token}/spec is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-013 (incl. spec_html_url).
- (+10 more — see tickets.json)

### access_policies_required
- pull_requests:workspace_member_select
- deliveries:workspace_owner_select
- comments:workspace_member_select_insert

---

## T-V3-B-21: Backend: Delivery backend (delivery pack / approve / send-client) (F-013)

- **feature**: F-013 / **screens**: S-033 pr_review, S-035 delivery_pack, S-042 client_workspace_view, S-043 client_comment_thread
- **entities**: E-033 PullRequest, E-034 Delivery, E-030 Comment
- **wave**: 3 / **group**: B / **deliverable**: backend
- **estimate**: 4.9h / 2 session(s)
- **endpoint paths** (3):
  - `GET /api/workspaces/{id}/delivery`
  - `POST /api/workspaces/{id}/delivery/approve`
  - `POST /api/workspaces/{id}/delivery/send-client`
- **branch**: `claude/T-V3-B-21` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-21.md`

### files_changed
- backend/app/routers/delivery.py (modify)
- backend/app/services/delivery.py (modify)
- backend/app/schemas/delivery.py (modify)
- backend/tests/routers/test_delivery.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When POST /api/workspaces/{id}/delivery/send-client is called, the system shall generate a public token with expires_at and email the client.
- EVENT-DRIVEN: When GET /api/workspaces/{id}/delivery is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-013 (incl. delivery).
- UNWANTED: If GET /api/workspaces/{id}/delivery is called without a valid auth token, the system shall return 401.
- UNWANTED: If GET /api/workspaces/{id}/delivery receives a request body failing validation, the system shall return 422 with a field-level error map.
- EVENT-DRIVEN: When POST /api/workspaces/{id}/delivery/approve is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-013 (incl. approved_at).
- (+4 more — see tickets.json)

### access_policies_required
- pull_requests:workspace_member_select
- deliveries:workspace_owner_select
- comments:workspace_member_select_insert

---

## T-V3-B-22: Backend: Knowledge base backend (list + search) (F-016)

- **feature**: F-016 / **screens**: S-039 knowledge_base
- **entities**: E-035 KnowledgeItem, E-036 ObsidianVault
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 3.6h / 1 session(s)
- **endpoint paths** (2):
  - `GET /api/workspaces/{id}/knowledge`
  - `GET /api/workspaces/{id}/knowledge/search`
- **branch**: `claude/T-V3-B-22` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-22.md`

### files_changed
- backend/app/routers/knowledge.py (modify)
- backend/app/services/knowledge.py (modify)
- backend/app/schemas/knowledge.py (modify)
- backend/tests/routers/test_knowledge.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When GET /api/workspaces/{id}/knowledge/search is called with q, the system shall combine pgvector + pg_trgm + FTS and return top 50 hits.
- EVENT-DRIVEN: When GET /api/workspaces/{id}/knowledge is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-016 (incl. items).
- UNWANTED: If GET /api/workspaces/{id}/knowledge is called without a valid auth token, the system shall return 401.
- UNWANTED: If GET /api/workspaces/{id}/knowledge receives a request body failing validation, the system shall return 422 with a field-level error map.
- EVENT-DRIVEN: When GET /api/workspaces/{id}/knowledge/search is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-016 (incl. hits).
- (+2 more — see tickets.json)

### access_policies_required
- knowledge_items:workspace_member_select
- obsidian_vaults:workspace_member_select

---

## T-V3-B-23: Backend: Observability backend (cost-summary export + token-limit) (F-017)

- **feature**: F-017 / **screens**: S-040 cost_dashboard
- **entities**: E-026 CostLog, E-022 SkillExecution, E-024 Session
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 3.6h / 1 session(s)
- **endpoint paths** (2):
  - `GET /api/observability/cost-summary/export.csv`
  - `POST /api/workspaces/{id}/token-limit`
- **branch**: `claude/T-V3-B-23` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-23.md`

### files_changed
- backend/app/routers/observability.py (modify)
- backend/app/services/observability.py (modify)
- backend/app/schemas/observability.py (modify)
- backend/tests/routers/test_observability.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When GET /api/observability/cost-summary is called with date range, the system shall return total_usd + by_provider + by_user breakdown.
- STATE-DRIVEN: While monthly cost reaches 80% of the workspace limit, the system shall emit cost_limit_warning notification.
- UNWANTED: If monthly cost exceeds the workspace limit, the system shall block new LLM invocations and return 429 with budget_exceeded code.
- UBIQUITOUS: The system shall record every LLM invocation with tokens_used + cost_usd + provider tags within 1 second of completion.
- EVENT-DRIVEN: When GET /api/observability/cost-summary/export.csv is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-017 (incl. csv_body).
- (+4 more — see tickets.json)

### access_policies_required
- cost_logs:workspace_member_select
- skill_executions:workspace_member_select
- sessions:workspace_member_select

---

## T-V3-B-24: Backend: Audit logs backend (list / export.csv / export.json) (F-018)

- **feature**: F-018 / **screens**: S-010 notifications_inbox, S-041 audit_log_viewer
- **entities**: E-037 AuditLog, E-038 Notification
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 4.9h / 2 session(s)
- **endpoint paths** (3):
  - `GET /api/audit-logs`
  - `GET /api/audit-logs/export.csv`
  - `GET /api/audit-logs/export.json`
- **branch**: `claude/T-V3-B-24` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-24.md`

### files_changed
- backend/app/routers/audit_logs.py (modify)
- backend/app/services/audit_logs.py (modify)
- backend/app/schemas/audit_logs.py (modify)
- backend/tests/routers/test_audit_logs.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When GET /api/audit-logs/export.csv is called with a date range >90 days, the system shall return 422 with filter_too_broad.
- EVENT-DRIVEN: When GET /api/audit-logs is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-018 (incl. items).
- UNWANTED: If GET /api/audit-logs is called without a valid auth token, the system shall return 401.
- UNWANTED: If GET /api/audit-logs receives a request body failing validation, the system shall return 422 with a field-level error map.
- EVENT-DRIVEN: When GET /api/audit-logs/export.csv is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-018 (incl. csv_body).
- (+5 more — see tickets.json)

### access_policies_required
- audit_logs:workspace_admin_select
- notifications:workspace_admin_select

---

## T-V3-B-25: Backend: Notifications backend (list / read / read-all) (F-018)

- **feature**: F-018 / **screens**: S-010 notifications_inbox, S-041 audit_log_viewer
- **entities**: E-037 AuditLog, E-038 Notification
- **wave**: 2 / **group**: B / **deliverable**: backend
- **estimate**: 4.9h / 2 session(s)
- **endpoint paths** (3):
  - `GET /api/notifications`
  - `POST /api/notifications/{id}/read`
  - `POST /api/notifications/read-all`
- **branch**: `claude/T-V3-B-25` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-25.md`

### files_changed
- backend/app/routers/notifications.py (modify)
- backend/app/services/notifications.py (modify)
- backend/app/schemas/notifications.py (modify)
- backend/tests/routers/test_notifications.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- STATE-DRIVEN: While a notification is unread, the system shall include it in the unread_count of GET /api/notifications.
- EVENT-DRIVEN: When POST /api/notifications/read-all is called with no category filter, the system shall mark all unread notifications for the user as read.
- EVENT-DRIVEN: When GET /api/notifications is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-018 (incl. items).
- UNWANTED: If GET /api/notifications is called without a valid auth token, the system shall return 401.
- UNWANTED: If GET /api/notifications receives a request body failing validation, the system shall return 422 with a field-level error map.
- (+4 more — see tickets.json)

### access_policies_required
- audit_logs:workspace_admin_select
- notifications:workspace_admin_select

---

## T-V3-B-26: Backend: Account profile backend (/me CRUD / api-keys / oauth unlink) (F-023)

- **feature**: F-023 / **screens**: S-009 profile_settings
- **entities**: E-002 User, E-041 UserSettings, E-006 ApiKey
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 6.0h / 2 session(s)
- **endpoint paths** (4):
  - `GET /api/me`
  - `PUT /api/me`
  - `POST /api/me/api-keys`
  - `DELETE /api/me/oauth/{provider}`
- **branch**: `claude/T-V3-B-26` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-26.md`

### files_changed
- backend/app/routers/me.py (modify)
- backend/app/services/me.py (modify)
- backend/app/schemas/me.py (modify)
- backend/tests/routers/test_me.py (new)
- backend/app/routers/api_keys.py (modify)
- backend/app/services/api_keys.py (modify)
- backend/app/schemas/api_keys.py (modify)
- backend/tests/routers/test_api_keys.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When POST /api/me/api-keys is called, the system shall encrypt the key plaintext with pgsodium before persisting.
- UNWANTED: If POST /api/me/api-keys is called for a provider where a key already exists, the system shall return 409.
- EVENT-DRIVEN: When DELETE /api/me/oauth/{provider} is called, the system shall revoke the OAuth token at the provider and unlink locally.
- EVENT-DRIVEN: When GET /api/me is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-023 (incl. user).
- UNWANTED: If GET /api/me is called without a valid auth token, the system shall return 401.
- (+8 more — see tickets.json)

### access_policies_required
- users:workspace_member_select
- user_settings:workspace_member_select
- api_keys:workspace_member_select

---

## T-V3-B-27: Backend: Global search + account dashboard backend (F-024)

- **feature**: F-024 / **screens**: S-006 account_dashboard, S-011 global_search
- **entities**: E-016 Task, E-014 Artifact, E-037 AuditLog, E-035 KnowledgeItem
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 3.6h / 1 session(s)
- **endpoint paths** (2):
  - `GET /api/search`
  - `GET /api/accounts/{id}/dashboard`
- **branch**: `claude/T-V3-B-27` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-27.md`

### files_changed
- backend/app/routers/search.py (modify)
- backend/app/services/search.py (modify)
- backend/app/schemas/search.py (modify)
- backend/tests/routers/test_search.py (new)
- backend/app/routers/dashboard.py (modify)
- backend/app/services/dashboard.py (modify)
- backend/app/schemas/dashboard.py (modify)
- backend/tests/routers/test_dashboard.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When GET /api/search is called with a non-empty q, the system shall return hits ranked by combined FTS + vector similarity score.
- UNWANTED: If GET /api/search receives q > 500 chars or empty, the system shall return 422.
- UNWANTED: If GET /api/search exceeds 60 requests per minute per user, the system shall return 429.
- EVENT-DRIVEN: When GET /api/accounts/{id}/dashboard is called, the system shall aggregate KPI across all workspaces the caller belongs to within the account.
- EVENT-DRIVEN: When GET /api/search is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-024 (incl. hits).
- (+5 more — see tickets.json)

### access_policies_required
- tasks:workspace_member_select
- artifacts:workspace_member_select
- audit_logs:workspace_member_select
- knowledge_items:workspace_member_select

---

## T-V3-B-28: Backend: Constitution backend (get / versions / approve) (F-026)

- **feature**: F-026 / **screens**: S-018 constitution_editor
- **entities**: E-042 Constitution, E-031 RedLine
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 4.9h / 2 session(s)
- **endpoint paths** (3):
  - `GET /api/workspaces/{id}/constitution`
  - `POST /api/workspaces/{id}/constitution/versions`
  - `POST /api/workspaces/{id}/constitution/versions/{v}/approve`
- **branch**: `claude/T-V3-B-28` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-28.md`

### files_changed
- backend/app/routers/constitution.py (modify)
- backend/app/services/constitution.py (modify)
- backend/app/schemas/constitution.py (modify)
- backend/tests/routers/test_constitution.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When POST /api/workspaces/{id}/constitution/versions is called, the system shall create a new version snapshot without affecting the active version.
- EVENT-DRIVEN: When POST /api/workspaces/{id}/constitution/versions/{v}/approve is called, the system shall mark v as active and inject it into newly spawned sessions.
- UNWANTED: If POST /api/workspaces/{id}/constitution/versions content_md exceeds 10KB, the system shall return 422.
- EVENT-DRIVEN: When GET /api/workspaces/{id}/constitution is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-026 (incl. content_md).
- UNWANTED: If GET /api/workspaces/{id}/constitution is called without a valid auth token, the system shall return 401.
- (+6 more — see tickets.json)

### access_policies_required
- constitutions:workspace_member_select
- red_lines:workspace_member_select

---

## T-V3-B-29: Backend: Onboarding backend (get / advance / skip) (F-027)

- **feature**: F-027 / **screens**: S-048 welcome_first_login, S-049 workspace_setup_wizard, S-050 ai_employee_intro
- **entities**: E-002 User, E-041 UserSettings
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 4.9h / 2 session(s)
- **endpoint paths** (3):
  - `GET /api/me/onboarding`
  - `POST /api/me/onboarding/advance`
  - `POST /api/me/onboarding/skip`
- **branch**: `claude/T-V3-B-29` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-29.md`

### files_changed
- backend/app/routers/onboarding.py (modify)
- backend/app/services/onboarding.py (modify)
- backend/app/schemas/onboarding.py (modify)
- backend/tests/routers/test_onboarding.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- EVENT-DRIVEN: When POST /api/me/onboarding/advance is called with a valid step transition, the system shall persist progress and return the next_step.
- UNWANTED: If POST /api/me/onboarding/skip is called for a step marked required=true, the system shall return 409.
- EVENT-DRIVEN: When GET /api/me/onboarding is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-027 (incl. state).
- UNWANTED: If GET /api/me/onboarding is called without a valid auth token, the system shall return 401.
- UNWANTED: If GET /api/me/onboarding receives a request body failing validation, the system shall return 422 with a field-level error map.
- (+5 more — see tickets.json)

### access_policies_required
- users:workspace_member_select
- user_settings:workspace_member_select

---

## T-V3-B-30: Backend: Email backend (templates list + test-send) (F-028)

- **feature**: F-028 / **screens**: S-056 email_signup_verify, S-057 email_password_reset, S-058 email_invitation, S-059 email_task_notification, S-060 email_weekly_summary
- **entities**: E-043 EmailTemplate, E-044 EmailDelivery
- **wave**: 1 / **group**: B / **deliverable**: backend
- **estimate**: 3.6h / 1 session(s)
- **endpoint paths** (2):
  - `GET /api/email/templates`
  - `POST /api/email/test-send`
- **branch**: `claude/T-V3-B-30` / **audit**: `docs/audit/2026-05-16_v3/T-V3-B-30.md`

### files_changed
- backend/app/routers/email.py (modify)
- backend/app/services/email.py (modify)
- backend/app/schemas/email.py (modify)
- backend/tests/routers/test_email.py (new)

### acceptance_criteria.functional (excerpt, first 5)
- UNWANTED: If POST /api/email/test-send is called more than 10 times per hour per workspace, the system shall return 429.
- EVENT-DRIVEN: When GET /api/email/templates is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-028 (incl. templates).
- UNWANTED: If GET /api/email/templates is called without a valid auth token, the system shall return 401.
- UNWANTED: If GET /api/email/templates receives a request body failing validation, the system shall return 422 with a field-level error map.
- EVENT-DRIVEN: When POST /api/email/test-send is called with valid inputs by an authorized caller, the system shall return 2xx with the contract defined in features.json#F-028 (incl. delivery_id).
- (+3 more — see tickets.json)

### access_policies_required
- email_templates:workspace_member_select
- email_deliveries:workspace_member_select

---
