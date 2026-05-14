"""T-011-01: Reviewer AI persona + Plan/Gen/Eval — 1:1 spec audit test.

Pre-flight audit (2026-05-13_v2). PR #253 lesson 適用版:
  - 3 stage (Plan / Gen / Eval) が **独立した input/output schema** + 独立 test を
    持つことを 1:1 で検証する.
  - 同一 helper を呼ぶだけの偽装は禁止 — 各 stage の payload key / output key が
    互いに重ならないことを test で機械的に保証する.
  - drift guard: source module は LangGraph / LangChain / LiteLLM を import しない
    (CLAUDE.md §3 メイン経路禁則).
  - REFACTOR invariant: 既存 `reviewer.py` + `reviewer_loop.py` への bi-directional
    依存禁止 + REVIEW_DIMENSIONS は import のみ (mutation 禁止).
  - Constitution 注入 (M-28) は **NOT-IN-SCOPE for T-011-01 (REFACTOR)** であることを
    drift guard として明示 — Phase 1 で本 module が独自に constitution_engine を
    呼び出さないこと (T-AI-04 / Memory Tool delegate 経路へ譲る) を機械検知.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : reviewer_persona service + router (POST plan/generate/
                       evaluate/full) 公開. REVIEW_DIMENSIONS REUSE. 既存
                       reviewer.py / reviewer_loop.py 無改変.
  AC-2 EVENT-DRIVEN  : structured dict / 2 秒以内 / chain Plan → Gen → Eval /
                       status: pass | needs_revision.
  AC-3 STATE-DRIVEN  : backend 未登録 → deterministic / no DB write /
                       REVIEW_DIMENSIONS 不変 / hook は 3 phase 外で呼ばない.
  AC-4 UNWANTED      : invalid review_kind / 空 artifact_ids / score 範囲外 /
                       backend 不正出力 → ReviewerPersonaError / 401 / 4xx.
"""
from __future__ import annotations

import inspect
import os
import re
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from services import reviewer_persona as rp
from services.reviewer_loop import REVIEW_DIMENSIONS


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "backend" / "services" / "reviewer_persona.py"
ROUTER = REPO_ROOT / "backend" / "routers" / "reviewer_persona.py"
EXISTING_LOOP = REPO_ROOT / "backend" / "services" / "reviewer_loop.py"
EXISTING_ROUTER = REPO_ROOT / "backend" / "routers" / "reviewer.py"


def _source_code_only(path: Path) -> str:
    """Strip docstrings + line comments for forbidden-string scans."""
    raw = path.read_text(encoding="utf-8")
    no_docstrings = re.sub(r'"""[\s\S]*?"""', "", raw)
    no_docstrings = re.sub(r"'''[\s\S]*?'''", "", no_docstrings)
    lines = []
    for line in no_docstrings.splitlines():
        idx = line.find("#")
        if idx >= 0:
            line = line[:idx]
        lines.append(line)
    return "\n".join(lines)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_backend():
    rp.register_persona_backend(None)
    yield
    rp.register_persona_backend(None)


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — module / public symbols / REUSE invariant
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_module_exists():
    assert SERVICE.exists(), f"missing service: {SERVICE}"


def test_ac1_router_module_exists():
    assert ROUTER.exists(), f"missing router: {ROUTER}"


@pytest.mark.parametrize("sym", [
    "plan_review",
    "generate_review",
    "evaluate_review",
    "run_plan_gen_eval",
    "register_persona_backend",
    "ReviewerPersonaError",
])
def test_ac1_required_public_symbols_present(sym):
    """AC-1 literal: plan_review / generate_review / evaluate_review /
    run_plan_gen_eval / register_persona_backend / ReviewerPersonaError."""
    assert hasattr(rp, sym), f"missing required public symbol: {sym}"


