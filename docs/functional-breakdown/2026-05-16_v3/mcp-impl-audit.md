# MCP 実装監査レポート (Phase 1.0-fix Wave 0 task E)

- **作成日**: 2026-05-17
- **対象**: F-010a 「MCP サーバー (データ流通)」 / 実装一式
- **目的**: 既存 MCP 実装が **外部公開 (Claude Desktop / Claude Code / 他 MCP client から呼び出される MCP server)** として運用可能か独立判定する.
- **対象ブランチ**: `claude/phase-1-fix-w0-e-mcp-audit`
- **対象ファイル (read-only investigation)**:
  - `backend/routers/mcp_server.py` (529 行 / HTTP+SSE transport)
  - `backend/routers/mcp_tokens.py` (143 行 / token CRUD)
  - `backend/services/mcp_token.py` (205 行 / token service)
  - `backend/mcp_stdio_server.py` (874 行 / stdio transport)
  - `mcp_stdio_server.py` (リポ root / 438 行 / legacy stdio)
  - 5 test files (`tests/test_t_010a_*.py` 計 2707 行)

---

## 1. 実装サーフェス棚卸し (Implementation Surface Inventory)

### 1.1 HTTP transport (`backend/routers/mcp_server.py`, prefix `/mcp`)

| Endpoint | Method | 行 | 役割 | 認証 |
|---|---|---|---|---|
| `/mcp` | GET | mcp_server.py:476-491 | SSE transport. 接続直後に `{jsonrpc:"2.0", method:"server/info", params:{name:"CompanyOS", version:"1.0"}}` を yield. 30s ごと keepalive (`: keepalive\n\n`). | **無認証** |
| `/mcp/tools/list` | POST | mcp_server.py:494-497 | 登録 tool 一覧 (8 tool) を返す | **無認証** |
| `/mcp/tools/call` | POST | mcp_server.py:507-529 | tool 実行. body は `{name, arguments, user_id?}` の dict | **無認証** (user_id は audit ラベル用、認証ではない / mcp_server.py:514-517) |

### 1.2 Token 管理 (`backend/routers/mcp_tokens.py`, prefix `/api/mcp/tokens`)

| Endpoint | Method | 行 | 役割 | 認証 |
|---|---|---|---|---|
| `/api/mcp/tokens` | POST | mcp_tokens.py:55-86 | issue (workspace_id + scopes + expires_in_days + issued_by) | **無認証** |
| `/api/mcp/tokens` | GET | mcp_tokens.py:89-95 | list (workspace_id クエリで絞り込み, token は masked) | **無認証** |
| `/api/mcp/tokens/verify` | POST | mcp_tokens.py:98-119 | token + required_scope + workspace_id を検査 | **無認証** |
| `/api/mcp/tokens/{token_id}` | DELETE | mcp_tokens.py:122-143 | revoke (`actor_user_id` クエリパラメータは audit 用) | **無認証** |

### 1.3 MCP tool セット (HTTP transport `MCP_TOOLS` / mcp_server.py:59-164)

8 tool 登録:

| Tool name | required args | 役割 | 行 |
|---|---|---|---|
| `query_company_db` | sql | SELECT 専用 SQL 実行 | mcp_server.py:60-68, 251-255 |
| `get_kpi` | (none) | 当日 KPI snapshot | mcp_server.py:69-73, 256-258 |
| `list_records` | (folder optional) | スキル出力 MD 一覧 | mcp_server.py:74-81, 259-261 |
| `bf_get_spec` | task_id | task の spec + acceptance_criteria + 紐付き artifact | mcp_server.py:82-96, 263-265, 355-402 |
| `bf_post_progress` | task_id, percent_done | progress event を `audit_logs` に emit (task status は変更しない) | mcp_server.py:97-112, 266-272, 405-430 |
| `bf_attach_artifact` | task_id, artifact_id | `artifacts.task_id` を update | mcp_server.py:113-127, 273-275, 433-468 |
| `bf_request_review` | task_id | reviewer_loop へレビュー依頼 | mcp_server.py:128-148, 276-283, 296-323 |
| `bf_get_review_feedback` | review_id | review record 取得 | mcp_server.py:149-163, 284-286, 326-347 |

