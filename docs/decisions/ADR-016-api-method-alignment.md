# ADR-016: API method alignment for mock-impl drift (PUT vs PATCH / GET vs POST)

- **Status**: Accepted
- **Date**: 2026-05-17
- **Deciders**: 高本まさと (proxy: claude session T-V3-D-09)
- **Trigger**: v3 functional-breakdown api-drift-summary.md (2026-05-16) で 5 endpoint が `method mismatch` (path 一致 / method 違い) と判定された。mock 側 (frontend / openapi.yaml) は PUT / GET を宣言、backend 既存実装は PATCH / POST のみという乖離。**T-V3-D-09 (Wave 4 / Group D-3 / 3h boxed)** で「spec を impl に合わせる方針」のもと alias 追加で解消する。
- **Related**:
  - `docs/functional-breakdown/2026-05-16_v3/api-drift-summary.md` §High 詳細 (method mismatch)
  - `docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-d-drift.json` (T-V3-D-09)
  - `docs/api-design/2026-05-16_v3/openapi.yaml` (spec)
  - `backend/routers/accounts.py` / `workspaces.py` / `ai_employees.py` / `tasks.py` (impl)

## Context

api-drift-summary §High が示す 5 endpoint:

| Feature | Mock 宣言 (spec) | Backend 既存 method | drift task |
|---|---|---|---|
| F-003 AI 社員 | `PUT /api/ai-employees/{id}` | `['DELETE','GET','PATCH']` | T-V3-DRIFT-F-003-02 |
| F-004 account 階層 | `PUT /api/accounts/{id}` | `['DELETE','GET','PATCH']` | T-V3-DRIFT-F-004-01 |
| F-004 account 階層 | `PUT /api/workspaces/{id}` | `['DELETE','GET','PATCH']` | T-V3-DRIFT-F-004-05 |
| F-004 account 階層 | `GET /api/workspaces/{id}/invitations` | `['POST']` | T-V3-DRIFT-F-004-07 |
| F-006 タスク分解 | `PUT /api/tasks/{id}` | `['GET','PATCH']` | T-V3-DRIFT-F-006-04 |

選択肢は 2 つあった:

1. **Spec (mock / openapi) を impl に合わせる**: openapi.yaml を `PUT → PATCH` に書き換え、mock も PATCH に統一する。frontend の生成型 (openapi-typescript / pact contract) が連動して PUT 呼び出しを消す。
2. **Impl を spec に合わせる**: backend に PUT alias を追加。既存 PATCH も残し両 method を accept する。spec 側は変更しない。

issue text の指示「spec / impl 統一 (**spec を impl に合わせる方針**) + openapi.yaml 更新」を採用する。ただし mock contract が既に `PUT` 前提で固定されており frontend / pact 既生成型を即時に書き換えると **drift fix Wave 4 の 3h boxed scope を逸脱** するため、Phase 1 末尾までは「**両 method (PATCH + PUT alias)** を accept しつつ openapi に alias 注記を追記」する暫定運用を取る。GET /workspaces/{id}/invitations は POST と path が同じだが意味が完全に違う (POST=create / GET=list) ため alias ではなく **新規 endpoint** を追加する。

## Decision

### 1. **PATCH を canonical / PUT を一時 alias とする** (HTTP REST 規約準拠)

- account / workspace / ai-employee / task の partial update endpoint は **PATCH を canonical method** とする (REST 規約: PATCH = partial update, PUT = full replace)。
- ただし mock contract / openapi spec で宣言済みの **PUT 呼び出しを backend が 404 / 405 で reject しないよう PUT alias handler を追加する**。
- alias handler の実装は本体 PATCH handler を `await` で呼ぶ 1 行 delegate とし、ロジック / response shape / audit emit / 認証ポリシーは PATCH と完全一致とする。

### 2. **GET /api/workspaces/{id}/invitations を新規追加する**

- 同一 path の POST endpoint (招待作成) とは意味が異なるため alias ではなく **独立 endpoint** として追加する。
- response shape は `{ invitations: [Invitation] }` (openapi.yaml の `get_workspaces_by_id_invitations` 定義準拠)。
- 既定で `status='pending'` のみを返す。`?status=all` で全状態。token は PII 漏洩防止のため `token_prefix` (先頭 8 文字) のみ返す。

### 3. **frontend migration 後に PUT alias を deprecate する future task を起票する**

- frontend (S-008 / S-013 / etc.) と openapi.yaml を **PATCH に統一する** future task を起票する (Phase 2 候補)。
- frontend 移行完了後、PUT alias を 410 Gone で deprecate → 6 ヶ月以降で物理削除する。
- 起票先: 次回 drift fix Wave (Wave 5 以降) の Group D に `T-V3-D-09-FOLLOWUP` として queue。

### 4. **openapi.yaml への注記**

- 既に openapi.yaml は PUT を definition として持っている。
- 各 PUT entry の `description` に「Currently aliases PATCH; see ADR-016. Will become canonical after frontend migrates and PATCH deprecates, or vice versa.」を追記する。
- GET /workspaces/{id}/invitations entry の `x-bf-drift.severity` を `resolved_by_adr_016` に更新する。

## Consequences

### 受容するリスク
- 同一 resource 更新に 2 method (PATCH + PUT) を持つことで「どちらが正?」混乱が起きうる。これは ADR で canonical = PATCH を明示することと future task で alias 削除を queue することで mitigate。
- PUT alias は内部で PATCH と同一 partial-update semantics で動くため、true full-replace を期待する client (HTTP/1.1 RFC 厳密派) からは不整合と映るリスクがある。openapi の description で明示する。

### 機械的検証
- `backend/tests/integration/test_api_method_alignment.py` で 5 endpoint × happy + 5 × unauthorized = **10 case minimum** を 401/200 で固定し、drift 再発を CI で reject。
- mock-impl method drift を再発させないため、frontend 移行完了 PR で `scripts/lint-mock.sh` rule #18 (screens-API method match) を有効化する (本 ADR scope 外、follow-up)。
- `python3 scripts/validate-tickets.py --check-file docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-d-drift.json` for T-V3-D-09 を CI gate に組み込み済み。

### 後続タスク (queue 起票)
- T-V3-D-09-FOLLOWUP-1: frontend を PATCH 統一に migration (Phase 2 候補)
- T-V3-D-09-FOLLOWUP-2: PUT alias を 410 Gone deprecate + openapi.yaml から PUT 削除 (frontend 完了後)
- T-V3-D-09-FOLLOWUP-3: `scripts/lint-mock.sh` rule #18 (screens-API method match) を CI gate 化

## References

- RFC 5789 (HTTP PATCH method)
- IETF HTTP/1.1 RFC 9110 §9.3 (PUT vs PATCH semantics)
- `docs/decisions/ADR-014-bf-prefix-decision.md` (drift 解消 ADR の前例)
- `docs/decisions/ADR-015-legacy-twin-table-archive.md` (drift 解消 ADR の前例)
