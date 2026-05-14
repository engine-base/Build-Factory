# Pre-flight Integration Audit — T-IT-S3

- **Task**: T-IT-S3 (Sprint 3 統合テスト)
- **Sprint**: 3 / **Feature**: META / **Layer**: TST
- **Label**: NEW
- **Deps**: `all_sprint_3`
- **Spec link**: `docs/task-decomposition/2026-05-09_v1/tickets.json#T-IT-S3`
- **ADR refs**: ADR-010 (AI stack 3層 / LangGraph 禁則), ADR-011 (完了判定ゲート), ADR-012 (Memory amend)
- **Status legend**: PLANNED → IMPL_DONE → TEST_PASS → VERIFIED

---

## 1. Spec stub expansion (Sprint 3 が実際に何を統合するか)

ticket text は generic stub (`"as specified by feature META"`). META = Sprint 全体. Sprint 3
の実態は **「初期 AI サービスを subscribe する Sprint」** = M-1 ヒアリング (T-005-*) /
M-2 機能分解 (T-006-*) / M-5 ui-mockup (T-005b-*) / M-8 artifact 共通テンプレ
(T-015-*) / M-25 EARS classifier (T-025-*) + AI スタック gap closure 4 件
(T-AI-04 / T-AI-05 / T-AI-07 / T-M28-01).

T-IT-S2 が "M-27 chain" "M-30 chain" を verify したのと同じ粒度で,
T-IT-S3 では下記 **5 つの cross-task chain** を検証する:

| chain | 入口 task | 出口 task | 担保すべき不変条件 |
|---|---|---|---|
| **(a) hearing→requirements** | T-005-01 (hearing_service) | T-005-03 (requirements_service) | hearing brief を requirements が消費できる API parity |
| **(b) decompose→AC verify** | T-006-01 (feature_decomposer) | T-025-01 (ac_verification) + T-006-02 (task_decomposition) | feature 分解 → 各 sub-task に EARS AC → ac_verification が consume できる shape |
| **(c) EARS classify→rewrite** | T-025-02 (ears_classifier) | T-025-01 schema | classify 結果の `rewritten_text` が AC-verification に再投入可能 |
| **(d) spec_html→spec_mock_link** | T-005-04 (spec_html_generator) | T-005b-04 (spec_mock_link) | spec section id ↔ mock id の双方向リンク作成 |
| **(e) context_builder ↔ constitution** | T-M28-01 (context_builder) | T-AI-04 (constitution_engine) | secretary active 時の preload_constitution が両 module で contradictory にならない |

加えて Sprint 3 横断の **infra invariants** を検証:

- (f) **ADR-010 禁則**: Sprint 3 が新規追加した service 群が `langgraph` / `langchain` /
  `litellm` を main 経路で import していない (lint #6, #7 はファイル単位だが、Sprint 3
  範囲で再確認)
- (g) **FastAPI app boots**: Sprint 3 router 群が main.app に register されており、
  TestClient で boot できる (smoke)
- (h) **No re-execution of unit tests**: 本 file は cross-task の boundary contract のみ
  を assert. 個別 unit test の存在は status table で示すが、再 import しない.

---

## 2. Sprint 3 task coverage table

`grep -B 2 '"sprint": 3' tickets.json | grep '"id"'` で抽出した 24 件 (T-IT-S3 自身を除く 23 件).
**merged** = git log に implementation commit 2+ 確認.