def test_ac1_review_dimensions_imported_from_reviewer_loop():
    """AC-1 literal: REUSE REVIEW_DIMENSIONS from reviewer_loop.py."""
    src = SERVICE.read_text(encoding="utf-8")
    assert "from services.reviewer_loop import REVIEW_DIMENSIONS" in src, (
        "REVIEW_DIMENSIONS must be imported (REUSE), not redefined"
    )
    # Also: no local rebinding of REVIEW_DIMENSIONS in service body
    code = _source_code_only(SERVICE)
    assert "REVIEW_DIMENSIONS =" not in code, (
        "REVIEW_DIMENSIONS must not be re-assigned in reviewer_persona.py"
    )


def test_ac1_review_dimensions_used_in_rule_based_plan():
    plan = rp.plan_review("task_review", ["A-1"])
    assert plan["dimensions"] == list(REVIEW_DIMENSIONS["task_review"]), (
        "rule-based plan must mirror REVIEW_DIMENSIONS[review_kind] verbatim"
    )
    plan2 = rp.plan_review("integration", ["A-1"])
    assert plan2["dimensions"] == list(REVIEW_DIMENSIONS["integration"])


def test_ac1_existing_reviewer_loop_has_no_reverse_dependency():
    """REFACTOR invariant: reviewer_loop.py must not import reviewer_persona."""
    src = EXISTING_LOOP.read_text(encoding="utf-8")
    assert "reviewer_persona" not in src


def test_ac1_existing_reviewer_router_has_no_reverse_dependency():
    src = EXISTING_ROUTER.read_text(encoding="utf-8")
    assert "reviewer_persona" not in src


def test_ac1_router_mounted_at_expected_prefix(client):
    """AC-1 literal: router mounted at POST /api/reviewer-persona/{plan,...}."""
    for path in ("/plan", "/generate", "/evaluate", "/full"):
        resp = client.options(f"/api/reviewer-persona{path}")
        # mounted endpoints return either 200 / 405 / 422 — never 404
        assert resp.status_code != 404, f"endpoint missing: {path}"


@pytest.mark.parametrize("endpoint", ["plan", "generate", "evaluate", "full"])
def test_ac1_router_endpoints_all_present(client, endpoint):
    """AC-1 literal: 4 endpoints (plan / generate / evaluate / full)."""
    body: dict[str, Any] = {
        "review_kind": "task_review",
        "target_artifact_ids": ["A-1"],
    }
    if endpoint == "generate":
        plan = rp.plan_review("task_review", ["A-1"])
        body = {"plan": plan}
    elif endpoint == "evaluate":
        plan = rp.plan_review("task_review", ["A-1"])
        review = rp.generate_review(plan)
        body = {"review": review}
    resp = client.post(f"/api/reviewer-persona/{endpoint}", json=body)
    assert resp.status_code == 200, f"{endpoint}: {resp.text}"


def test_ac1_persona_name_is_reviewer():
    """AC-1 literal: persona: 'reviewer'."""
    assert rp.PERSONA_NAME == "reviewer"
    plan = rp.plan_review("task_review", ["A-1"])
    assert plan["persona"] == "reviewer"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — 3 stage independence + chain + 2 秒 timeout
# ══════════════════════════════════════════════════════════════════════
#
# Anti-drift requirement (PR #253 lesson):
#   各 stage が異なる input / output / side-effect を持つことを 1:1 で検証.
#   Plan / Gen / Eval が同じ helper を呼ぶだけの偽装を禁止.


def test_ac2_three_stages_have_distinct_signatures():
    """Plan / Gen / Eval は **異なる input signature** を持つ.

    Anti-drift: 全 stage が同じ wrapper を呼ぶだけだと signature が同じになる.
    """
    plan_sig = inspect.signature(rp.plan_review)
    gen_sig = inspect.signature(rp.generate_review)
    eval_sig = inspect.signature(rp.evaluate_review)

    # Plan は (review_kind, target_artifact_ids) を取る
    assert "review_kind" in plan_sig.parameters
    assert "target_artifact_ids" in plan_sig.parameters
    assert "plan" not in plan_sig.parameters
    assert "review" not in plan_sig.parameters

    # Generate は plan dict を取る (Plan output が input)
    assert "plan" in gen_sig.parameters
    assert "review_kind" not in gen_sig.parameters
    assert "review" not in gen_sig.parameters

    # Evaluate は review dict + pass_threshold を取る
    assert "review" in eval_sig.parameters
    assert "pass_threshold" in eval_sig.parameters
    assert "plan" not in eval_sig.parameters


