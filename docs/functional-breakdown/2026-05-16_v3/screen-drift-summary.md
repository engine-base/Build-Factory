# v3 Screen Drift Summary (2026-05-16)

> Build-Factory v3 functional-breakdown STEP 2 — screen↔frontend component drift detection result.

> Inputs: 64 v3 mocks (`docs/mocks/2026-05-15_v3/`) ↔ frontend/src/app pages.


## 数値サマリ

- 全 screen 数: **64**
- frontend 実装あり (hint match): **9**
- frontend 実装なし (missing): **55**
- h1 mismatch (impl HTML 比較): **未実施** (page.tsx 内 h1 を後段 lint で diff)
- meta tag drift: **0** (全 64 mock で `bf-screen-id` `bf-version=v3` 揃い済)

## severity 別

| severity | 件数 | 説明 | 流し込み先 group |
|---|---|---|---|
| missing (medium) | 55 | mock あるが frontend page なし | Group C (新規実装) |
| exists (low) | 9 | hint match。h1/KPI/section の lint diff は後段 | Group D (Drift fix, 必要時) |
| high | 0 | (未検出) | — |

## missing 一覧 (Group C 流し込み)

| screen_id | screen_name | category | mock |
|---|---|---|---|
| S-006 | account_dashboard | account | docs/mocks/2026-05-15_v3/account/S-006-account-dashboard.html |
| S-008 | account_members | account | docs/mocks/2026-05-15_v3/account/S-008-account-members.html |
| S-010 | notifications_inbox | account | docs/mocks/2026-05-15_v3/account/S-010-notifications-inbox.html |
| S-011 | global_search | account | docs/mocks/2026-05-15_v3/account/S-011-global-search.html |
| S-037 | ai_employee_detail | ai_management | docs/mocks/2026-05-15_v3/ai/S-037-ai-employee-detail.html |
| S-001 | login | auth | docs/mocks/2026-05-15_v3/auth/S-001-login.html |
| S-002 | signup | auth | docs/mocks/2026-05-15_v3/auth/S-002-signup.html |
| S-003 | password_reset | auth | docs/mocks/2026-05-15_v3/auth/S-003-password-reset.html |
| S-004 | mfa_setup | auth | docs/mocks/2026-05-15_v3/auth/S-004-mfa-setup.html |
| S-005 | oauth_callback | auth | docs/mocks/2026-05-15_v3/auth/S-005-oauth-callback.html |
| S-042 | client_workspace | client | docs/mocks/2026-05-15_v3/client/S-042-client-workspace.html |
| S-043 | client_comment | client | docs/mocks/2026-05-15_v3/client/S-043-client-comment.html |
| S-051 | confirm_delete | dialog | docs/mocks/2026-05-15_v3/dialog/S-051-confirm-delete.html |
| S-052 | unsaved_changes | dialog | docs/mocks/2026-05-15_v3/dialog/S-052-unsaved-changes.html |
| S-053 | mfa_challenge | dialog | docs/mocks/2026-05-15_v3/dialog/S-053-mfa-challenge.html |
| S-054 | session_expired | dialog | docs/mocks/2026-05-15_v3/dialog/S-054-session-expired.html |
| S-055 | danger_zone | dialog | docs/mocks/2026-05-15_v3/dialog/S-055-danger-zone.html |
| S-056 | email_signup_verify | email | docs/mocks/2026-05-15_v3/email/S-056-email-signup-verify.html |
| S-057 | email_password_reset | email | docs/mocks/2026-05-15_v3/email/S-057-email-password-reset.html |
| S-058 | email_invitation | email | docs/mocks/2026-05-15_v3/email/S-058-email-invitation.html |
| S-059 | email_task_notification | email | docs/mocks/2026-05-15_v3/email/S-059-email-task-notification.html |
| S-060 | email_weekly_summary | email | docs/mocks/2026-05-15_v3/email/S-060-email-weekly-summary.html |
| S-061 | export_spec_pdf | export | docs/mocks/2026-05-15_v3/export/S-061-export-spec-pdf.html |
| S-062 | export_delivery_report | export | docs/mocks/2026-05-15_v3/export/S-062-export-delivery-report.html |
| S-063 | search_results | extras | docs/mocks/2026-05-15_v3/extras/S-063-search-results.html |
| S-064 | api_tokens | extras | docs/mocks/2026-05-15_v3/extras/S-064-api-tokens.html |
| S-016 | phase_management | moat | docs/mocks/2026-05-15_v3/moat/S-016-phase-management.html |
| S-017 | dependency_graph | moat | docs/mocks/2026-05-15_v3/moat/S-017-dependency-graph.html |
| S-018 | constitution_editor | safety | docs/mocks/2026-05-15_v3/moat/S-018-constitution-editor.html |
| S-019 | red_line_settings | safety | docs/mocks/2026-05-15_v3/moat/S-019-red-line-settings.html |
| S-034 | red_line_approval | safety | docs/mocks/2026-05-15_v3/moat/S-034-red-line-approval.html |
| S-048 | welcome_first_login | onboarding | docs/mocks/2026-05-15_v3/onboarding/S-048-welcome-first-login.html |
| S-049 | workspace_setup_wizard | onboarding | docs/mocks/2026-05-15_v3/onboarding/S-049-workspace-setup-wizard.html |
| S-050 | ai_employee_intro | onboarding | docs/mocks/2026-05-15_v3/onboarding/S-050-ai-employee-intro.html |
| S-033 | pr_review | review | docs/mocks/2026-05-15_v3/review/S-033-pr-review.html |
| S-035 | delivery_approval | review | docs/mocks/2026-05-15_v3/review/S-035-delivery-approval.html |
| S-020 | hearing_session | spec | docs/mocks/2026-05-15_v3/spec/S-020-hearing-session.html |
| S-021 | requirements_editor | spec | docs/mocks/2026-05-15_v3/spec/S-021-requirements-editor.html |
| S-022 | spec_viewer | spec | docs/mocks/2026-05-15_v3/spec/S-022-spec-viewer.html |
| S-023 | screen_mock_viewer | spec | docs/mocks/2026-05-15_v3/spec/S-023-screen-mock-viewer.html |
| S-024 | component_catalog | spec | docs/mocks/2026-05-15_v3/spec/S-024-component-catalog.html |
| S-025 | screen_flow_map | spec | docs/mocks/2026-05-15_v3/spec/S-025-screen-flow-map.html |
| S-026 | design_html_editor | spec | docs/mocks/2026-05-15_v3/spec/S-026-design-html-editor.html |
| S-044 | not_found_404 | system | docs/mocks/2026-05-15_v3/system/S-044-not-found-404.html |
| S-045 | server_error_500 | system | docs/mocks/2026-05-15_v3/system/S-045-server-error-500.html |
| S-046 | forbidden_403 | system | docs/mocks/2026-05-15_v3/system/S-046-forbidden-403.html |
| S-047 | maintenance | system | docs/mocks/2026-05-15_v3/system/S-047-maintenance.html |
| S-027 | task_kanban | task | docs/mocks/2026-05-15_v3/task/S-027-task-kanban.html |
| S-029 | task_dag_view | task | docs/mocks/2026-05-15_v3/task/S-029-task-dag-view.html |
| S-030 | task_detail | task | docs/mocks/2026-05-15_v3/task/S-030-task-detail.html |
| S-032 | swarm_session_detail | execution | docs/mocks/2026-05-15_v3/task/S-032-swarm-session-detail.html |
| S-012 | workspace_dashboard | workspace | docs/mocks/2026-05-15_v3/workspace/S-012-workspace-dashboard.html |
| S-013 | workspace_settings | workspace | docs/mocks/2026-05-15_v3/workspace/S-013-workspace-settings.html |
| S-014 | workspace_members | workspace | docs/mocks/2026-05-15_v3/workspace/S-014-workspace-members.html |
| S-015 | workspace_invite | workspace | docs/mocks/2026-05-15_v3/workspace/S-015-workspace-invite.html |