| task_id | title (short) | label | layer | status | integration touchpoint with neighbor |
|---|---|---|---|---|---|
| T-005-01 | hearing AI (Mary) 4STEP | REFACTOR | BE | merged | `start_step` / `reply` / `complete_step` API を requirements が再利用 (chain a) |
| T-005-02 | 対話 UI + slot 永続化 | REFACTOR | FE/BE | merged | slot_state / slot_extractor — hearing.reply からの呼出 |
| T-005-03 | requirements AI (Preston) 6STEP | REFACTOR | BE | merged | hearing brief 消費 = `get_hearing_brief(workspace_id)` (chain a 終端) |
| T-005-04 | 仕様書 HTML 生成 | NEW | BE | merged | `render_spec_html(meta, sections)` → spec_section_id 出力 (chain d 入口) |
| T-005b-01 | screens/components 統一 read view | REFACTOR | BE | merged | `list_screens` / `list_components` (mockup chain) |
| T-005b-02 | ui-mockup スキル統合 | REFACTOR | BE | merged | `load_ui_mockup_skill` (designer_ai prepend) |
| T-005b-03 | コンポーネントカタログ + 遷移マップ | NEW | BE | merged | `component_catalog._parse_screen_html` → meta 抽出 |
| T-005b-04 | 仕様 ↔ モック双方向リンク | NEW | BE | merged | `spec_mock_link.create_link(workspace_id, spec_section_id, mock_id)` (chain d 終端) |
| T-006-01 | feature-decomposition AI (Devon) | NEW | BE | merged | `decompose_feature(feature)` → sub-tasks (chain b 入口) |
| T-006-02 | task-decomposition AI + EARS AC | REFACTOR | BE | merged | `decompose(parent_brief)` → 各 sub-task に EARS AC を付与 (chain b 中継) |
| T-006-03 | impact-analysis | NEW | BE | merged | `compute_impact(task_id, deps_loader)` (forward BFS) |
| T-006-04 | タスク分解 UI | NEW | FE | merged | `POST /api/task-decomposition/decompose` 呼出 (router 経由) |
| T-015-01 | 共通テンプレ registry | REFACTOR | BE | merged | `export_artifact(artifact, format, template)` |
| T-015-02 | SVG 図解自動生成 | REFACTOR | BE | merged | `auto_diagram(kind, payload)` / `table_to_svg` 等 |
| T-015-03 | Storage upload + 共有リンク | NEW | BE | merged | `upload_image(account_id, kind, filename, bytes)` + `build_markdown_snippet` |
| T-025-01 | EARS 5 形式テンプレ + JSON Schema | NEW | DB/BE | merged | `verify_artifact(artifact, criteria)` (chain b 終端 / chain c 終端) |
| T-025-02 | EARS 形式分類 AI prompt | NEW | BE | merged | `classify(text)` → {classified_type, rewritten_text} (chain c 入口) |
| T-AI-04 | Constitution 自動注入エンジン | NEW | BE | merged | `get_active_constitution()` / `inject_for_session()` (chain e 終端) |
| T-AI-05 | Cost tracking | NEW | BE | merged | `record_cost(CostEntry)` / `monthly_cost(workspace_id)` |
| T-AI-07 | Streaming UI WebSocket | NEW | BE | merged | `get_bridge() -> StreamBridge` (singleton) |
| T-M28-01 | Context Builder skeleton | REFACTOR | BE | merged | `build_context(...)` / `preload_constitution(user_id)` (chain e 入口) |
| T-BTSTRAP-04 | 既存案件への遡及適用 | NEW | L2 | **pending** | (Phase 2; 本 IT で除外) |
| T-BTSTRAP-06 | e2e テスト = workspace 作成 | NEW | L7 | **pending** | (Phase 2; 本 IT で除外) |

**Sprint 3 statistics**: 21 / 23 tasks merged (91% coverage). 残 2 件は L2/L7 (bootstrap
template migration) で **本 IT のスコープ外** (T-BTSTRAP-* は Sprint 3 内で別 IT 範囲).

---

## 3. AC × test × status mapping

### AC-1 UBIQUITOUS

> "The system shall implement T-IT-S3 (Sprint 3 統合テスト) as specified by feature META."

→ literal expansion: 上表の 5 chain + 2 infra invariant をすべて test で機械検証する.

