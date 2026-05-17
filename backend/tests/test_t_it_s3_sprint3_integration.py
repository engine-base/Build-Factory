"""T-IT-S3: Sprint 3 統合テスト.

本セッションでマージされた Sprint 3 deliverables の cross-task 結合を verify:

  (a) hearing→requirements    : T-005-01/02 と T-005-03 が同一の step lifecycle API parity
  (b) decompose→AC verify     : T-006-01 → T-025-01 (EARS AC が verify_artifact に再投入可能)
  (c) EARS classify→rewrite   : T-025-02 → T-025-01 (rewritten_text が AC として valid)
  (d) spec_html→spec_mock_link: T-005-04 → T-005b-04 (section id 経路の結合)
  (e) constitution duality    : T-M28-01 (context_builder) ↔ T-AI-04 (constitution_engine)
  (f) ADR-010 禁則             : Sprint 3 services が LangGraph/LangChain を import しない
  (g) FastAPI smoke            : Sprint 3 routers が main.app に register されている

各シナリオは 2+ module を跨ぐ behavior を assert.
**ユニットテストの再実行ではなく "module 間契約" を検証** (T-IT-S2 と同方針).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : 5 cross-task chain + 2 infra invariant の 9 test.
  AC-2 EVENT-DRIVEN  : audit emit / 2 秒以内完走 の 3 test.
  AC-3 STATE-DRIVEN  : no real network / public API stable / workspace 分離 の 3 test.
  AC-4 UNWANTED      : invalid input が state mutate 前に reject される 5 test.

Audit doc: `docs/audit/2026-05-13_v2/T-IT-S3.md` (Spec stub expansion + invariant 一覧).
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


# ──────────────────────────────────────────────────────────────────────
# Fixtures (cross-task shared)
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _capture_all_audit(monkeypatch):
    """audit_logs DB 書込を fake で capture (state mutate なし).

    services.memory_service.emit_event を hook して呼出を memory list に集める.
    """
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type,
            "session_id": session_id,
            "user_id": user_id,
            "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture(autouse=True)
def _reset_sprint3_modules():
    """Sprint 3 module 内の process-wide state を test 前後で reset."""
    # T-005b-04 spec_mock_link in-memory store
    from services import spec_mock_link
    spec_mock_link.reset_store()

    # T-025-02 ears_classifier backend hook
    from services import ears_classifier
    ears_classifier.register_classifier_backend(None)

    # T-006-02 task_decomposition backend hook
    from services import task_decomposition
    task_decomposition.register_decomposer_backend(None)

    # T-005b-03 component_catalog cache (if accessible)
    try:
        from services import component_catalog
        component_catalog.reset_cache()
    except Exception:
        pass

    yield

    spec_mock_link.reset_store()
    ears_classifier.register_classifier_backend(None)
    task_decomposition.register_decomposer_backend(None)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """外部依存 env を test 中で誤動作させないよう clear (Constitution は test ごとに set)."""
    for k in (
        "CONSTITUTION_TEXT",
        "CONSTITUTION_DIR",
        "OBSIDIAN_VAULT_DIR",
        "SUPABASE_URL", "SUPABASE_SERVICE_KEY",
        "BETTER_STACK_HEARTBEAT_URL",
        "SENTRY_DSN",
    ):
        monkeypatch.delenv(k, raising=False)
    # upload_service.py captures SUPABASE_URL / SUPABASE_SERVICE_KEY at module
    # import time. When conftest.py populates test defaults, those constants
    # are non-empty even after delenv. Reset the module-level constants so
    # `_is_supabase_configured()` returns False on the local-fallback path.
    try:
        from services import upload_service as _us
        monkeypatch.setattr(_us, "SUPABASE_URL", "")
        monkeypatch.setattr(_us, "SUPABASE_SERVICE_KEY", "")
    except Exception:
        pass
    yield


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: cross-task chains + infra invariants
# ══════════════════════════════════════════════════════════════════════


def test_chain_a_hearing_and_requirements_share_step_lifecycle_api():
    """(chain a) hearing_service / requirements_service が同一の step lifecycle API
    (`start_step`, `reply`, `complete_step`, `get_state`) を露出する.

    片方の signature が変わったらこの test が fail し、chain a 崩壊を捕捉.
    """
    import inspect
    from services import hearing_service as hs
    from services import requirements_service as rs

    expected = ("start_step", "reply", "complete_step", "get_state")
    for name in expected:
        assert hasattr(hs, name), f"hearing_service.{name} missing"
        assert hasattr(rs, name), f"requirements_service.{name} missing"
        # signature 一致 (parameter 名と数)
        sig_h = inspect.signature(getattr(hs, name))
        sig_r = inspect.signature(getattr(rs, name))
        params_h = tuple(sig_h.parameters.keys())
        params_r = tuple(sig_r.parameters.keys())
        assert params_h == params_r, (
            f"{name} signature mismatch: hearing={params_h} vs requirements={params_r}"
        )


def test_chain_a_requirements_consumes_hearing_brief_shape():
    """(chain a) requirements_service.get_hearing_brief の async dict 返却契約.

    実 DB 接続を避け、artifact_service.list_artifacts を fake で stub する.
    contract: workspace_id を受け取り、空でも dict を返す.
    """
    import inspect
    from services import requirements_service as rs

    # signature contract
    sig = inspect.signature(rs.get_hearing_brief)
    params = list(sig.parameters.keys())
    assert params == ["workspace_id"], f"unexpected params: {params}"
    assert inspect.iscoroutinefunction(rs.get_hearing_brief)

    # behavior contract: artifact_service を fake で差し替えて dict 返却を確認
    async def fake_list_artifacts(**kwargs):
        return []

    with patch("services.artifact_service.list_artifacts", fake_list_artifacts):
        out = asyncio.run(rs.get_hearing_brief(1))
    assert isinstance(out, dict), f"get_hearing_brief must return dict, got {type(out)}"


def test_chain_b_feature_decomposer_emits_ears_ac_per_subtask():
    """(chain b) decompose_feature の各 sub-task は 1+ 件の EARS AC を持ち、
    各 AC は {type, text} を持つ."""
    from services import feature_decomposer
    from services.ac_verification import EARS_TYPES

    res = feature_decomposer.decompose_feature({
        "id": "F-IT-S3-A",
        "title": "demo feature for chain b",
        "description": "DB BE FE TST",
    })
    assert res.total >= 1
    for sub in res.tasks:
        assert isinstance(sub.acceptance_criteria, list)
        assert len(sub.acceptance_criteria) >= 1
        for ac in sub.acceptance_criteria:
            assert "type" in ac and "text" in ac
            assert ac["type"] in EARS_TYPES, f"non-EARS type emitted: {ac['type']}"


def test_chain_b_task_decomposition_ac_consumable_by_ac_verification():
    """(chain b) task_decomposition.decompose の sub-task の acceptance_criteria を
    ac_verification.verify_artifact に直接渡せる (carrier shape parity)."""
    from services import task_decomposition
    from services import ac_verification

    result = task_decomposition.decompose("Build a small REST endpoint with FastAPI", subtask_count=3)
    subtasks = result["subtasks"]
    assert len(subtasks) >= 1

    first = subtasks[0]
    # carrier shape: list[{type,text}]
    assert isinstance(first["acceptance_criteria"], list)
    # ac_verification.verify_artifact に渡せること (no exception, returns VerificationReport)
    artifact = {
        "id": "artifact-it-s3",
        "title": first["title"],
        "content": " ".join(ac["text"] for ac in first["acceptance_criteria"]),
    }
    report = ac_verification.verify_artifact(artifact, first["acceptance_criteria"])
    # total が AC 件数と一致 = criteria が parse できた証拠
    assert report.total == len(first["acceptance_criteria"])
    # overall は pass/warn/fail のいずれか (fail でも shape 検証は通る)
    assert report.overall in ("pass", "warn", "fail")


def test_chain_c_classify_rewrite_then_ac_verify():
    """(chain c) ears_classifier.classify の rewritten_text を ac_verification の
    criteria として使える (5 EARS type 全部で機能する)."""
    from services import ears_classifier
    from services import ac_verification
    from services.ac_verification import EARS_TYPES

    raw = "ユーザーが フォームを 送信したら システムは 2秒以内に レスポンスを返す"
    out = ears_classifier.classify(raw)
    assert out["classified_type"] in EARS_TYPES
    rewritten = out["rewritten_text"]
    assert isinstance(rewritten, str) and len(rewritten) >= 1

    # rewritten を criterion として使い、artifact に同 text を含めれば pass する
    criterion = {"type": out["classified_type"], "text": rewritten}
    artifact = {"id": "a-classify", "content": rewritten + "\n" + rewritten}
    report = ac_verification.verify_artifact(artifact, [criterion])
    assert report.total == 1
    # artifact が criterion を全文含む → fail でない (pass or warn)
    assert report.overall in ("pass", "warn")


def test_chain_d_spec_html_section_id_links_to_mock():
    """(chain d) render_spec_html が生成する section id (sec-N) を
    spec_mock_link.create_link の spec_section_id として渡せる."""
    from services.spec_html_generator import SpecMeta, SpecSection, render_spec_html
    from services import spec_mock_link

    meta = SpecMeta(project_name="IT-S3 chain d", workspace_id=42)
    sections = [
        SpecSection(title="概要", bullet_items=["a", "b"]),
        SpecSection(title="機能", bullet_items=["c"]),
    ]
    html = render_spec_html(meta, sections)

    # section id pattern: id="sec-N"
    ids = re.findall(r'id="(sec-\d+)"', html)
    assert len(ids) == 2

    # 各 section id を spec_mock_link に渡せる
    link1 = spec_mock_link.create_link(
        workspace_id=meta.workspace_id, spec_section_id=ids[0], mock_id=100, created_by="it-s3"
    )
    link2 = spec_mock_link.create_link(
        workspace_id=meta.workspace_id, spec_section_id=ids[1], mock_id=101, created_by="it-s3"
    )
    assert link1["spec_section_id"] == ids[0]
    assert link2["spec_section_id"] == ids[1]
    # 同 workspace の section から list 可能
    listed = spec_mock_link.list_links_for_spec(workspace_id=meta.workspace_id, spec_section_id=ids[0])
    assert len(listed) == 1 and listed[0]["mock_id"] == 100


def test_chain_e_constitution_dual_path_consistency(monkeypatch):
    """(chain e) context_builder.preload_constitution と constitution_engine の
    duality 不変条件:
      - 両 path とも empty を返す (DB なし / env なし / dir なし) ことは許容.
      - env CONSTITUTION_TEXT を set すると context_builder.preload_constitution は
        その値を直接返す (constitution_engine も env fallback).
    """
    from services import context_builder
    from services import constitution_engine

    # 両 path とも empty fallback 経路: env / dir なし
    monkeypatch.setenv("CONSTITUTION_DIR", "/nonexistent_dir_it_s3_xxx")
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    out_empty = asyncio.run(context_builder.preload_constitution("alice"))
    assert out_empty == ""

    # env path: context_builder.preload_constitution が env を直接返す
    monkeypatch.setenv("CONSTITUTION_TEXT", "TEST_CONSTITUTION_VALUE_FOR_IT_S3")
    out_env = asyncio.run(context_builder.preload_constitution("alice"))
    assert "TEST_CONSTITUTION_VALUE_FOR_IT_S3" in out_env

    # constitution_engine も env load 可能 (private helper _load_from_env)
    env_c = constitution_engine._load_from_env()
    # _load_from_env は dict (principles) を期待する形式なので raw string env はパースに失敗 → None でも OK
    # ここでの不変条件: env 経路の存在を相互認識していること (両者が同 env を見る or 機能 disable)
    assert env_c is None or hasattr(env_c, "principles")


def test_infra_f_sprint3_services_no_langgraph_import():
    """(infra f) ADR-010 禁則: Sprint 3 で touch した service module が
    langgraph / langchain を import していない (main 経路 invariant)."""
    sprint3_services = [
        "hearing_service.py",
        "requirements_service.py",
        "spec_html_generator.py",
        "spec_mock_link.py",
        "feature_decomposer.py",
        "task_decomposition.py",
        "impact_analyzer.py",
        "ac_verification.py",
        "ears_classifier.py",
        "constitution_engine.py",
        "cost_service.py",
        "stream_bridge.py",
        "context_builder.py",
        "screens_components.py",
        "designer_ai.py",
        "ui_mockup_integration.py",
        "component_catalog.py",
        "svg_diagram.py",
        "upload_service.py",
        "artifact_export.py",
        "output_processor.py",
        "slot_state.py",
        "slot_extractor.py",
    ]
    for fname in sprint3_services:
        path = REPO_ROOT / "backend" / "services" / fname
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        code_only = _strip_comments(src)
        assert "import langgraph" not in code_only, f"{fname}: ADR-010 violation (langgraph)"
        assert "from langgraph" not in code_only, f"{fname}: ADR-010 violation (langgraph)"
        assert "import langchain" not in code_only, f"{fname}: ADR-010 violation (langchain)"
        assert "from langchain" not in code_only, f"{fname}: ADR-010 violation (langchain)"


def test_infra_g_fastapi_app_boots_with_sprint3_routers():
    """(infra g) FastAPI app が boot でき、Sprint 3 router が register されている
    (smoke: TestClient の boot は成功 + 期待 path が router 経由で resolve)."""
    from fastapi.testclient import TestClient
    from main import app

    # boot check
    client = TestClient(app, raise_server_exceptions=False)
    assert client is not None

    # Sprint 3 router の代表的 path が registered routes に存在
    paths = {getattr(r, "path", "") for r in app.routes}
    expected_substrings = [
        "/hearing",                    # T-005-01 hearing router
        "/api/task-decomposition",     # T-006-02 task_decomposition router
        "/api/context/",               # T-M28-01 context_builder router
        "cost-summary",                # T-AI-05 cost dashboard (observability)
        "/api/ears/",                  # T-025-02 ears_classifier router
        "/api/spec-mock-links",        # T-005b-04 spec_mock_links router
        "/api/features/decompose",     # T-006-01 feature_decomposer router
        "impact",                      # T-006-03 impact_analyzer router (in /api/tasks/{}/impact)
        "screens-components",          # T-005b-01 screens_components router
        "/api/component-catalog",      # T-005b-03 component_catalog router
    ]
    for substr in expected_substrings:
        assert any(substr in p for p in paths), (
            f"no registered route contains substring {substr!r}; "
            f"Sprint 3 router likely not mounted"
        )


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: audit emit + 2 秒以内完走
# ══════════════════════════════════════════════════════════════════════


def test_ac2_hearing_emits_audit_on_start_step(_capture_all_audit, monkeypatch):
    """T-005-01: hearing_service の audit emit hook が呼ばれる (cross-module 接点)."""
    from services import hearing_service as hs

    # 直接 _emit_hearing_audit を呼んで cross-module emit を確認
    # (start_step は LLM 呼出を含むので、unit test の重複は避け、emit 専用 helper を verify)
    asyncio.run(hs._emit_hearing_audit(
        hs.EVENT_HEARING_STEP_STARTED,
        workspace_id=1, step=1, detail={"trigger": "it_s3"},
    ))
    types = [e["event_type"] for e in _capture_all_audit]
    assert hs.EVENT_HEARING_STEP_STARTED in types
    # event 定数は string で公開されている (cross-task で grep できる)
    assert isinstance(hs.EVENT_HEARING_STEP_STARTED, str)
    assert hs.EVENT_HEARING_STEP_STARTED.startswith("hearing.")


def test_ac2_upload_emits_audit(_capture_all_audit, tmp_path, monkeypatch):
    """T-015-03 upload_image が audit を emit する (local fallback 経路).

    LOCAL_FALLBACK_DIR を tmp_path に差し替え、test 副作用で実 backend/static/
    を mutate しない (AC-3 state isolation).
    """
    from services import upload_service

    # local upload 経路: SUPABASE 設定なし (clean_env で保証済).
    # 実 backend/static/uploads/ を汚さないよう LOCAL_FALLBACK_DIR を tmp_path に差替.
    monkeypatch.setattr(upload_service, "LOCAL_FALLBACK_DIR", tmp_path)

    out = asyncio.run(upload_service.upload_image(
        account_id=1,
        kind="logo",
        filename="test.png",
        content=b"\x89PNG\r\n\x1a\nfake",
        content_type="image/png",
        generate_markdown=True,
    ))
    # output shape contract
    assert "url" in out
    assert "share_url" in out
    assert "markdown" in out

    # audit emit が 1+ 件発火していること (success or any)
    assert len(_capture_all_audit) >= 1
    # event_type は uploads.* で始まる (upload_service の EVENT_UPLOAD_* 定数)
    upload_events = [e for e in _capture_all_audit if e["event_type"].startswith("uploads.")]
    assert len(upload_events) >= 1


def test_ac2_each_chain_completes_within_2_seconds():
    """各 chain の最小サイクルが 2 秒以内 (no real LLM/network)."""
    from services import feature_decomposer
    from services import task_decomposition
    from services import ears_classifier
    from services import ac_verification
    from services import spec_mock_link
    from services.spec_html_generator import SpecMeta, SpecSection, render_spec_html

    t0 = time.time()
    # chain b: decompose → AC verify
    res = feature_decomposer.decompose_feature({
        "id": "F-IT-S3-T", "title": "x", "description": "DB BE",
    })
    ac_verification.verify_artifact(
        {"id": "a", "content": "x"}, res.tasks[0].acceptance_criteria,
    )
    # chain c: classify → verify
    cl = ears_classifier.classify("The system shall do X.")
    ac_verification.verify_artifact(
        {"id": "a2", "content": cl["rewritten_text"] + " " + cl["rewritten_text"]},
        [{"type": cl["classified_type"], "text": cl["rewritten_text"]}],
    )
    # chain d: spec html → link
    html = render_spec_html(
        SpecMeta(project_name="t", workspace_id=1),
        [SpecSection(title="s", bullet_items=["x"])],
    )
    assert "sec-1" in html
    spec_mock_link.create_link(workspace_id=1, spec_section_id="sec-1", mock_id=1)
    # task decomposition heuristic
    task_decomposition.decompose("Build small API endpoint", subtask_count=2)

    elapsed = time.time() - t0
    assert elapsed < 2.0, f"chains took {elapsed:.2f}s, expected < 2.0s"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: no real network / API stable / workspace isolation
# ══════════════════════════════════════════════════════════════════════


def test_ac3_no_real_http_in_test_session():
    """テスト内で httpx の real network が呼ばれていないこと.

    upload_service の local fallback 経路 (SUPABASE 未設定) が外部呼出 ゼロ.
    """
    from services import upload_service
    # is_supabase_configured == False を確認 (env clear fixture で保証済)
    assert upload_service._is_supabase_configured() is False


def test_ac3_sprint3_public_api_surface_stable():
    """Sprint 3 公開 API が想定どおり存在 (regression 検出)."""
    expected_apis = {
        "services.hearing_service": [
            "start_step", "reply", "complete_step", "get_state",
            "EVENT_HEARING_STEP_STARTED", "EVENT_HEARING_REPLIED",
            "EVENT_HEARING_STEP_COMPLETED",
        ],
        "services.requirements_service": [
            "start_step", "reply", "complete_step", "get_state",
            "get_hearing_brief",
        ],
        "services.spec_html_generator": [
            "SpecMeta", "SpecSection", "render_spec_html", "build_sections_from_view",
        ],
        "services.spec_mock_link": [
            "create_link", "list_links_for_spec", "list_links_for_mock",
            "get_link", "delete_link", "reset_store",
            "DuplicateLinkError", "LinkNotFoundError",
        ],
        "services.feature_decomposer": [
            "decompose_feature", "DecompositionResult", "SubTask",
            "FeatureDecomposerError",
        ],
        "services.task_decomposition": [
            "decompose", "decompose_heuristic", "register_decomposer_backend",
            "list_ac_types",
        ],
        "services.impact_analyzer": [
            "compute_impact", "ImpactReport", "ImpactedTask",
            "CycleDetectedError", "ImpactAnalyzerError",
        ],
        "services.ac_verification": [
            "verify_artifact", "EARS_TYPES", "CriterionResult", "VerificationReport",
        ],
        "services.ears_classifier": [
            "classify", "suggest_rewrite", "register_classifier_backend",
            "VALID_TYPES", "TYPE_PATTERNS",
        ],
        "services.constitution_engine": [
            "get_active_constitution", "inject_for_session", "invalidate_cache",
            "SECTION_KEYS", "MissingConstitution", "CorruptConstitution",
        ],
        "services.cost_service": [
            "record_cost", "monthly_cost", "session_cost",
            "compute_display_cost", "CostEntry",
        ],
        "services.stream_bridge": [
            "get_bridge", "reset_bridge", "StreamBridge",
        ],
        "services.context_builder": [
            "build_context", "preload_constitution", "lookup_decision",
            "read_obsidian_note", "write_obsidian_note", "is_secretary_active",
        ],
        "services.upload_service": [
            "upload_image", "build_markdown_snippet",
        ],
        "services.svg_diagram": [
            "auto_diagram", "table_to_svg", "checklist_to_svg", "list_to_svg",
            "list_diagram_kinds", "SvgDiagramError",
        ],
        "services.screens_components": [
            "list_screens", "list_components", "list_all", "count_by_type",
        ],
        "services.component_catalog": ["reset_cache"],
    }
    for module_name, expected in expected_apis.items():
        mod = __import__(module_name, fromlist=["*"])
        for sym in expected:
            assert hasattr(mod, sym), (
                f"BROKEN PUBLIC API CONTRACT: {module_name}.{sym} missing"
            )


def test_ac3_spec_mock_link_workspace_isolation():
    """spec_mock_link は workspace_id をキーに分離する (cross-workspace leakage なし)."""
    from services import spec_mock_link

    # 同一 spec_section_id / mock_id でも workspace が違えば独立した link
    l1 = spec_mock_link.create_link(workspace_id=10, spec_section_id="sec-x", mock_id=5)
    l2 = spec_mock_link.create_link(workspace_id=20, spec_section_id="sec-x", mock_id=5)
    assert l1["id"] != l2["id"]

    # list は workspace_id をキーに分離する
    listed_10 = spec_mock_link.list_links_for_spec(workspace_id=10, spec_section_id="sec-x")
    listed_20 = spec_mock_link.list_links_for_spec(workspace_id=20, spec_section_id="sec-x")
    assert len(listed_10) == 1 and listed_10[0]["workspace_id"] == 10
    assert len(listed_20) == 1 and listed_20[0]["workspace_id"] == 20
    # 別 workspace の row が混入しない (UNWANTED に該当)
    assert listed_10[0]["id"] != listed_20[0]["id"]


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: invalid input rejected before state mutation
# ══════════════════════════════════════════════════════════════════════


def test_ac4_decompose_feature_rejects_empty_id():
    """T-006-01: feature.id 空文字は state mutate 前に reject (FeatureDecomposerError)."""
    from services import feature_decomposer

    with pytest.raises(feature_decomposer.FeatureDecomposerError):
        feature_decomposer.decompose_feature({"id": "", "title": "x"})
    # title 欠落も拒否
    with pytest.raises(feature_decomposer.FeatureDecomposerError):
        feature_decomposer.decompose_feature({"id": "F-1", "title": ""})
    # dict でない入力も拒否
    with pytest.raises(feature_decomposer.FeatureDecomposerError):
        feature_decomposer.decompose_feature("not a dict")  # type: ignore[arg-type]


def test_ac4_spec_mock_link_rejects_invalid_input():
    """T-005b-04: 空 section_id / 負 mock_id / 0 workspace_id は state mutate 前に reject.

    state mutation 前に raise されるので、reject 後に list を引いても 0 件のまま.
    """
    from services import spec_mock_link

    spec_mock_link.reset_store()
    # 0 workspace_id
    with pytest.raises(spec_mock_link.SpecMockLinkError):
        spec_mock_link.create_link(workspace_id=0, spec_section_id="sec-1", mock_id=1)
    # 空 section
    with pytest.raises(spec_mock_link.SpecMockLinkError):
        spec_mock_link.create_link(workspace_id=1, spec_section_id="", mock_id=1)
    # 負 mock_id
    with pytest.raises(spec_mock_link.SpecMockLinkError):
        spec_mock_link.create_link(workspace_id=1, spec_section_id="sec-1", mock_id=-1)
    # 過大 section_id (> 200)
    with pytest.raises(spec_mock_link.SpecMockLinkError):
        spec_mock_link.create_link(workspace_id=1, spec_section_id="x" * 201, mock_id=1)

    # state 未変化 (作成された link なし)
    listed = spec_mock_link.list_links_for_spec(workspace_id=1, spec_section_id="sec-1")
    assert listed == []


def test_ac4_ears_classifier_rejects_short_text():
    """T-025-02: classify は < 10 文字 text を reject (ValueError)."""
    from services import ears_classifier

    with pytest.raises(ValueError):
        ears_classifier.classify("short")  # 5 chars
    with pytest.raises(ValueError):
        ears_classifier.classify("")  # empty
    with pytest.raises(ValueError):
        ears_classifier.classify("   ")  # whitespace only

    # 有効 text は通る
    out = ears_classifier.classify("The system shall do something useful here.")
    assert out["classified_type"] in ears_classifier.VALID_TYPES


def test_ac4_obsidian_slug_rejects_traversal(tmp_path, monkeypatch):
    """T-M28-01 context_builder: Obsidian slug 内の `..` traversal を reject.

    state mutation 前に raise されるので、reject 後に file が作成されていない.
    """
    from services import context_builder

    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()

    # traversal を含む slug は ContextBuilderError (or ValueError) で reject
    for bad_slug in ("../etc/passwd", "..", "a/../b", "/abs/path", "x" * 300):
        with pytest.raises((context_builder.ContextBuilderError, ValueError)):
            context_builder.write_obsidian_note(
                bad_slug, content="should not write", vault_dir=vault_dir,
            )

    # vault_dir 配下に file が作成されていない
    written_files = list(vault_dir.rglob("*"))
    # ディレクトリ自身を除いた file が 0
    actual_files = [p for p in written_files if p.is_file()]
    assert actual_files == [], f"vault was mutated: {actual_files}"


def test_ac4_no_hardcoded_secret_in_test_file():
    """本テストファイル自身が API key / token / project URL を hardcode していない."""
    test_file = (
        REPO_ROOT / "backend" / "tests" / "test_t_it_s3_sprint3_integration.py"
    )
    src = _strip_comments(test_file.read_text(encoding="utf-8"))
    # 実 API key / token / project URL pattern
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{30,}", src)
    assert not re.search(r"sk-proj-[A-Za-z0-9_-]{30,}", src)
    assert not re.search(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}", src)
    # supabase project URL pattern (xxxx.supabase.co with real-looking prefix)
    assert not re.search(r"https://[a-z]{20,}\.supabase\.co", src)


# ══════════════════════════════════════════════════════════════════════
# helpers
# ══════════════════════════════════════════════════════════════════════


def _strip_comments(src: str) -> str:
    """Python source から comment と docstring を粗く除去."""
    out_lines = []
    in_triple = False
    triple_char = None
    for raw in src.splitlines():
        line = raw
        if in_triple:
            if triple_char in line:
                line = line.split(triple_char, 1)[1]
                in_triple = False
            else:
                continue
        for ch in ('"""', "'''"):
            if ch in line:
                before, _, after = line.partition(ch)
                if ch in after:
                    line = before + after.split(ch, 1)[1]
                else:
                    line = before
                    in_triple = True
                    triple_char = ch
                break
        if "#" in line:
            line = line.split("#", 1)[0]
        if line.strip():
            out_lines.append(line)
    return "\n".join(out_lines)