def test_ac2_three_stages_emit_distinct_phase_label():
    """各 stage の output["phase"] は異なる値 (plan / generate / evaluate)."""
    plan = rp.plan_review("task_review", ["A-1"])
    review = rp.generate_review(plan)
    ev = rp.evaluate_review(review)
    assert plan["phase"] == "plan"
    assert review["phase"] == "generate"
    assert ev["phase"] == "evaluate"
    assert len({plan["phase"], review["phase"], ev["phase"]}) == 3, (
        "all 3 stages must emit distinct phase labels (anti-drift)"
    )


def test_ac2_three_stages_have_distinct_output_schemas():
    """各 stage の output dict は互いに **重ならない unique key** を持つ.

    Anti-drift: 全 stage が同じ shape を返したら 3 stage 設計が空洞化する.
    """
    plan = rp.plan_review("task_review", ["A-1"])
    review = rp.generate_review(plan)
    ev = rp.evaluate_review(review)

    # Plan-unique: dimensions + rationale + target_artifact_ids
    assert "dimensions" in plan
    assert "rationale" in plan
    assert "target_artifact_ids" in plan
    assert "findings" not in plan
    assert "score" not in plan

    # Generate-unique: findings (Plan には無い)
    assert "findings" in review
    assert "dimensions" not in review  # plan-specific
    assert "score" not in review  # eval-specific

    # Evaluate-unique: score + status + weakness + pass_threshold
    assert "score" in ev
    assert "status" in ev
    assert "weakness" in ev
    assert "pass_threshold" in ev
    assert "findings" not in ev  # generate-specific


def test_ac2_three_stages_invoke_backend_with_distinct_payload_keys():
    """各 stage は backend hook に **異なる payload key** を渡す.

    Anti-drift: 全 stage が同じ payload を渡したら variant が空洞化する.
    """
    seen: list[tuple[str, frozenset[str]]] = []

    def tracking_backend(phase, payload):
        seen.append((phase, frozenset(payload.keys())))
        return None

    rp.register_persona_backend(tracking_backend)
    rp.run_plan_gen_eval("task_review", ["A-1"])

    # 3 distinct phases observed
    assert [p for p, _ in seen] == ["plan", "generate", "evaluate"]

    payloads = {p: keys for p, keys in seen}
    # Plan payload: review_kind + artifact_ids (no plan / review)
    assert "review_kind" in payloads["plan"]
    assert "artifact_ids" in payloads["plan"]
    assert "plan" not in payloads["plan"]
    assert "review" not in payloads["plan"]
    # Generate payload: plan (no review_kind direct)
    assert "plan" in payloads["generate"]
    assert "review" not in payloads["generate"]
    # Evaluate payload: review (no plan direct)
    assert "review" in payloads["evaluate"]
    assert "plan" not in payloads["evaluate"]

    # All 3 payloads must be set-distinct
    assert len({payloads["plan"], payloads["generate"], payloads["evaluate"]}) == 3


def test_ac2_run_plan_gen_eval_chains_in_order():
    """AC-2 literal: chain Plan → Gen → Eval."""
    order: list[str] = []

    def ordered_backend(phase, payload):
        order.append(phase)
        return None

    rp.register_persona_backend(ordered_backend)
    out = rp.run_plan_gen_eval("task_review", ["A-1"])
    assert order == ["plan", "generate", "evaluate"]
    assert "plan" in out and "review" in out and "evaluation" in out


def test_ac2_run_plan_gen_eval_returns_status_pass_or_needs_revision():
    """AC-2 literal: status: 'pass' | 'needs_revision'."""
    out = rp.run_plan_gen_eval("task_review", ["A-1"])
    assert out["status"] in ("pass", "needs_revision")
    assert out["status"] == out["evaluation"]["status"]


