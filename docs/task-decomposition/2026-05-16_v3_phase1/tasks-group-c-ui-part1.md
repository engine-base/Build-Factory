# Group C — UI Vertical Slice (Part 1) tasks

- 生成日: 2026-05-16
- スコープ: 9 categories (account / ai_management / auth / client / design-system 該当無 / dialog / email / export / extras)
- dialog 5 件は親画面に merge: S-051→S-008, S-052→S-007, S-053→S-001, S-054→S-006, S-055→S-007
- 総タスク数: 25
- 総工数: 104 h

| # | task_id | screen(s) | feature | est h | depends_on | mock |
|---|---|---|---|---|---|---|
| 01 | T-V3-C-01 | S-001 + S-053 | F-001 | 5 | T-FOUNDATION-08, T-V3-AUTH-01, T-V3-AUTH-02, T-V3-AUTH-03, T-V3-AUTH-04, T-V3-AUTH-05, T-V3-AUTH-06, T-V3-B-RBAC-01 | docs/mocks/2026-05-15_v3/auth/S-001-login.html |
| 02 | T-V3-C-02 | S-002 | F-001 | 4 | T-FOUNDATION-08, T-V3-AUTH-01, T-V3-AUTH-02, T-V3-AUTH-03, T-V3-AUTH-04, T-V3-AUTH-05, T-V3-AUTH-06, T-V3-B-ACCOUNT-01 | docs/mocks/2026-05-15_v3/auth/S-002-signup.html |
| 03 | T-V3-C-03 | S-003 | F-001 | 4 | T-FOUNDATION-08, T-V3-AUTH-01, T-V3-AUTH-02, T-V3-AUTH-03, T-V3-AUTH-04, T-V3-AUTH-05, T-V3-AUTH-06 | docs/mocks/2026-05-15_v3/auth/S-003-password-reset.html |
| 04 | T-V3-C-04 | S-004 | F-001 | 4 | T-FOUNDATION-08, T-V3-AUTH-01, T-V3-AUTH-02, T-V3-AUTH-03, T-V3-AUTH-04, T-V3-AUTH-05, T-V3-AUTH-06 | docs/mocks/2026-05-15_v3/auth/S-004-mfa-setup.html |
| 05 | T-V3-C-05 | S-005 | F-001 | 4 | T-FOUNDATION-08, T-V3-AUTH-01, T-V3-AUTH-02, T-V3-AUTH-03, T-V3-AUTH-04, T-V3-AUTH-05, T-V3-AUTH-06 | docs/mocks/2026-05-15_v3/auth/S-005-oauth-callback.html |
| 06 | T-V3-C-06 | S-006 + S-054 | F-024 | 5 | T-FOUNDATION-08, T-V3-B-SEARCH-01, T-V3-B-NOTIF-01, T-V3-B-AUDIT-01, T-V3-B-PHASE-01, T-V3-B-TASK-01, T-V3-B-COST-01 | docs/mocks/2026-05-15_v3/account/S-006-account-dashboard.html |
| 07 | T-V3-C-07 | S-007 + S-052 + S-055 | F-004 | 5 | T-FOUNDATION-08, T-V3-B-ACCOUNT-01 | docs/mocks/2026-05-15_v3/account/S-007-account-settings.html |
| 08 | T-V3-C-08 | S-008 + S-051 | F-004 | 5 | T-FOUNDATION-08, T-V3-B-ACCOUNT-01, T-V3-B-RBAC-01 | docs/mocks/2026-05-15_v3/account/S-008-account-members.html |
| 09 | T-V3-C-09 | S-009 | F-022 | 4 | T-FOUNDATION-08, T-V3-B-AI-02, T-V3-B-PROFILE-01 | docs/mocks/2026-05-15_v3/account/S-009-profile-settings.html |
| 10 | T-V3-C-10 | S-010 | F-018 | 4 | T-FOUNDATION-08, T-V3-B-NOTIF-01, T-V3-B-AUDIT-01 | docs/mocks/2026-05-15_v3/account/S-010-notifications-inbox.html |
| 11 | T-V3-C-11 | S-011 | F-024 | 4 | T-FOUNDATION-08, T-V3-B-SEARCH-01 | docs/mocks/2026-05-15_v3/account/S-011-global-search.html |
| 12 | T-V3-C-12 | S-036 | F-003 | 4 | T-FOUNDATION-08, T-V3-B-AI-01, T-V3-B-AI-02 | docs/mocks/2026-05-15_v3/ai/S-036-ai-employees-org-chart.html |
| 13 | T-V3-C-13 | S-037 | F-003 | 4 | T-FOUNDATION-08, T-V3-B-AI-01, T-V3-B-AI-02 | docs/mocks/2026-05-15_v3/ai/S-037-ai-employee-detail.html |
| 14 | T-V3-C-14 | S-038 | F-002 | 4 | T-FOUNDATION-08, T-V3-B-SKILLS-01, T-V3-B-AI-01 | docs/mocks/2026-05-15_v3/ai/S-038-skill-manager.html |
| 15 | T-V3-C-15 | S-042 | F-013 | 4 | T-FOUNDATION-08, T-V3-B-PR-01, T-V3-B-RBAC-01 | docs/mocks/2026-05-15_v3/client/S-042-client-workspace.html |
| 16 | T-V3-C-16 | S-043 | F-013 | 4 | T-FOUNDATION-08, T-V3-B-PR-01 | docs/mocks/2026-05-15_v3/client/S-043-client-comment.html |
| 17 | T-V3-C-17 | S-056 | F-028 | 4 | T-FOUNDATION-08, T-V3-B-EMAIL-01 | docs/mocks/2026-05-15_v3/email/S-056-email-signup-verify.html |
| 18 | T-V3-C-18 | S-057 | F-028 | 4 | T-FOUNDATION-08, T-V3-B-EMAIL-01 | docs/mocks/2026-05-15_v3/email/S-057-email-password-reset.html |
| 19 | T-V3-C-19 | S-058 | F-028 | 4 | T-FOUNDATION-08, T-V3-B-EMAIL-01 | docs/mocks/2026-05-15_v3/email/S-058-email-invitation.html |
| 20 | T-V3-C-20 | S-059 | F-028 | 4 | T-FOUNDATION-08, T-V3-B-EMAIL-01 | docs/mocks/2026-05-15_v3/email/S-059-email-task-notification.html |
| 21 | T-V3-C-21 | S-060 | F-028 | 4 | T-FOUNDATION-08, T-V3-B-EMAIL-01 | docs/mocks/2026-05-15_v3/email/S-060-email-weekly-summary.html |
| 22 | T-V3-C-22 | S-061 | F-031 | 4 | T-FOUNDATION-08, T-V3-B-EXPORT-01 | docs/mocks/2026-05-15_v3/export/S-061-export-spec-pdf.html |
| 23 | T-V3-C-23 | S-062 | F-031 | 4 | T-FOUNDATION-08, T-V3-B-EXPORT-01 | docs/mocks/2026-05-15_v3/export/S-062-export-delivery-report.html |
| 24 | T-V3-C-24 | S-063 | F-024 | 4 | T-FOUNDATION-08, T-V3-B-SEARCH-01 | docs/mocks/2026-05-15_v3/extras/S-063-search-results.html |
| 25 | T-V3-C-25 | S-064 | F-030 | 4 | T-FOUNDATION-08, T-V3-B-TOKEN-01 | docs/mocks/2026-05-15_v3/extras/S-064-api-tokens.html |

## ファイル境界 (file-level mutex)

- 各 task は `frontend/src/app/<route>/page.tsx` を 1 つだけ新規作成し、衝突なし。
- `frontend/src/api/*.ts` は feature 単位で共有のため、Group B 完了後に touch。同 feature 内の複数 task が並列実行する場合は依存タスクで直列化。
- `frontend/src/app/layout.tsx` / `frontend/src/api/index.ts` は shared_no_concurrent_edit (同 Wave で 1 task のみ touch)。