### 1.4 stdio transport (`backend/mcp_stdio_server.py`)

`FastMCP("Build-Factory")` (mcp_stdio_server.py:23, 28) でツール 44 件登録. 大別:

- DB / KPI / Records アクセス (mcp_stdio_server.py:33-187, 約 6 tool)
- AI 社員システム連携 (mcp_stdio_server.py:198-447, 約 13 tool)
- Skill 管理 (mcp_stdio_server.py:452-560, 約 9 tool)
- Build-Factory REST API ブリッジ `bf_*` (mcp_stdio_server.py:611-870, 16 tool, BF_API_BASE = `http://localhost:8001` 既定 / mcp_stdio_server.py:581)

44 tool 中 `bf_*` 16 tool は HTTP transport (8 tool) と **重複命名はあるが実装は別** (stdio は REST API 経由、HTTP は service 直叩き).

### 1.5 リポ root の legacy stdio (`mcp_stdio_server.py`)

- 39 tool (browser queue / staff / scoped knowledge), backend を `http://localhost:8000` で叩く (mcp_stdio_server.py:37).
- 用途: Claude Desktop (macOS) から実行する dogfooding 用 (mcp_stdio_server.py:8-18 コメント).
- `tests/test_t_010a_01_mcp_server_spec.py:514-525` (`test_drift_stdio_server_returns_jsonrpc_envelope`) が JSON-RPC 2.0 envelope を root の `mcp_stdio_server.py` に対し検証している (LEGACY_STDIO 変数で参照).

---

## 2. MCP spec バージョン適合 (Spec Compliance)

### 2.1 実装されているプロトコル