def test_ac2_run_plan_gen_eval_returns_backend_used_flag():
    """AC-2 literal: returns {..., backend_used: bool}."""
    out = rp.run_plan_gen_eval("task_review", ["A-1"])
    assert isinstance(out["backend_used"], bool)
    assert out["backend_used"] is False  # no backend registered


def test_ac2_each_stage_returns_latency_ms():
    """AC-2 literal: returns {..., latency_ms} for each stage."""
    plan = rp.plan_review("task_review", ["A-1"])
    review = rp.generate_review(plan)
    ev = rp.evaluate_review(review)
    for r in (plan, review, ev):
        assert isinstance(r["latency_ms"], int)
        assert r["latency_ms"] >= 0


def test_ac2_full_chain_within_2_seconds():
    """AC-2 literal: within 2 seconds for the rule-based fallback path."""
    t0 = time.time()
    rp.run_plan_gen_eval("task_review", ["A-1", "A-2", "A-3"])
    elapsed = time.time() - t0
    assert elapsed < 2.0, f"rule-based chain took {elapsed:.3f}s"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — fallback / no DB / hook scope / REVIEW_DIMENSIONS 不変
# ══════════════════════════════════════════════════════════════════════


def test_ac3_no_backend_uses_deterministic_fallback():
    """AC-3 literal: While no AI backend is registered, fall back to
    deterministic rule-based output."""
    assert rp.get_persona_backend() is None
    out1 = rp.run_plan_gen_eval("task_review", ["A-1"])
    out2 = rp.run_plan_gen_eval("task_review", ["A-1"])
    assert out1["backend_used"] is False
    assert out2["backend_used"] is False
    # deterministic: same dimensions / findings count
    assert out1["plan"]["dimensions"] == out2["plan"]["dimensions"]
    assert len(out1["review"]["findings"]) == len(out2["review"]["findings"])


def test_ac3_no_db_write_in_source():
    """AC-3 literal: no DB write."""
    code = _source_code_only(SERVICE)
    forbidden = ["INSERT INTO", "UPDATE ", "DELETE FROM",
                 "aiosqlite", "DB_PATH"]
    for token in forbidden:
        assert token not in code, f"forbidden DB write token in source: {token}"


def test_ac3_review_dimensions_not_mutated_after_run():
    """AC-3 literal: REVIEW_DIMENSIONS untouched."""
    before = {k: tuple(v) for k, v in REVIEW_DIMENSIONS.items()}
    rp.run_plan_gen_eval("task_review", ["A-1"])
    rp.run_plan_gen_eval("integration", ["A-1"])
    after = {k: tuple(v) for k, v in REVIEW_DIMENSIONS.items()}
    assert before == after


def test_ac3_backend_hook_signature_is_phase_payload_dict():
    """AC-3 literal: hook accepts (phase, payload) -> dict callable."""
    received: list[tuple[Any, Any]] = []

    def hook(phase, payload):
        received.append((phase, payload))
        return None

    rp.register_persona_backend(hook)
    rp.run_plan_gen_eval("task_review", ["A-1"])
    assert len(received) == 3
    for phase, payload in received:
        assert phase in rp.VALID_PHASES
        assert isinstance(payload, dict)


def test_ac3_backend_hook_not_invoked_outside_3_phases():
    """AC-3 literal: backend hook shall not be invoked outside 3 phases."""
    phases_called: set[str] = set()

    def tracking_hook(phase, payload):
        phases_called.add(phase)
        return None

    rp.register_persona_backend(tracking_hook)
    rp.run_plan_gen_eval("task_review", ["A-1"])
    # only the 3 documented phases
    assert phases_called == {"plan", "generate", "evaluate"}
    assert phases_called <= set(rp.VALID_PHASES)