## exists 一覧 (Group D 候補 / hint match)

| screen_id | screen_name | impl_path |
|---|---|---|
| S-007 | account_settings | frontend/src/app/settings/account/page.tsx |
| S-009 | profile_settings | frontend/src/app/settings/profile/page.tsx |
| S-036 | ai_employees_org_chart | frontend/src/app/ai-employees/page.tsx |
| S-038 | skill_manager | frontend/src/app/skills/page.tsx |
| S-039 | knowledge_base | frontend/src/app/knowledge/page.tsx |
| S-040 | cost_dashboard | frontend/src/app/dashboard/costs/page.tsx |
| S-041 | audit_log_viewer | frontend/src/app/audit-logs/page.tsx |
| S-028 | task_list | frontend/src/app/tasks/page.tsx |
| S-031 | swarm_grid | frontend/src/app/dashboard/swarm/page.tsx |

## meta tag 検証 (全 64 件 pass)

- `bf-screen-id` unique: OK (64 unique)
- `bf-version=v3`: 全件 OK
- `bf-feature-id` / `bf-task-ids` / `bf-entities` / `bf-related-apis`: 全件 present (CSV 配列)
- `bf-spec-link` / `bf-design-link`: 全件 present

## 検証ステップ (次フェーズ)

- [ ] `scripts/lint-mock.sh` (rule_id: `mock-impl-diff`) を 64 mock 全件に走らせ、impl 実在分の h1/KPI/section diff を取得
- [ ] Group C: missing 47 件 (推定) を v3 task-decomposition に流し込み (Vertical Slice / UI)
- [ ] Group D: exists hint match 件を実 page.tsx と diff 取り、改修 task として登録

---

_Generated by `docs/functional-breakdown/2026-05-16_v3/_extract.py` on 2026-05-16._