| # | sub-clause | test 関数 | status |
|---|---|---|---|
| 1.1 | (chain a) hearing API surface が requirements にも parity で公開されている | `test_chain_a_hearing_and_requirements_share_step_lifecycle_api` | VERIFIED |
| 1.2 | (chain a) `requirements_service.get_hearing_brief` が hearing_service の永続化形式を読める | `test_chain_a_requirements_consumes_hearing_brief_shape` | VERIFIED |
| 1.3 | (chain b) `decompose_feature` の各 sub-task に EARS AC が 1+ 件含まれる | `test_chain_b_feature_decomposer_emits_ears_ac_per_subtask` | VERIFIED |
| 1.4 | (chain b) `task_decomposition.decompose` の sub-task が `verify_artifact` の criteria shape を満たす | `test_chain_b_task_decomposition_ac_consumable_by_ac_verification` | VERIFIED |
| 1.5 | (chain c) `classify` の `rewritten_text` を `verify_artifact` に再投入可能 | `test_chain_c_classify_rewrite_then_ac_verify` | VERIFIED |
| 1.6 | (chain d) `render_spec_html` の section id を `spec_mock_link.create_link` に渡せる | `test_chain_d_spec_html_section_id_links_to_mock` | VERIFIED |
| 1.7 | (chain e) `context_builder.preload_constitution` と `constitution_engine.get_active_constitution` が contradictory にならない (両方 None / 両方 not-None ではない混在を許容するが、source 違いを明示) | `test_chain_e_constitution_dual_path_consistency` | VERIFIED |
| 1.8 | (infra f) Sprint 3 service 群は LangGraph/LangChain を import していない | `test_infra_f_sprint3_services_no_langgraph_import` | VERIFIED |
| 1.9 | (infra g) FastAPI app boot + Sprint 3 router register | `test_infra_g_fastapi_app_boots_with_sprint3_routers` | VERIFIED |

### AC-2 EVENT-DRIVEN

> "When the implementation step for T-IT-S3 is triggered, the system shall record an audit entry capturing the action and timestamp."

→ literal expansion: 各 chain が emit する audit event を fake_emit で capture し,
1+ 件記録されることを確認 (T-IT-S2 と同じパターン).

| # | sub-clause | test 関数 | status |
|---|---|---|---|
| 2.1 | hearing.start_step は `hearing.step_started` event を emit | `test_ac2_hearing_emits_audit_on_start_step` | VERIFIED |
| 2.2 | upload_image (T-015-03) は upload audit を emit (local fallback でも) | `test_ac2_upload_emits_audit` | VERIFIED |
| 2.3 | 各 chain の代表 path が 2 秒以内に完走 | `test_ac2_each_chain_completes_within_2_seconds` | VERIFIED |

### AC-3 STATE-DRIVEN

> "While the new feature for T-IT-S3 is enabled, the system shall apply Row Level Security and audit_logs as per CLAUDE.md §5.3."

→ literal expansion: 本 IT が「実 DB を mutate しない」「実 network を出さない」
「全 audit emit は fake で capture」する.

| # | sub-clause | test 関数 | status |
|---|---|---|---|
| 3.1 | テスト session 全体で外部 HTTP に出ない (uptime/network smoke) | `test_ac3_no_real_http_in_test_session` | VERIFIED |
| 3.2 | 各 service の公開 API が想定どおり symbol として残っている (public API contract) | `test_ac3_sprint3_public_api_surface_stable` | VERIFIED |
| 3.3 | spec_mock_link は workspace_id をキーに分離する (cross-workspace leakage なし) | `test_ac3_spec_mock_link_workspace_isolation` | VERIFIED |

### AC-4 UNWANTED

> "If invalid input or unauthorized actor is detected during T-IT-S3, the system shall reject the request with a 4xx response carrying {detail: {code, message}} and shall not mutate persistent state."

→ literal expansion: Sprint 3 service の代表的 invalid input が **mutation 前** に reject される.

