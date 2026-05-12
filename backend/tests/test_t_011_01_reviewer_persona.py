"""T-011-01: Reviewer AI persona + Plan/Gen/Eval (REFACTOR / new wrapper) — 4 AC.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : reviewer_persona service + router 公開. REVIEW_DIMENSIONS REUSE.
                       既存 reviewer.py / reviewer_loop.py 無改変.
  AC-2 EVENT-DRIVEN  : 2 秒以内 / structured dict / chain Plan → Gen → Eval.
  AC-3 STATE-DRIVEN  : backend 未登録 → deterministic / no DB write /
                       REVIEW_DIMENSIONS 不変 / hook は 3 phase 外で呼ばない.
  AC-4 UNWANTED      : invalid review_kind / 空 artifact_ids / score 範囲外 /
                       backend 不正出力 → ReviewerPersonaError + fallback.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import reviewer_persona as rp
from services.reviewer_loop import REVIEW_DIMENSIONS


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "backend" / "services" / "reviewer_persona.py"
ROUTER = REPO_ROOT / "backend" / "routers" / "reviewer_persona.py"
EXISTING_LOOP = REPO_ROOT / "backend" / "services" / "reviewer_loop.py"
EXISTING_ROUTER = REPO_ROOT / "backend" / "routers" / "reviewer.py"


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
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_exists():
    assert SERVICE.exists()


def test_ac1_router_exists():
    assert ROUTER.exists()


def test_ac1_public_api():
    for sym in (
        "plan_review", "generate_review", "evaluate_review",
        "run_plan_gen_eval", "register_persona_backend",
        "get_persona_backend", "list_review_kinds",
        "ReviewerPersonaError",
        "VALID_REVIEW_KINDS", "VALID_PHASES",
        "DEFAULT_PASS_THRESHOLD", "PERSONA_NAME",
    ):
        assert hasattr(rp, sym), f"missing service.{sym}"


def test_ac1_persona_name_is_reviewer():
    assert rp.PERSONA_NAME == "reviewer"


def test_ac1_review_dimensions_reused_from_reviewer_loop():
    """REVIEW_DIMENSIONS は reviewer_loop からそのまま REUSE."""
    src = SERVICE.read_text(encoding="utf-8")
    assert "from services.reviewer_loop import REVIEW_DIMENSIONS" in src
    # plan should use these dimensions for rule-based fallback
    plan = rp.plan_review("task_review", ["A-1"])
    assert plan["dimensions"] == list(REVIEW_DIMENSIONS["task_review"])


def test_ac1_existing_reviewer_loop_unchanged():
    """既存 reviewer_loop に reviewer_persona 依存追加なし (REFACTOR invariant)."""
    src = EXISTING_LOOP.read_text(encoding="utf-8")
    assert "reviewer_persona" not in src


def test_ac1_existing_reviewer_router_unchanged():
    src = EXISTING_ROUTER.read_text(encoding="utf-8")
    assert "reviewer_persona" not in src


def test_ac1_router_mounted(client):
    resp = client.post(
        "/api/reviewer-persona/plan",
        json={"review_kind": "task_review", "target_artifact_ids": ["A-1"]},
    )
    assert resp.status_code == 200, resp.text


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac2_plan_review_structure():
    r = rp.plan_review("task_review", ["A-1", "A-2"])
    assert r["persona"] == "reviewer"
    assert r["phase"] == "plan"
    assert r["review_kind"] == "task_review"
    assert isinstance(r["dimensions"], list)
    assert len(r["dimensions"]) >= 5
    assert r["backend_used"] is False
    assert isinstance(r["latency_ms"], int)


def test_ac2_generate_review_structure():
    plan = rp.plan_review("task_review", ["A-1"])
    review = rp.generate_review(plan)
    assert review["phase"] == "generate"
    assert isinstance(review["findings"], list)
    assert len(review["findings"]) == len(plan["dimensions"])
    for f in review["findings"]:
        assert "dimension" in f and "note" in f and "severity" in f


def test_ac2_evaluate_review_structure():
    plan = rp.plan_review("task_review", ["A-1"])
    review = rp.generate_review(plan)
    ev = rp.evaluate_review(review)
    assert ev["phase"] == "evaluate"
    assert 0.0 <= ev["score"] <= 1.0
    assert ev["status"] in ("pass", "needs_revision")
    assert isinstance(ev["weakness"], list)


def test_ac2_full_chain_returns_all_three():
    out = rp.run_plan_gen_eval("integration", ["A-1", "A-2"])
    assert "plan" in out
    assert "review" in out
    assert "evaluation" in out
    assert out["status"] in ("pass", "needs_revision")


def test_ac2_within_2_seconds():
    t0 = time.time()
    rp.run_plan_gen_eval("task_review", ["A-1", "A-2", "A-3"])
    elapsed = time.time() - t0
    assert elapsed < 2.0


def test_ac2_endpoint_plan(client):
    resp = client.post(
        "/api/reviewer-persona/plan",
        json={"review_kind": "task_review", "target_artifact_ids": ["A-1"]},
    )
    assert resp.status_code == 200
    assert resp.json()["phase"] == "plan"


def test_ac2_endpoint_full_chain(client):
    resp = client.post(
        "/api/reviewer-persona/full",
        json={"review_kind": "task_review", "target_artifact_ids": ["A-1"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "plan" in body
    assert "review" in body
    assert "evaluation" in body


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac3_backend_unregistered_uses_rule_based():
    assert rp.get_persona_backend() is None
    out = rp.run_plan_gen_eval("task_review", ["A-1"])
    assert out["backend_used"] is False


def test_ac3_backend_registered_used_when_valid():
    def fake_backend(phase, payload):
        if phase == "plan":
            return {"dimensions": ["dim-A", "dim-B"], "rationale": "AI plan"}
        if phase == "generate":
            return {"findings": [
                {"dimension": "dim-A", "note": "x", "severity": "info"},
                {"dimension": "dim-B", "note": "y", "severity": "info"},
            ]}
        if phase == "evaluate":
            return {"score": 0.85, "weakness": ["minor"]}
        return {}

    rp.register_persona_backend(fake_backend)
    out = rp.run_plan_gen_eval("task_review", ["A-1"])
    assert out["backend_used"] is True
    assert out["plan"]["dimensions"] == ["dim-A", "dim-B"]
    assert out["evaluation"]["score"] == 0.85


def test_ac3_deterministic_rule_based():
    r1 = rp.plan_review("task_review", ["A-1"])
    r2 = rp.plan_review("task_review", ["A-1"])
    assert r1["dimensions"] == r2["dimensions"]
    assert r1["review_kind"] == r2["review_kind"]


def test_ac3_no_db_write():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "INSERT INTO" not in code
    assert "aiosqlite" not in code
    assert "DB_PATH" not in code


def test_ac3_no_langgraph_no_langchain():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src).lower()
    assert "langgraph" not in code
    assert "langchain" not in code


def test_ac3_review_dimensions_invariant():
    """RUN 後 REVIEW_DIMENSIONS が変化しない (read-only REUSE)."""
    before = {k: list(v) for k, v in REVIEW_DIMENSIONS.items()}
    rp.run_plan_gen_eval("task_review", ["A-1"])
    after = {k: list(v) for k, v in REVIEW_DIMENSIONS.items()}
    assert before == after


def test_ac3_backend_called_only_in_3_phases():
    """register された backend は plan/generate/evaluate でしか呼ばれない."""
    phases_seen: list[str] = []

    def tracking_backend(phase, payload):
        phases_seen.append(phase)
        return None  # backend が None を返すと fallback

    rp.register_persona_backend(tracking_backend)
    rp.run_plan_gen_eval("task_review", ["A-1"])
    assert set(phases_seen) <= {"plan", "generate", "evaluate"}
    assert phases_seen == ["plan", "generate", "evaluate"]


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bad_kind", ["BOGUS", "", None, 123, "task-review"])
def test_ac4_invalid_review_kind_raises(bad_kind):
    with pytest.raises(rp.ReviewerPersonaError):
        rp.plan_review(bad_kind, ["A-1"])


@pytest.mark.parametrize("bad_ids", [None, "not list", [], ["", "  "], [1, 2]])
def test_ac4_invalid_artifact_ids_raises(bad_ids):
    with pytest.raises(rp.ReviewerPersonaError):
        rp.plan_review("task_review", bad_ids)


def test_ac4_artifact_ids_over_max_raises():
    too_many = [f"A-{i}" for i in range(rp.MAX_ARTIFACT_IDS + 1)]
    with pytest.raises(rp.ReviewerPersonaError):
        rp.plan_review("task_review", too_many)


@pytest.mark.parametrize("bad_score", [-0.1, 1.1, None, True, "0.5"])
def test_ac4_invalid_pass_threshold_raises(bad_score):
    plan = rp.plan_review("task_review", ["A-1"])
    review = rp.generate_review(plan)
    with pytest.raises(rp.ReviewerPersonaError):
        rp.evaluate_review(review, pass_threshold=bad_score)


def test_ac4_empty_actor_raises():
    with pytest.raises(rp.ReviewerPersonaError):
        rp.plan_review("task_review", ["A-1"], actor_user_id="  ")


def test_ac4_register_non_callable_raises():
    with pytest.raises(rp.ReviewerPersonaError):
        rp.register_persona_backend(12345)


def test_ac4_backend_malformed_falls_back():
    def bad_backend(phase, payload):
        return "not a dict"

    rp.register_persona_backend(bad_backend)
    out = rp.run_plan_gen_eval("task_review", ["A-1"])
    assert out["backend_used"] is False


def test_ac4_backend_score_out_of_range_falls_back():
    def bad_eval_backend(phase, payload):
        if phase == "evaluate":
            return {"score": 9.99}  # out of range
        return None  # plan/generate use rule-based

    rp.register_persona_backend(bad_eval_backend)
    out = rp.run_plan_gen_eval("task_review", ["A-1"])
    # evaluation fell back to rule-based
    assert out["evaluation"]["backend_used"] is False
    assert 0.0 <= out["evaluation"]["score"] <= 1.0


def test_ac4_endpoint_400_on_bad_kind(client):
    resp = client.post(
        "/api/reviewer-persona/plan",
        json={"review_kind": "BOGUS", "target_artifact_ids": ["A-1"]},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "reviewer_persona.invalid_input"


def test_ac4_endpoint_400_on_empty_ids(client):
    resp = client.post(
        "/api/reviewer-persona/plan",
        json={"review_kind": "task_review", "target_artifact_ids": []},
    )
    assert resp.status_code == 400


def test_ac4_endpoint_401_on_empty_actor(client):
    resp = client.post(
        "/api/reviewer-persona/plan",
        json={
            "review_kind": "task_review",
            "target_artifact_ids": ["A-1"],
            "actor_user_id": "  ",
        },
    )
    assert resp.status_code == 401


def test_ac4_no_hardcoded_secret():
    import re
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _strip_comments(src: str) -> str:
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


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_011_01_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-011-01"), None)
    assert t is not None
    generic = [
        "as specified by feature F-011",
        "When the relevant API endpoint or service function is invoked for T-011-01",
        "While refactoring for T-011-01 is in progress",
        "If invalid input or unauthorized actor is detected during T-011-01",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-011-01 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "reviewer_persona.py" in full
    assert "register_persona_backend" in full
    assert "REVIEW_DIMENSIONS" in full


def test_tickets_t_011_01_has_adr_link():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-011-01"), None)
    assert t.get("adr_link") is not None
