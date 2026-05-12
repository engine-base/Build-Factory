"""T-011-04: 統合テスト指揮 AI (integration test conductor) — 4 AC.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : integration_test_conductor service + router 公開.
                       reviewer_loop / reviewer_persona / reviewer_turn_counter
                       は無改変 (REUSE invariant).
  AC-2 EVENT-DRIVEN  : run_pipeline 2 秒以内 / deterministic topological /
                       fail → reviewer_turn_counter.increment 連携.
  AC-3 STATE-DRIVEN  : process-local dict only / no DB / cross-module 定数
                       (SECTION_KEYS / REVIEW_DIMENSIONS / PERSONA_NAME)
                       再定義禁止 / GET endpoint 不変.
  AC-4 UNWANTED      : invalid target / status / 不明 deps / cycle / overflow
                       MAX_TARGETS で IntegrationTestConductorError +
                       state unchanged.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import integration_test_conductor as itc
from services import reviewer_turn_counter as rtc


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "backend" / "services" / "integration_test_conductor.py"
ROUTER = REPO_ROOT / "backend" / "routers" / "integration_test_conductor.py"
REVIEWER_LOOP = REPO_ROOT / "backend" / "services" / "reviewer_loop.py"
REVIEWER_PERSONA = REPO_ROOT / "backend" / "services" / "reviewer_persona.py"
REVIEWER_TURN = REPO_ROOT / "backend" / "services" / "reviewer_turn_counter.py"


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_state():
    itc.reset_all_state()
    rtc.reset_all_state()
    yield
    itc.reset_all_state()
    rtc.reset_all_state()


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — public surface + REUSE invariant
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_exists():
    assert SERVICE.exists()


def test_ac1_router_exists():
    assert ROUTER.exists()


@pytest.mark.parametrize("sym", [
    "add_target",
    "record_result",
    "run_pipeline",
    "get_state",
    "get_summary",
    "reset",
    "reset_all_state",
    "MAX_TARGETS",
    "MAX_TARGET_ID_LEN",
    "VALID_STATUSES",
    "IntegrationTestConductorError",
])
def test_ac1_public_symbols(sym):
    assert hasattr(itc, sym), f"missing service.{sym}"


def test_ac1_max_targets_500():
    assert itc.MAX_TARGETS == 500


def test_ac1_valid_statuses_exact():
    assert itc.VALID_STATUSES == (
        "pending", "running", "pass", "fail", "skipped",
    )


def test_ac1_reviewer_loop_unchanged():
    """REUSE invariant: reviewer_loop に conductor 依存追加なし."""
    assert "integration_test_conductor" not in REVIEWER_LOOP.read_text(
        encoding="utf-8",
    )


def test_ac1_reviewer_persona_unchanged():
    assert "integration_test_conductor" not in REVIEWER_PERSONA.read_text(
        encoding="utf-8",
    )


def test_ac1_reviewer_turn_counter_unchanged():
    """T-011-02 module は conductor を知らない (one-way dep: conductor → rtc)."""
    assert "integration_test_conductor" not in REVIEWER_TURN.read_text(
        encoding="utf-8",
    )


def test_ac1_router_add_endpoint(client):
    resp = client.post(
        "/api/integration-test/add",
        json={"target_id": "t-1"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending"


def test_ac1_router_record_endpoint(client):
    client.post("/api/integration-test/add", json={"target_id": "t-r1"})
    resp = client.post(
        "/api/integration-test/record",
        json={"target_id": "t-r1", "status": "pass"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pass"


def test_ac1_router_summary_endpoint(client):
    client.post("/api/integration-test/add", json={"target_id": "t-s1"})
    client.post("/api/integration-test/add", json={"target_id": "t-s2"})
    resp = client.get("/api/integration-test/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["pending"] == 2


def test_ac1_router_run_endpoint(client):
    client.post("/api/integration-test/add", json={"target_id": "t-run-1"})
    resp = client.post("/api/integration-test/run", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert "order" in body
    assert "t-run-1" in body["order"]


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — topological / fail → escalation
# ══════════════════════════════════════════════════════════════════════


def test_ac2_topological_order_respects_deps():
    itc.add_target("a")
    itc.add_target("b", deps=["a"])
    itc.add_target("c", deps=["a", "b"])
    result = itc.run_pipeline()
    order = result["order"]
    assert order.index("a") < order.index("b")
    assert order.index("b") < order.index("c")


def test_ac2_topological_order_deterministic():
    """同じ依存グラフを 2 回登録しても同じ order が返る."""
    itc.add_target("z")
    itc.add_target("a")
    itc.add_target("m")
    order1 = itc.run_pipeline()["order"]
    itc.reset_all_state()
    itc.add_target("z")
    itc.add_target("a")
    itc.add_target("m")
    order2 = itc.run_pipeline()["order"]
    assert order1 == order2
    # tie-break = alphabetical
    assert order1 == ["a", "m", "z"]


def test_ac2_fail_triggers_reviewer_turn_counter_increment():
    itc.add_target("t-fail")
    assert rtc.get_count("t-fail") == 0
    itc.record_result("t-fail", "fail")
    assert rtc.get_count("t-fail") == 1


def test_ac2_4th_fail_escalates_via_t_011_02():
    """T-011-02 invariant: 4th fail で escalate=True (count > MAX_TURNS_DEFAULT=3)."""
    itc.add_target("t-esc")
    for i in range(1, 5):
        r = itc.record_result("t-esc", "fail")
        if i <= 3:
            assert r["escalated"] is False, f"escalated too early at fail #{i}"
        else:
            assert r["escalated"] is True, f"not escalated at fail #{i}"


def test_ac2_run_pipeline_under_2_seconds():
    """500 targets を topological order で並べても 2 秒以内."""
    for i in range(100):
        itc.add_target(f"t-{i:03d}")
    t0 = time.time()
    result = itc.run_pipeline()
    elapsed = time.time() - t0
    assert elapsed < 2.0, f"run_pipeline took {elapsed:.2f}s for 100 targets"
    assert len(result["order"]) == 100


def test_ac2_run_pipeline_returns_ran_pending_blocked_order():
    itc.add_target("ok")
    itc.add_target("bad")
    itc.add_target("after_bad", deps=["bad"])
    itc.record_result("bad", "fail")
    result = itc.run_pipeline()
    assert result["ran"] == 0   # conductor は実行しない (sandbox 委譲)
    assert "order" in result
    assert isinstance(result["pending"], int)
    assert isinstance(result["blocked"], int)
    # after_bad は dep が fail なので blocked
    assert result["blocked"] >= 1


def test_ac2_endpoint_record_fail_escalates(client):
    client.post("/api/integration-test/add", json={"target_id": "t-ep-esc"})
    last = None
    for _ in range(4):
        resp = client.post(
            "/api/integration-test/record",
            json={"target_id": "t-ep-esc", "status": "fail"},
        )
        last = resp
    assert last.json()["escalated"] is True


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — in-memory / cross-module invariant / GET immutable
# ══════════════════════════════════════════════════════════════════════


def test_ac3_no_db_no_redis():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "aiosqlite" not in code
    assert "redis" not in code.lower()
    assert "INSERT INTO" not in code
    assert "DB_PATH" not in code


def test_ac3_no_langgraph_no_langchain():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src).lower()
    assert "langgraph" not in code
    assert "langchain" not in code


def test_ac3_no_litellm():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src).lower()
    assert "litellm" not in code


def test_ac3_no_section_keys_redefinition():
    """G15: SECTION_KEYS は mid_term_layer の責務."""
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "SECTION_KEYS" not in code


def test_ac3_no_review_dimensions_redefinition():
    """G15: REVIEW_DIMENSIONS は reviewer_loop の責務."""
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "REVIEW_DIMENSIONS" not in code


def test_ac3_no_persona_name_redefinition():
    """G15: PERSONA_NAME は reviewer_persona の責務."""
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "PERSONA_NAME" not in code


def test_ac3_get_summary_does_not_mutate(client):
    client.post("/api/integration-test/add", json={"target_id": "t-imm"})
    before = itc.get_state("t-imm")["updated_at"]
    client.get("/api/integration-test/summary")
    client.get("/api/integration-test/summary")
    after = itc.get_state("t-imm")["updated_at"]
    assert before == after


def test_ac3_get_target_does_not_mutate(client):
    client.post("/api/integration-test/add", json={"target_id": "t-getimm"})
    before = itc.get_state("t-getimm")["updated_at"]
    client.get("/api/integration-test/target/t-getimm")
    client.get("/api/integration-test/target/t-getimm")
    after = itc.get_state("t-getimm")["updated_at"]
    assert before == after


def test_ac3_reset_returns_false_for_unknown():
    assert itc.reset("never-existed") is False


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — validation / cycle / overflow
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bad_target", ["", "  ", None, 123, [], {}])
def test_ac4_invalid_target_id_raises(bad_target):
    with pytest.raises(itc.IntegrationTestConductorError):
        itc.add_target(bad_target)


def test_ac4_target_id_over_max_length_raises():
    long = "x" * (itc.MAX_TARGET_ID_LEN + 1)
    with pytest.raises(itc.IntegrationTestConductorError):
        itc.add_target(long)


@pytest.mark.parametrize("bad_status", [
    "", "OK", "PASS", "passed", "failed", None, 123, "running ",
])
def test_ac4_invalid_status_raises(bad_status):
    itc.add_target("t-bad-status")
    with pytest.raises(itc.IntegrationTestConductorError):
        itc.record_result("t-bad-status", bad_status)


def test_ac4_unknown_deps_raises():
    with pytest.raises(itc.IntegrationTestConductorError):
        itc.add_target("t-x", deps=["never-registered"])


def test_ac4_self_dep_raises():
    with pytest.raises(itc.IntegrationTestConductorError):
        itc.add_target("t-self", deps=["t-self"])


def test_ac4_cycle_detected():
    """a → b → c → a の cycle を弾く."""
    itc.add_target("a")
    itc.add_target("b", deps=["a"])
    itc.add_target("c", deps=["b"])
    # a を c に依存させると cycle
    with pytest.raises(itc.IntegrationTestConductorError) as exc_info:
        itc.add_target("a", deps=["c"])
    assert "cycle" in str(exc_info.value).lower()


def test_ac4_cycle_rollback_does_not_mutate():
    """cycle 検出時に既存 state が変わらない (rollback)."""
    itc.add_target("p")
    itc.add_target("q", deps=["p"])
    original_q = itc.get_state("q")
    with pytest.raises(itc.IntegrationTestConductorError):
        itc.add_target("p", deps=["q"])  # cycle
    # p は元の状態のまま (deps 空)
    p_state = itc.get_state("p")
    assert p_state["deps"] == []
    # q も無変化
    assert itc.get_state("q")["deps"] == original_q["deps"]


def test_ac4_overflow_max_targets_raises(monkeypatch):
    monkeypatch.setattr(itc, "MAX_TARGETS", 3)
    itc.add_target("t1")
    itc.add_target("t2")
    itc.add_target("t3")
    before_total = itc.get_summary()["total"]
    with pytest.raises(itc.IntegrationTestConductorError):
        itc.add_target("t4")
    # state は 3 のまま
    assert itc.get_summary()["total"] == before_total


def test_ac4_record_unknown_target_raises():
    with pytest.raises(itc.IntegrationTestConductorError):
        itc.record_result("never-added", "pass")


def test_ac4_empty_actor_raises():
    with pytest.raises(itc.IntegrationTestConductorError):
        itc.add_target("t-actor", actor_user_id="  ")


def test_ac4_validation_failure_does_not_mutate():
    before = itc.get_summary()["total"]
    with pytest.raises(itc.IntegrationTestConductorError):
        itc.add_target("", deps=[])  # invalid target_id
    after = itc.get_summary()["total"]
    assert before == after


def test_ac4_output_over_max_length_raises():
    itc.add_target("t-output")
    long = "x" * (itc.MAX_OUTPUT_LEN + 1)
    with pytest.raises(itc.IntegrationTestConductorError):
        itc.record_result("t-output", "pass", output=long)


def test_ac4_endpoint_400_on_invalid_target(client):
    resp = client.post(
        "/api/integration-test/add",
        json={"target_id": ""},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == (
        "integration_test_conductor.invalid_input"
    )


def test_ac4_endpoint_400_on_cycle(client):
    client.post("/api/integration-test/add", json={"target_id": "cyc-a"})
    client.post(
        "/api/integration-test/add",
        json={"target_id": "cyc-b", "deps": ["cyc-a"]},
    )
    resp = client.post(
        "/api/integration-test/add",
        json={"target_id": "cyc-a", "deps": ["cyc-b"]},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == (
        "integration_test_conductor.cycle_detected"
    )


def test_ac4_endpoint_404_on_unknown_target(client):
    resp = client.get("/api/integration-test/target/never-existed")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == (
        "integration_test_conductor.not_found"
    )


def test_ac4_endpoint_401_on_empty_actor(client):
    resp = client.post(
        "/api/integration-test/add",
        json={"target_id": "x", "actor_user_id": "  "},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == (
        "integration_test_conductor.unauthorized"
    )


def test_ac4_no_hardcoded_secret():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_011_04_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-011-04"), None)
    assert t is not None
    generic = [
        "as specified by feature F-011",
        "When the relevant API endpoint or service function is invoked for T-011-04",
        "While the new feature for T-011-04 is enabled",
        "If invalid input or unauthorized actor is detected during T-011-04",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-011-04 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "integration_test_conductor.py" in full
    assert "MAX_TARGETS" in full
    assert "VALID_STATUSES" in full
    assert "reviewer_turn_counter" in full


def test_tickets_t_011_04_has_adr_link_and_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-011-04"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert any("reviewer_turn_counter" in f for f in files)
    assert any("reviewer_loop" in f for f in files)


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