def test_ac3_call_backend_rejects_unknown_phase():
    """invariant: _call_backend with phase outside VALID_PHASES → raises."""
    if hasattr(rp, "_call_backend"):
        with pytest.raises(rp.ReviewerPersonaError):
            rp._call_backend("INVALID_PHASE", {})  # type: ignore[attr-defined]


# ── Drift guard: CLAUDE.md §3 メイン経路禁則 (no LangGraph / LangChain / LiteLLM) ──


def test_ac3_no_langgraph_import_in_source():
    code = _source_code_only(SERVICE).lower()
    assert "langgraph" not in code, (
        "reviewer_persona must not import LangGraph (CLAUDE.md §3 禁則)"
    )


def test_ac3_no_langchain_import_in_source():
    code = _source_code_only(SERVICE).lower()
    assert "langchain" not in code, (
        "reviewer_persona must not import LangChain (CLAUDE.md §3 禁則)"
    )


def test_ac3_no_litellm_import_in_source():
    """CLAUDE.md §3: LiteLLM はメイン経路 (claude-runner) で使ってはならない."""
    code = _source_code_only(SERVICE).lower()
    # litellm の import を直接持たない (sub-layer 経由のみ許可)
    assert "import litellm" not in code
    assert "from litellm" not in code


# ── Drift guard: Constitution 注入は M-28 / T-AI-04 / Memory Tool delegate 経路 ──
#   T-011-01 (REFACTOR) は本 module 内で constitution_engine を直接呼ばない.
#   Phase 1 では Constitution 注入は **NOT-IN-SCOPE** (Memory Tool / T-AI-04 が担当).


