"""T-011-02: 3 ターンカウンター + state 管理 — 4 AC.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : reviewer_turn_counter service + router 公開.
                       reviewer_loop / reviewer_persona は無改変 (REUSE invariant).
  AC-2 EVENT-DRIVEN  : increment N 回目で {count: N, escalate: N>threshold} /
                       2 秒以内 / list_active 安定 sort.
  AC-3 STATE-DRIVEN  : process-local dict only / no DB write /
                       REVIEW_DIMENSIONS / PERSONA_NAME 再定義禁止 /
                       GET endpoint で mutate しない.
  AC-4 UNWANTED      : invalid target / threshold / actor / overflow MAX_COUNT
                       → ReviewerTurnCounterError + state unchanged.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import reviewer_turn_counter as rtc


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "backend" / "services" / "reviewer_turn_counter.py"
ROUTER = REPO_ROOT / "backend" / "routers" / "reviewer_turn_counter.py"
EXISTING_LOOP = REPO_ROOT / "backend" / "services" / "reviewer_loop.py"
EXISTING_PERSONA = REPO_ROOT / "backend" / "services" / "reviewer_persona.py"


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_state():
    rtc.reset_all_state()
    yield
    rtc.reset_all_state()


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_exists():
    assert SERVICE.exists()


def test_ac1_router_exists():
    assert ROUTER.exists()


def test_ac1_public_api():
    for sym in (
        "increment", "get_count", "get_state", "reset",
        "should_escalate", "list_active", "reset_all_state",
        "MAX_TURNS_DEFAULT", "MIN_THRESHOLD", "MAX_THRESHOLD",
        "MAX_COUNT", "MAX_TARGET_ID_LEN",
        "ReviewerTurnCounterError",
    ):
        assert hasattr(rtc, sym), f"missing service.{sym}"


def test_ac1_max_turns_default_is_3():
    assert rtc.MAX_TURNS_DEFAULT == 3


def test_ac1_existing_reviewer_loop_unchanged():
    """REFACTOR invariant: reviewer_loop.py に turn_counter 依存追加なし."""
    src = EXISTING_LOOP.read_text(encoding="utf-8")
    assert "reviewer_turn_counter" not in src


def test_ac1_existing_reviewer_persona_unchanged():
    src = EXISTING_PERSONA.read_text(encoding="utf-8")
    assert "reviewer_turn_counter" not in src


def test_ac1_router_increment_endpoint(client):
    resp = client.post(
        "/api/reviewer-turn/increment",
        json={"target_id": "t-001"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 1


def test_ac1_router_get_endpoint(client):
    client.post("/api/reviewer-turn/increment", json={"target_id": "t-002"})
    resp = client.get("/api/reviewer-turn/t-002")
    assert resp.status_code == 200
    assert resp.json()["target_id"] == "t-002"


def test_ac1_router_active_endpoint(client):
    for tid in ("t-1", "t-2", "t-3"):
        client.post("/api/reviewer-turn/increment", json={"target_id": tid})
    resp = client.get("/api/reviewer-turn/active")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 3
    assert isinstance(body["items"], list)


def test_ac1_router_reset_endpoint(client):
    client.post("/api/reviewer-turn/increment", json={"target_id": "t-r"})
    resp = client.post(
        "/api/reviewer-turn/reset",
        json={"target_id": "t-r"},
    )
    assert resp.status_code == 200
    assert resp.json()["removed"] is True


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac2_increment_returns_structured_dict():
    r = rtc.increment("target-1")
    assert r["target_id"] == "target-1"
    assert r["count"] == 1
    assert r["threshold"] == 3
    assert r["escalate"] is False
    assert "last_updated_at" in r
    assert "first_seen_at" in r


def test_ac2_escalate_after_4th_turn():
    """3 ターンは pass, 4 ターン目で escalate=True (count > threshold=3)."""
    for i in range(1, 5):
        r = rtc.increment("t-esc")
        if i <= 3:
            assert r["escalate"] is False, f"escalate at count={i}"
        else:
            assert r["escalate"] is True, f"not escalating at count={i}"


def test_ac2_increment_within_2_seconds():
    t0 = time.time()
    for i in range(100):
        rtc.increment(f"t-{i}")
    elapsed = time.time() - t0
    assert elapsed < 2.0


def test_ac2_list_active_stable_sort():
    """count desc + target_id asc on ties."""
    rtc.increment("t-a")  # 1
    rtc.increment("t-b")  # 1
    rtc.increment("t-b")  # 2
    rtc.increment("t-c")  # 1
    rtc.increment("t-c")  # 2
    rtc.increment("t-c")  # 3
    items = rtc.list_active()
    counts = [(it["count"], it["target_id"]) for it in items]
    # count desc, target_id asc on ties
    assert counts == [(3, "t-c"), (2, "t-b"), (1, "t-a")]


def test_ac2_should_escalate_strictly_greater_than():
    rtc.increment("t-th", threshold=3)
    rtc.increment("t-th", threshold=3)
    rtc.increment("t-th", threshold=3)
    # count = 3, not strictly greater than 3 → False
    assert rtc.should_escalate("t-th") is False
    rtc.increment("t-th", threshold=3)
    # count = 4, > 3 → True
    assert rtc.should_escalate("t-th") is True


def test_ac2_endpoint_returns_escalate(client):
    for _ in range(4):
        resp = client.post(
            "/api/reviewer-turn/increment",
            json={"target_id": "t-ep"},
        )
    assert resp.json()["escalate"] is True


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac3_no_db_no_redis():
    """process-local dict only."""
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


def test_ac3_no_section_keys_redefinition():
    """G15: cross-module invariant. SECTION_KEYS は本 module で再定義しない."""
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "SECTION_KEYS" not in code


def test_ac3_no_review_dimensions_redefinition():
    """REVIEW_DIMENSIONS は reviewer_loop の責務 / 本 module で再定義禁止."""
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "REVIEW_DIMENSIONS" not in code


def test_ac3_no_persona_name_redefinition():
    """PERSONA_NAME は reviewer_persona の責務 / 本 module で再定義禁止."""
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "PERSONA_NAME" not in code


def test_ac3_get_endpoint_does_not_mutate_state(client):
    client.post("/api/reviewer-turn/increment", json={"target_id": "t-imm"})
    before = rtc.get_count("t-imm")
    client.get("/api/reviewer-turn/t-imm")
    client.get("/api/reviewer-turn/t-imm")
    after = rtc.get_count("t-imm")
    assert before == after


def test_ac3_active_endpoint_does_not_mutate_state(client):
    client.post("/api/reviewer-turn/increment", json={"target_id": "t-act"})
    before = rtc.get_count("t-act")
    client.get("/api/reviewer-turn/active")
    after = rtc.get_count("t-act")
    assert before == after


def test_ac3_reset_returns_false_for_unknown():
    assert rtc.reset("never-existed") is False


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bad_target", ["", "  ", None, 123, [], {}])
def test_ac4_invalid_target_id_raises(bad_target):
    with pytest.raises(rtc.ReviewerTurnCounterError):
        rtc.increment(bad_target)


def test_ac4_target_id_over_max_length_raises():
    long = "x" * (rtc.MAX_TARGET_ID_LEN + 1)
    with pytest.raises(rtc.ReviewerTurnCounterError):
        rtc.increment(long)


@pytest.mark.parametrize("bad_threshold", [0, -1, 21, 1000, True, "3", 3.5])
def test_ac4_invalid_threshold_raises(bad_threshold):
    with pytest.raises(rtc.ReviewerTurnCounterError):
        rtc.increment("t-th-bad", threshold=bad_threshold)


def test_ac4_empty_actor_raises():
    with pytest.raises(rtc.ReviewerTurnCounterError):
        rtc.increment("t-actor", actor_user_id="  ")


def test_ac4_validation_failure_does_not_mutate():
    """invalid input は raise しても state を mutate しない."""
    before = rtc.get_count("t-vmut")
    with pytest.raises(rtc.ReviewerTurnCounterError):
        rtc.increment("t-vmut", threshold=999)  # threshold out of range
    after = rtc.get_count("t-vmut")
    assert before == after == 0


def test_ac4_overflow_max_count_raises(monkeypatch):
    """MAX_COUNT 到達後 +1 で raise + 既存 state 不変."""
    monkeypatch.setattr(rtc, "MAX_COUNT", 3)
    rtc.increment("t-overflow")
    rtc.increment("t-overflow")
    rtc.increment("t-overflow")
    # count = 3 = MAX_COUNT. +1 で raise
    with pytest.raises(rtc.ReviewerTurnCounterError):
        rtc.increment("t-overflow")
    # state は 3 のまま (mutate しない)
    assert rtc.get_count("t-overflow") == 3


def test_ac4_endpoint_400_on_invalid_target(client):
    resp = client.post(
        "/api/reviewer-turn/increment",
        json={"target_id": ""},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "reviewer_turn_counter.invalid_input"


def test_ac4_endpoint_422_on_bad_threshold(client):
    resp = client.post(
        "/api/reviewer-turn/increment",
        json={"target_id": "x", "threshold": 999},
    )
    assert resp.status_code == 422


def test_ac4_endpoint_401_on_empty_actor(client):
    resp = client.post(
        "/api/reviewer-turn/increment",
        json={"target_id": "x", "actor_user_id": "  "},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "reviewer_turn_counter.unauthorized"


def test_ac4_endpoint_404_on_unknown_target(client):
    resp = client.get("/api/reviewer-turn/never-existed")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "reviewer_turn_counter.not_found"


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


def test_tickets_t_011_02_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-011-02"), None)
    assert t is not None
    generic = [
        "as specified by feature F-011",
        "When the relevant API endpoint or service function is invoked for T-011-02",
        "While the new feature for T-011-02 is enabled",
        "If invalid input or unauthorized actor is detected during T-011-02",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-011-02 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "reviewer_turn_counter.py" in full
    assert "MAX_TURNS_DEFAULT" in full
    assert "escalate" in full


def test_tickets_t_011_02_has_adr_link_and_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-011-02"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert "TBD" not in str(files)
    assert any("reviewer_loop" in f for f in files)