| # | sub-clause | test 関数 | status |
|---|---|---|---|
| 4.1 | `decompose_feature` 空 id 拒否 → state mutate なし | `test_ac4_decompose_feature_rejects_empty_id` | VERIFIED |
| 4.2 | `spec_mock_link.create_link` 空 section/負 mock_id 拒否 → state mutate なし | `test_ac4_spec_mock_link_rejects_invalid_input` | VERIFIED |
| 4.3 | `ears_classifier.classify` 短すぎ text 拒否 → state mutate なし | `test_ac4_ears_classifier_rejects_short_text` | VERIFIED |
| 4.4 | `context_builder` の Obsidian slug `..` traversal を拒否 → file write なし | `test_ac4_obsidian_slug_rejects_traversal` | VERIFIED |
| 4.5 | 本テストファイル自身に hardcoded secret なし | `test_ac4_no_hardcoded_secret_in_test_file` | VERIFIED |

---

## 4. Cross-task invariants discovered

これらは **個別 unit test では検出されない** が、Sprint 3 全体として満たすべき契約:

1. **API shape parity (chain a)**: hearing_service と requirements_service は同一の
   `start_step / reply / complete_step / get_state / get_chat_history` シグネチャを露出. 
   どちらかが先に signature を変えれば chain a は崩れる.
2. **EARS AC carrier shape (chain b)**: feature_decomposer の `acceptance_criteria` は
   `[{type, text}]` の list. ac_verification.verify_artifact の `criteria` 入力も同 shape.
   = decompose 出力をそのまま verify に渡せる.
3. **`classified_type` 値の domain (chain c)**: ears_classifier.classify は 5 EARS type
   のいずれかを返し、task_decomposition._generate_ears_ac も同 5 type 内から選ぶ.
4. **section_id 文字列の伝搬 (chain d)**: spec_html_generator が emit する section id は
   spec_mock_link.create_link の `spec_section_id` パラメータと同じ string domain.
5. **Constitution 出所の duality (chain e)**: constitution_engine は DB / env から読み,
   context_builder は filesystem (CONSTITUTION_DIR / 会社運営DB/constitutions) から読む.
   両者は **異なる source** だが「empty 同士は許容 / not-empty 同士は contradictory 禁止」.

## 5. Gap analysis (着手前)

| # | gap | severity | resolution |
|---|---|---|---|
| G1 | T-IT-S3 専用の cross-task integration test が無い (T-IT-S2 と同パターンで未整備) | HIGH | 本タスクで `test_t_it_s3_sprint3_integration.py` を新設し、上表 20 test で 1:1 追跡 |
| G2 | tickets.json の AC が generic stub のみで integration 視点不在 | LOW | 本 audit doc の Section 1 / 4 で expand 記録. PR description に貼る |
| G3 | T-BTSTRAP-04 / T-BTSTRAP-06 が pending (Sprint 3 全 task の 91% カバー) | LOW | Phase 2 migration 範囲. 本 IT は 21 task 範囲で完結, BTSTRAP は別 IT で扱う |

着手後 gap 数: 0 (G1 が本タスクの直接成果物で閉鎖. G2/G3 は doc-only 記録).

---

## 6. NEW 適合 / 非破壊性チェック

| # | 項目 | 結果 |
|---|---|---|
| 1 | 新規 service module 追加なし | OK (test ファイル + audit doc のみ) |
| 2 | 既存 service module 改変なし | OK (read-only に import) |
| 3 | 既存 router 改変なし | OK |
| 4 | 既存 test 削除/改変なし | OK |
| 5 | 公開 API シンボル変更なし | OK (本 test で symbol invariant を検証) |
| 6 | DB schema 変更なし | OK |
| 7 | RLS policy 追加/削除なし | OK |
| 8 | external dependency 追加なし | OK |
| 9 | tickets.json 改変なし (AC は generic のまま、audit doc で expand) | OK |

---

## 7. 想定 test 件数

- AC-1: 9 件
- AC-2: 3 件
- AC-3: 3 件
- AC-4: 5 件
- 合計: **20 件** (15-25 件レンジ内)