def test_ac3_constitution_inject_not_self_implemented_in_reviewer_persona():
    """Drift guard (NIH 削減 / ADR-012):
    本 module は constitution_engine を直接 import / 呼び出さない.
    Constitution 注入は T-AI-04 (Memory Tool delegate) 経路で行う.
    """
    code = _source_code_only(SERVICE)
    assert "constitution_engine" not in code, (
        "T-011-01 (REFACTOR) は constitution_engine を直接呼ばない "
        "(NIH 削減 / Memory Tool delegate に譲る)"
    )
    assert "inject_for_session" not in code, (
        "inject_for_session は T-AI-04 / Memory Tool 経由のみ呼ぶ"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — invalid input + 4xx mapping + no regression
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bad_kind", ["BOGUS", "task-review", "", None, 123, [], {}])
def test_ac4_invalid_review_kind_raises_persona_error(bad_kind):
    """AC-4 literal: review_kind not in {'task_review', 'integration'} →
    ReviewerPersonaError."""
    with pytest.raises(rp.ReviewerPersonaError):
        rp.plan_review(bad_kind, ["A-1"])


@pytest.mark.parametrize("bad_ids", [None, "not-a-list", [], ["", "  "], [1, 2]])
def test_ac4_invalid_artifact_ids_raises_persona_error(bad_ids):
    """AC-4 literal: target_artifact_ids empty / non-list → ReviewerPersonaError."""
    with pytest.raises(rp.ReviewerPersonaError):
        rp.plan_review("task_review", bad_ids)


@pytest.mark.parametrize("bad_score", [-0.1, 1.1, 2.0, -1.0])
def test_ac4_score_out_of_range_in_threshold_raises(bad_score):
    """AC-4 literal: evaluation score outside [0.0, 1.0] → ReviewerPersonaError.
    Validated via _validate_score helper exposed in pass_threshold."""
    plan = rp.plan_review("task_review", ["A-1"])
    review = rp.generate_review(plan)
    with pytest.raises(rp.ReviewerPersonaError):
        rp.evaluate_review(review, pass_threshold=bad_score)


def test_ac4_backend_malformed_output_falls_back_silently():
    """AC-4 literal: backend returns malformed output → fall back to rule-based.
    Critical: must not crash, must continue to deterministic path."""
    def bad_backend(phase, payload):
        return "this is not a dict"  # malformed

    rp.register_persona_backend(bad_backend)
    out = rp.run_plan_gen_eval("task_review", ["A-1"])
    assert out["backend_used"] is False  # fell back
    assert out["status"] in ("pass", "needs_revision")  # still produced result


def test_ac4_backend_score_out_of_range_falls_back():
    """AC-4 literal: backend score outside [0.0, 1.0] → fall back."""
    def bad_eval(phase, payload):
        if phase == "evaluate":
            return {"score": 42.0, "weakness": []}
        return None

    rp.register_persona_backend(bad_eval)
    out = rp.run_plan_gen_eval("task_review", ["A-1"])
    assert out["evaluation"]["backend_used"] is False
    assert 0.0 <= out["evaluation"]["score"] <= 1.0


def test_ac4_endpoint_returns_4xx_with_detail_code_message(client):
    """AC-4 literal: 4xx {detail:{code:'reviewer_persona.invalid_input', message}}."""
    resp = client.post(
        "/api/reviewer-persona/plan",
        json={"review_kind": "BOGUS", "target_artifact_ids": ["A-1"]},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "detail" in body
    assert body["detail"]["code"] == "reviewer_persona.invalid_input"
    assert "message" in body["detail"]


def test_ac4_endpoint_returns_401_for_empty_actor(client):
    """AC-4 literal: 'reviewer_persona.unauthorized' code for empty actor."""
    resp = client.post(
        "/api/reviewer-persona/plan",
        json={
            "review_kind": "task_review",
            "target_artifact_ids": ["A-1"],
            "actor_user_id": "  ",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "reviewer_persona.unauthorized"


def test_ac4_existing_review_dimensions_not_renamed():
    """AC-4 literal: no rename of REVIEW_DIMENSIONS (REFACTOR invariant)."""
    src = EXISTING_LOOP.read_text(encoding="utf-8")
    # exact name preserved + still a top-level dict
    assert "REVIEW_DIMENSIONS = {" in src
    assert isinstance(REVIEW_DIMENSIONS, dict)
    assert "task_review" in REVIEW_DIMENSIONS
    assert "integration" in REVIEW_DIMENSIONS


def test_ac4_no_hardcoded_secret_in_source():
    """Red-line: no API key in source."""
    code = _source_code_only(SERVICE)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code
    assert "ANTHROPIC_API_KEY" not in code


# ══════════════════════════════════════════════════════════════════════
# Drift guard summary (PR #253 lesson)
# ══════════════════════════════════════════════════════════════════════


def test_drift_guard_plan_and_generate_helpers_are_distinct_functions():
    """Anti-drift: Plan / Generate / Evaluate は同一関数の alias ではない."""
    assert rp.plan_review is not rp.generate_review
    assert rp.plan_review is not rp.evaluate_review
    assert rp.generate_review is not rp.evaluate_review
    # All distinct code objects
    codes = {
        rp.plan_review.__code__,
        rp.generate_review.__code__,
        rp.evaluate_review.__code__,
    }
    assert len(codes) == 3, "3 stages must be 3 distinct code objects"


def test_drift_guard_each_stage_produces_variant_specific_output():
    """同じ input でも各 stage は variant-specific output を返す
    (空洞 wrapper でないことの runtime 検証)."""
    plan = rp.plan_review("task_review", ["A-1"])
    review = rp.generate_review(plan)
    ev = rp.evaluate_review(review)

    # Plan-unique data
    assert "dimensions" in plan and isinstance(plan["dimensions"], list)
    # Generate produces variant-specific data from Plan (findings have notes)
    for f in review["findings"]:
        assert isinstance(f["note"], str) and len(f["note"]) > 0
    # Evaluate produces score that depends on findings severity
    assert isinstance(ev["score"], float)


def test_drift_guard_persona_name_constant_matches_reviewer_persona():
    """PERSONA_NAME 定数と output[persona] が一致 (BMAD reviewer)."""
    assert rp.PERSONA_NAME == "reviewer"
    for fn, args in [
        (rp.plan_review, ("task_review", ["A-1"])),
    ]:
        out = fn(*args)
        assert out["persona"] == rp.PERSONA_NAME