| Transport | JSON-RPC 2.0 | protocolVersion | initialize | tools/list | tools/call | notifications/* | error code |
|---|---|---|---|---|---|---|---|
| HTTP (mcp_server.py) | No | No | No | Yes (REST POST) | Yes (REST POST) | No | カスタム (`mcp.<code>`) |
| stdio (backend/mcp_stdio_server.py) | Yes (FastMCP SDK 提供) | Yes (SDK 既定) | Yes (SDK) | Yes (SDK) | Yes (SDK) | Yes (SDK) | SDK 既定 |
| stdio (root mcp_stdio_server.py) | Yes (自前実装) | `2024-11-05` (mcp_stdio_server.py:411) | Yes | Yes | Yes | `notifications/initialized` のみ | `-32601` (method not found) |

### 2.2 公式 MCP spec との差分

公式 MCP spec ([modelcontextprotocol.io](https://modelcontextprotocol.io)) の最新版は **`2025-06-18`** (2025 年 6 月 18 日改訂、それ以前は `2025-03-26` / `2024-11-05`). 主要要素:

- **JSON-RPC 2.0 メッセージ** (`{"jsonrpc":"2.0", "id", "method"|"result"|"error"}`)
- **transport**: stdio または **Streamable HTTP** (SSE 単独ではなく POST + 任意 SSE upgrade、2025-03-26 spec で導入)
- **初期化 handshake**: `initialize` → `initialized` 通知 (capabilities 交換 / protocolVersion negotiation)
- **JSON-RPC method**: `initialize`, `tools/list`, `tools/call`, `prompts/list`, `prompts/get`, `resources/list`, `resources/read`, `resources/subscribe`, `logging/setLevel`, `completion/complete`, `ping`
- **エラー code**: `-32700`/`-32600`/`-32601`/`-32602`/`-32603` (JSON-RPC 標準) + アプリ固有
- **認可**: `2025-03-26` spec で **OAuth 2.1** ベース (resource server, PKCE 必須) を導入
- **session ID**: Streamable HTTP では `Mcp-Session-Id` ヘッダで session 紐付け

#### HTTP transport `backend/routers/mcp_server.py` の差分 (高リスク)

| 観点 | 公式 spec | 本実装 | 評価 |
|---|---|---|---|
| プロトコル | JSON-RPC 2.0 envelope | REST 風 `POST /mcp/tools/list`, `POST /mcp/tools/call` | NG -- 非互換. 公式 MCP client は接続できない |
| initialize handshake | 必須 | 未実装 (SSE で `server/info` を一方的に push のみ / mcp_server.py:481-486) | NG |
| protocolVersion negotiation | 必須 | なし | NG |
| Streamable HTTP | 単一 `POST` endpoint + 任意 SSE | 別 endpoint `/mcp` (SSE) と `/mcp/tools/*` (REST POST) に分割 | NG |
| error code | `-32700` -- `-32603` + アプリ固有 | `{detail:{code, message}}` (HTTPException 構造、`-32601` 未使用) | NG -- JSON-RPC 標準と非互換 |
| 認可 | OAuth 2.1 (推奨) | なし (mcp token は **発行できるが** endpoint 側で検査されない、§4) | NG |
| ping | 必須 | なし | NG |
| `resources/*` | (Optional だが互換性のため期待) | 未実装 | WARN |
| `prompts/*` | (Optional) | 未実装 | WARN |

**結論: HTTP transport は MCP 公式 spec に準拠していない**. 「MCP server endpoint」と書かれているが、実態は **MCP プロトコルの一部 method を REST endpoint として模倣**しただけ. 公式 MCP client (Claude Desktop / Claude Code / mcp-cli) から接続することは **できない**.

#### stdio transport の差分

- `backend/mcp_stdio_server.py` (874 行): `FastMCP` (Anthropic 公式 `mcp` Python SDK) を使うので、protocolVersion / initialize / tools/list / tools/call は SDK が標準対応. spec 適合性は **高い**.
- root `mcp_stdio_server.py` (438 行): JSON-RPC 2.0 envelope を **自前実装** (mcp_stdio_server.py:409-431). `protocolVersion: "2024-11-05"` 固定 (mcp_stdio_server.py:411) -- **古い**. 最新 spec (`2025-06-18`) / 2025-03-26 とは違うので Streamable HTTP 等は使えない.

---

## 3. テストカバレッジ (Test Coverage Report)

### 3.1 実行結果

| コマンド | 結果 |
|---|---|
| `uv run pytest tests/ -k mcp -v` | **179 passed / 9132 deselected / 0 fail / 0 skip** in 17s |
| `uv run pytest tests/test_t_010a_03_bf_review_tools.py` | **0 passed / 19 errors** (Supabase env var 未設定で collection error) |
| `SUPABASE_*=x uv run pytest tests/test_t_010a_03_bf_review_tools.py` | **19 passed** (env stub すれば通る) |
| `uv run pytest --cov=routers.mcp_server --cov=routers.mcp_tokens --cov=services.mcp_token --cov=mcp_stdio_server` | (下表) |

### 3.2 ファイル別 coverage (179 MCP-related tests run)

| Module | Stmts | Miss | Cover | Missing 行 (代表) |
|---|---|---|---|---|
| `routers/mcp_server.py` | 204 | 94 | **54%** | 186, 226-241, 276-288, 304-322, 328-346, 360-401, 410-429, 435-467, 487-489, 511, 524-526 |
| `routers/mcp_tokens.py` | 65 | 3 | **95%** | 103, 118, 130 |
| `services/mcp_token.py` | 100 | 7 | **93%** | 105, 116, 163-165, 188, 199 |
| `mcp_stdio_server.py` | (測定不可) | -- | **0%** (import すらされない) | 全行 |
| **合計** | **369** | **104** | **72%** | -- |

### 3.3 重要なカバレッジ欠落 (HTTP transport)

`routers/mcp_server.py` の 54% は CLAUDE.md §5.3 が要求する Phase 1 ゲート 70% を満たしていない. Missing 領域:

- **mcp_server.py:226-248** : `bf_request_review` の入力 validation 分岐 (`target_artifact_ids` の各 chunk / `summary` 長さ).
  - `tests/test_t_010a_03_bf_review_tools.py` が無効化されているため、本来カバーされる箇所が外れている.
- **mcp_server.py:296-347** : `_bf_request_review` / `_bf_get_review_feedback` 実体 (reviewer_loop 経由 / 404/500 fallback).
- **mcp_server.py:355-468** : `_bf_get_spec` / `_bf_post_progress` / `_bf_attach_artifact` の **本物の DB アクセス実装**. 全テストが `monkeypatch.setattr(mcp, "_bf_get_spec", fake_...)` で **実装ごと差し替えている** (test_t_010a_02_bf_mcp_tools.py:97-99, test_t_010a_02_mcp_tools_spec.py:157-159).
  - **本物の SQLite 経路は 1 行も覆われていない**. 本番で動く保証は test だけからは得られない.
- **mcp_server.py:487-489** : SSE keepalive ループ. 性質上 unit test が困難.
- **mcp_server.py:524-526** : `handle_tool_call` 内 catch-all 500 経路.

### 3.4 stdio server (`backend/mcp_stdio_server.py` / 874 行) のテスト不在

- 44 tool 中、unit/integration テストが **完全に存在しない**. test_t_010a_01_mcp_server_spec.py:114-116 が「ファイル存在チェック」のみ.
- `bf_*` 16 tool は `_bf_request` (mcp_stdio_server.py:584-604) 経由で `BF_API_BASE` の REST を叩くが、その経路の挙動 (200 / 4xx / timeout / connection refused) は一切テストされていない.
- mcp_stdio_server.py:33-187 (DB query / KPI / records) は **build.db に直接 sqlite3.connect** (mcp_stdio_server.py:47, 67, 124, 176, 308 等). 行レベルの permission・workspace スコープなし.

### 3.5 テストされていない動作

1. **本物の DB 経路** (`_bf_get_spec` / `_bf_post_progress` / `_bf_attach_artifact` の SQL 部) -- 全 BF tool テストで fake に差し替えられている.
2. **stdio server 全 44 tool**.
3. **mcp token と mcp tool call の連動** -- token を発行しても tool call で参照されない (実装が無いので test も無い、§4 参照).
4. **同時並行リクエスト** -- race condition / lock 周りなし. `services/mcp_token.py:56` の `_tokens: dict` は process-local in-memory store であり、複数 worker / restart で消える.
5. **token 期限切れ境界** -- `services/mcp_token.py:159-165` の `datetime.strptime` parse 失敗時に **`except Exception: pass` で例外を握りつぶし無条件 valid 扱い**にする経路 (Line 164-165). expire 表記が壊れたとき token が無期限化する.
6. **SSE 長時間接続切断** -- keepalive 30s ループの client 切断検知が無い (mcp_server.py:480-489).

---

## 4. マルチテナント安全性 (Multi-tenant Safety)

### 4.1 結論: **HIGH RISK**

`/mcp/tools/call` は **どの workspace_id にも紐付かないし、token も検査しない**. 任意の client から hit すれば全 DB / 全 record / 全 task / 全 artifact / 全 review に access できる.

### 4.2 根拠 (コード引用)

- mcp_server.py:507-529 (`tools_call` 関数):
  - body から `user_id` を取り出して空文字検査 (Line 514-517) のみ.
  - **`Authorization` / `Bearer` / mcp token / `verify_token` の呼び出しが一切ない**.
  - **`workspace_id` 引数も無い**.
- mcp_server.py:251-288 (`handle_tool_call`):
  - 5 つの BF tool は `task_id` だけで identify, workspace 境界チェックなし.
- mcp_server.py:355-402 (`_bf_get_spec`):
  - `SELECT ... FROM tasks WHERE id=?` (Line 367) で **workspace_id 条件なし**. 他 workspace の task でも取れる.
- mcp_server.py:443-457 (`_bf_attach_artifact`):
  - `SELECT id FROM tasks WHERE id=?` (Line 447) + `UPDATE artifacts SET task_id=? WHERE id=?` (Line 453-455) も **workspace_id 条件なし**. cross-workspace な artifact 移動が可能.
- mcp_server.py:190-202 (`query_company_db` validation):
  - SELECT / WITH / PRAGMA のみ許可 (read-only) だが、**SELECT 範囲に workspace_id フィルタが無い** -- 任意のテーブルを全件取得可能.
- db/queries.py:161-170 (`run_query`):
  - 純粋に渡された SQL を `aiosqlite.connect(DB_PATH)` (build.db) で実行. **テナント分離なし**.

### 4.3 token サービスは workspace スコープを持つが、結線されていない

- `services/mcp_token.py:91-136` の `issue_token(workspace_id, scopes, ...)` は workspace 単位で token を発行する.
- `services/mcp_token.py:139-182` の `verify_token(token, required_scope, workspace_id)` は workspace mismatch を検出できる.
- **しかし `routers/mcp_server.py` から `verify_token` の呼び出しが 0 件**. token を発行しても誰も検査しない. つまり token システムは **見せかけ**.

### 4.4 RLS 状況

- F-010a の `error_paths` に「RLS 違反→403」と書かれている (features.json:14, features.json v3 F-010a) が、**RLS を適用するコードパスが存在しない**.
- Supabase migrations にも MCP 用 RLS policy はおそらく無い (今回の audit は read-only なので grep で確認のみ -- 後続タスクで cross-check すること).

### 4.5 stdio server (`backend/mcp_stdio_server.py`) も同様

- `query_company_db` / `get_company_kpi` / `bf_*` どれも workspace_id を取らない.
- ただし stdio は **同一マシン上で動く Claude Desktop からの単一ユーザ前提**なので Phase 1 dogfooding ならリスク低. Phase 2 で SaaS として公開するなら HTTP transport 同様の問題.

---

## 5. レートリミット / 濫用防止

### 5.1 結論: **存在しない**

- `routers/mcp_server.py` / `routers/mcp_tokens.py` / `services/mcp_token.py` / `mcp_stdio_server.py` に `rate_limit`, `RateLimiter`, `slowapi`, `throttle` のいずれの記号も存在しない (grep -i で 0 件).
- 他 router (`backend/routers/auth.py:54` の `get_rate_limiter`, `backend/routers/accounts.py:270` の `check_invitation_rate_limit` 等) は rate limit を入れているので、infrastructure は存在する.
- F-010a v3 features.json には `outputs_4xx.429: "rate limit"` と書かれている -- spec ↔ impl drift.

### 5.2 SSE keepalive の DoS リスク

- `/mcp` SSE (mcp_server.py:480-489) は接続数上限なし. 大量同時接続で worker thread を全て占有可能.
- 1 connection = 30s keepalive ループで生き続ける. 切断検知なし.

### 5.3 SQL injection / DoS

- `query_company_db` (mcp_server.py:251-255, db/queries.py:161-170) は SELECT に限定するが、`SELECT * FROM huge_table` や `WITH RECURSIVE CTE` で **長時間 / 大量メモリのクエリ**が走り得る. SQLite なので process が固まる.
- query timeout / row limit / cost-based gating なし.

---

## 6. OpenAPI / 仕様 parity

### 6.1 OpenAPI に存在する MCP endpoint (`docs/api-design/2026-05-16_v3/openapi.yaml`)

| Path / Method | OpenAPI 行 | OpenAPI の implementation_path | 実装ファイル | drift |
|---|---|---|---|---|
| `POST /api/mcp/tokens` | openapi.yaml:12622-12725 | `backend/routers/mcp.py::post_mcp_tokens` | `backend/routers/mcp_tokens.py:55` | **ファイル名違い** (mcp.py vs mcp_tokens.py) + body 構造違い |
| `GET /api/mcp/tokens` | openapi.yaml:12726-12797 | `backend/routers/mcp.py::get_mcp_tokens` | `backend/routers/mcp_tokens.py:89` | **同上** |
| `DELETE /api/mcp/tokens/{token_id}` | openapi.yaml:12800-12860+ | `backend/routers/mcp.py::delete_mcp_tokens_by_token_id` | `backend/routers/mcp_tokens.py:122` | **同上** |

### 6.2 OpenAPI に存在しない MCP endpoint

実装にはあるが OpenAPI には書かれていない:

- `GET  /mcp` (SSE) -- mcp_server.py:476
- `POST /mcp/tools/list` -- mcp_server.py:494
- `POST /mcp/tools/call` -- mcp_server.py:507
- `POST /api/mcp/tokens/verify` -- mcp_tokens.py:98

-- **4 endpoint が spec から drift**. 加えて issue token の body 構造が違う (OpenAPI: `name/scopes/expires_at` / 実装: `workspace_id/scopes/expires_in_days/issued_by` / mcp_tokens.py:42-46) -- SDK 型自動生成すると壊れる.

### 6.3 spec ↔ impl drift 要因

1. features.json (v3) F-010a `audit_logs` で `mcp_token_issued` / `mcp_tool_invoked` を declare. 実装は `mcp_tokens.issued` / `mcp_tokens.revoked` / `mcp.tool.called` (= 別名). 命名不整合.
2. features.json v3 で `related_entities` に `E-006 ApiKey` を載せているが、`entities.json` の E-006 は `WorkspaceInvitation` (entities.json:532-535). MCP token を管理する entity が **エンティティ定義に無い**.
3. openapi.yaml の error_seeds で `429 RATE_LIMITED` を declare. 実装には rate limiter が無い (§5).

---

## 7. TODO / placeholder マーカー

`backend/routers/mcp_server.py` / `backend/routers/mcp_tokens.py` / `backend/services/mcp_token.py` / `backend/mcp_stdio_server.py` / 6 test files から `TODO` / `FIXME` / `XXX` / `HACK` / `pass` を検索:

| ファイル:行 | マーカー | 文脈 |
|---|---|---|
| services/mcp_token.py:34 | `pass` | `class MCPTokenError(RuntimeError): pass` (空 exception 定義 / 問題なし) |
| services/mcp_token.py:163-165 | `except Exception: pass` | **token 期限 parse 失敗を握りつぶす -- token が事実上無期限化** (要修正) |
| routers/mcp_server.py:387 | `except Exception: pass` | artifacts 取得 best-effort. spec 取得時に artifacts が取れなくても 500 にしない (許容範囲) |

`TODO` / `FIXME` / `XXX` / `HACK` は **0 件** (3 module + 5 test file).

---

## 8. 公開準備度 verdict

### 結論: **NOT-READY** (外部 SaaS / public MCP server として公開不能)

### 8.1 致命的 (block-public-launch)

| # | 問題 | 引用 | 影響 |
|---|---|---|---|
| F1 | **HTTP transport が MCP 公式 spec に準拠していない** (JSON-RPC 2.0 envelope なし / initialize handshake なし / protocolVersion negotiation なし) | mcp_server.py:476-529 § 2.2 | 公式 MCP client から接続できない. 「MCP server」と名乗っているが実態は REST 風 API. |
| F2 | **認証 / 認可が `/mcp/tools/call` に一切ない** | mcp_server.py:507-529 § 4.2 | 任意の attacker から全 tool が呼べる. mcp token も発行しても無視. |
| F3 | **マルチテナント分離なし** (workspace_id を引数で取らず、SELECT/UPDATE で workspace 条件もなし) | mcp_server.py:367, 447-455 § 4.2 | 1 client が全 workspace の task / artifact / DB row を read/write 可能. |
| F4 | **token 期限 parse 失敗時に無条件 valid** | services/mcp_token.py:159-165 | 改ざんで永久 token 化が可能. |
| F5 | **rate limiting なし** | § 5 | 単純な DoS (`SELECT * FROM huge_table` の連発 / SSE 大量接続) で落ちる. |
| F6 | **OpenAPI と impl drift** (4 endpoint 未収載 / 3 endpoint の path・body 構造 mismatch) | § 6 | SDK 型自動生成 / contract test が機能しない. |

### 8.2 重大 (block-Phase-2-promotion)

| # | 問題 | 引用 | 影響 |
|---|---|---|---|
| M1 | **HTTP transport coverage 54%** (Phase 1 ゲート 70% 未達) -- 本物の DB 経路がテストされていない | § 3.2-3.3 | regression 防止能力が低い. |
| M2 | **stdio transport coverage 0%** (44 tool / 874 行が完全に未テスト) | § 3.4 | 「Claude Desktop から繋がる」だけが手動確認手段. |
| M3 | **token store が in-memory** -- process 再起動で消える, multi-worker / multi-process で共有不可 | services/mcp_token.py:55-59 | 本番運用に耐えない. RLS つき DB 永続化が必須. |
| M4 | **bf_review tool テストが Supabase env で error する** (dev 環境では一切実行できない) | § 3.1 | CI / 開発時の confidence が下がる. |
| M5 | **F-010a の error_paths "RLS 違反→403" が実装に存在しない** | § 4.4, § 6.3 | spec / impl の核心が drift. |

### 8.3 軽微 (defer-to-polish)

| # | 問題 | 引用 |
|---|---|---|
| L1 | `routers/mcp.py` の名前で OpenAPI が参照しているが実体は `mcp_tokens.py` (file rename or spec fix) | § 6.1 |
| L2 | features.json v3 が `E-006 ApiKey` を参照するが entities.json E-006 は `WorkspaceInvitation` | § 6.3 |
| L3 | audit event 名の命名不一致 (`mcp_token_issued` vs `mcp_tokens.issued`) | § 6.3 |

---

## 9. アクション項目 (verdict != READY のため必須)

下記は将来 Wave で着手する task. すべて 2-6 h サイズで切り出してある (各タスク独立). 連番は `T-MCP-W1-*` (Wave 1) / `T-MCP-W2-*` (Wave 2) で割当.

### Wave 1 (block-public-launch を解消、Phase 1 完走を目指す)

1. **T-MCP-W1-01** (3-4 h) -- `/mcp/tools/call` に `Authorization: Bearer <mcp_token>` ヘッダ検査を追加し、`services.mcp_token.verify_token` を呼び出して `workspace_id` + `required_scope` を強制. unauthorized -> 401, scope mismatch -> 403. § 4.2 / § 4.3.
2. **T-MCP-W1-02** (3 h) -- `_bf_get_spec` / `_bf_post_progress` / `_bf_attach_artifact` の SQL に `AND workspace_id = ?` を追加し、token から取れる workspace_id で絞り込む. cross-workspace アクセスを 404 化. § 4.2.
3. **T-MCP-W1-03** (2 h) -- `services/mcp_token.py:159-165` の `except Exception: pass` を削除し、parse 失敗を `invalid_expires_at` で reject. § 7.
4. **T-MCP-W1-04** (4 h) -- MCP token を in-memory ではなく Supabase の RLS つき新規 table `mcp_tokens` に永続化. 多 worker / 再起動でも token が生き続けるように. § 8.2 M3.
5. **T-MCP-W1-05** (3 h) -- `/mcp/tools/call` と `/api/mcp/tokens` 系に rate limiter (existing `get_rate_limiter`) を導入. token 単位 / IP 単位の hybrid 制限. § 5.
6. **T-MCP-W1-06** (2 h) -- `query_company_db` に SQL timeout (`SET statement_timeout` 相当 / aiosqlite では `db.execute_async` cancel) と row limit (e.g. 10000) を強制. § 5.3.
7. **T-MCP-W1-07** (3-4 h) -- OpenAPI に `/mcp` (SSE), `/mcp/tools/list`, `/mcp/tools/call`, `/api/mcp/tokens/verify` の 4 endpoint を追記し、`x-bf-implementation-path` を `backend/routers/mcp_server.py` / `mcp_tokens.py` に修正. spec ↔ impl の drift を closure. § 6.

### Wave 2 (block-Phase-2-promotion を解消、SaaS 公開準備)

8. **T-MCP-W2-01** (5-6 h) -- HTTP transport を **MCP 公式 spec (`2025-06-18` Streamable HTTP)** に書き換え. JSON-RPC 2.0 envelope, `initialize` / `tools/list` / `tools/call` / `ping`, `Mcp-Session-Id`. 既存 `/mcp/tools/list` (REST POST) は backwards-compat 用に 1 release だけ deprecated として残す. § 2.2.
9. **T-MCP-W2-02** (2-3 h) -- `mcp_stdio_server.py` (backend / root) に unit test (44 + 39 tool 別の dispatch matrix, error envelope) を追加. coverage 0% -> 70%+. § 3.4.
10. **T-MCP-W2-03** (3 h) -- bf_review tools test (test_t_010a_03_bf_review_tools.py) を Supabase env なしで動くよう、`services.supabase_client` の import を遅延化 (lazy / conftest stub). § 3.1.
11. **T-MCP-W2-04** (2-3 h) -- `routers/mcp_server.py` 真の DB 経路 (`_bf_*` impl) の integration test (sqlite in-memory) を追加. 現在の monkeypatch fake 依存を解消. § 3.3.
12. **T-MCP-W2-05** (3 h) -- Entity 定義に `E-???  McpToken` (table `mcp_tokens`) を正式追加し、features.json v3 F-010a の `related_entities` を修正. § 6.3.
13. **T-MCP-W2-06** (2 h) -- audit event 名を統一 (`mcp_token_issued` / `mcp_tool_invoked` で spec / impl 一致). § 6.3 / § 8.3 L3.
14. **T-MCP-W2-07** (3-4 h) -- OAuth 2.1 (Resource Server プロファイル) を MCP HTTP transport にオプションで実装. mcp token (opaque) と OAuth access token のどちらでも認証できるように. SaaS 公開時の Claude Desktop 連携をスムーズに. § 2.2.
15. **T-MCP-W2-08** (2 h) -- SSE 接続上限・client disconnect 検知・keepalive cancel handling を追加 (`/mcp` endpoint). § 5.2.

### 合計サイズ

- Wave 1: 7 タスク / 約 20-23 h.
- Wave 2: 8 タスク / 約 21-25 h.

---

## 10. 監査担当者の補足

- 「Phase 9 = 187/187 完走」と CLAUDE.md §2 に書かれているが、**MCP 実装は (1) HTTP transport の公式 spec 非準拠、(2) 認証なし、(3) RLS なし、(4) coverage 54%、という 4 つの致命的問題** を抱えたまま「完走」とマークされている. F-010a の error_paths に明記された「auth 失敗 -> 401」「RLS 違反 -> 403」は **AC として書かれているだけで実装に存在しない**.
- 本監査は read-only で実行し、`mcp_server.py` / `mcp_token.py` / `mcp_stdio_server.py` / 5 test files をいずれも変更していない.
- 次の着手は **T-MCP-W1-01** (Bearer 認証導入) と **T-MCP-W1-02** (workspace_id 絞り込み) を同 PR で行うのが安全. 認証だけ入れて scope 絞りが無いと「token を持つ workspace_A 利用者が workspace_B の task を取れる」状態が残るため.

---

**Audit by**: Claude (Build-Factory Phase 1.0-fix Wave 0 task E)
**Branch**: `claude/phase-1-fix-w0-e-mcp-audit`
**Files unchanged**: backend MCP 実装一式 (本 audit は doc 追加のみ).
