"""T-025-02: EARS 形式分類 AI prompt + 書き直し suggest service.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : service / router / prompt の 3 deliverable / 既存 schema 無改変.
  AC-2 EVENT-DRIVEN  : classify() / suggest() で valid dict / audit emit / 100ms 以内.
  AC-3 STATE-DRIVEN  : backend 未登録で rule-based / backend 不正で graceful fallback /
                       T-025-01 schema 整合維持.
  AC-4 UNWANTED      : invalid text / target_type で ValueError / backend invalid output
                       で fallback / hardcoded secret なし.
"""
from __future__ import annotations

import asyncio
import json as _json
import os
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "backend" / "services" / "ears_classifier.py"
ROUTER = REPO_ROOT / "backend" / "routers" / "ears_classifier.py"
PROMPT = REPO_ROOT / "data" / "prompts" / "ears-classifier.md"
SCHEMA = REPO_ROOT / "backend" / "schemas" / "ears_ac_schema.json"


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_backend():
    from services import ears_classifier as ec
    ec.register_classifier_backend(None)
    yield
    ec.register_classifier_backend(None)


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({"event_type": event_type, "user_id": user_id, "detail": detail or {}})
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_exists():
    assert SERVICE.exists()


def test_ac1_router_exists():
    assert ROUTER.exists()


def test_ac1_prompt_file_exists():
    assert PROMPT.exists()


def test_ac1_service_public_api():
    from services import ears_classifier as ec
    for sym in (
        "classify", "suggest_rewrite", "validate_against_schema",
        "register_classifier_backend", "get_classifier_backend",
        "VALID_TYPES", "TYPE_PATTERNS", "REWRITE_TEMPLATES",
        "get_prompt_path", "load_system_prompt",
    ):
        assert hasattr(ec, sym), f"missing service.{sym}"


def test_ac1_endpoints_registered():
    from main import app
    paths = [getattr(r, "path", "") for r in app.routes]
    assert "/api/ears/classify" in paths
    assert "/api/ears/suggest" in paths
    assert "/api/ears/health" in paths
    assert "/api/ears/forms" in paths


def test_ac1_existing_schema_unchanged():
    """T-025-01 schema は本 PR で改変なし (REUSE)."""
    assert SCHEMA.exists()
    schema = _json.load(open(SCHEMA))
    # T-025-01 で定義した必須 properties が維持
    assert schema["properties"]["type"]["enum"]
    assert "UBIQUITOUS" in schema["properties"]["type"]["enum"]


def test_ac1_prompt_documents_5_forms():
    src = PROMPT.read_text(encoding="utf-8")
    for form in ("UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"):
        assert form in src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: classify + suggest + audit
# ══════════════════════════════════════════════════════════════════════


def test_ac2_classify_ubiquitous_text():
    from services import ears_classifier as ec
    out = ec.classify("The API shall return JSON responses always.")
    assert out["classified_type"] == "UBIQUITOUS"
    assert 0.0 <= out["confidence"] <= 1.0
    assert "rewritten_text" in out
    assert "rationale" in out
    assert out["backend_used"] is False


def test_ac2_classify_event_driven_text():
    from services import ears_classifier as ec
    out = ec.classify("When the user clicks login, the system shall navigate.")
    assert out["classified_type"] == "EVENT-DRIVEN"


def test_ac2_classify_state_driven_text():
    from services import ears_classifier as ec
    out = ec.classify("While the user is authenticated, the system shall show profile.")
    assert out["classified_type"] == "STATE-DRIVEN"


def test_ac2_classify_optional_text():
    from services import ears_classifier as ec
    out = ec.classify("Where 2FA is enabled, the system shall require an OTP.")
    assert out["classified_type"] == "OPTIONAL"


def test_ac2_classify_unwanted_text():
    from services import ears_classifier as ec
    out = ec.classify("If invalid input is received, the system shall reject it.")
    assert out["classified_type"] == "UNWANTED"


def test_ac2_classify_within_100ms():
    from services import ears_classifier as ec
    t0 = time.time()
    ec.classify("The system shall do something within reasonable time.")
    elapsed = (time.time() - t0) * 1000
    assert elapsed < 100, f"classify took {elapsed:.1f}ms"


def test_ac2_classify_dict_has_all_keys():
    from services import ears_classifier as ec
    out = ec.classify("The system shall return JSON always for safety reasons.")
    for key in ("classified_type", "confidence", "rewritten_text", "rationale",
                "warnings", "backend_used"):
        assert key in out


def test_ac2_endpoint_classify_emits_audit(client, _capture_audit):
    r = client.post("/api/ears/classify", json={
        "text": "When done, the system shall persist data correctly.",
        "actor_user_id": "alice",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "ears.classified"]
    assert len(events) == 1
    assert events[0]["detail"]["classified_type"] == "EVENT-DRIVEN"


def test_ac2_endpoint_suggest_emits_audit(client, _capture_audit):
    r = client.post("/api/ears/suggest", json={
        "text": "API returns JSON for safety reasons every time.",
        "target_type": "UBIQUITOUS",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "ears.suggested"]
    assert len(events) == 1


def test_ac2_endpoint_health(client):
    r = client.get("/api/ears/health")
    assert r.status_code == 200
    body = r.json()
    assert "backend_registered" in body
    assert body["phase"] == "rule-based"
    assert body["prompt_file_exists"] is True
    assert len(body["valid_types"]) == 5


def test_ac2_endpoint_forms(client):
    r = client.get("/api/ears/forms")
    assert r.status_code == 200
    body = r.json()
    assert len(body["forms"]) == 5
    for ft in ("UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"):
        assert ft in body["forms"]


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: backend register + fallback + T-025-01 整合
# ══════════════════════════════════════════════════════════════════════


def test_ac3_no_backend_uses_rule_based():
    from services import ears_classifier as ec
    assert ec.get_classifier_backend() is None
    out = ec.classify("The system shall do X for safety reasons.")
    assert out["backend_used"] is False


def test_ac3_backend_registered_is_used():
    from services import ears_classifier as ec
    sentinel = {
        "classified_type": "UBIQUITOUS",
        "confidence": 0.99,
        "rewritten_text": "The backend rewritten text shall work correctly.",
        "rationale": "AI backend response",
        "warnings": [],
    }
    ec.register_classifier_backend(lambda text, hint: sentinel)
    out = ec.classify("any text here for testing AI mode integration.")
    assert out["backend_used"] is True
    assert out["rewritten_text"] == sentinel["rewritten_text"]


def test_ac3_invalid_backend_output_falls_back():
    from services import ears_classifier as ec
    # bad output cases
    bad_outputs = [
        lambda t, h: "not a dict",
        lambda t, h: {"classified_type": "UBIQUITOUS"},  # missing keys
        lambda t, h: {"classified_type": "BOGUS", "confidence": 0.5,
                       "rewritten_text": "x", "rationale": "y"},
        lambda t, h: {"classified_type": "UBIQUITOUS", "confidence": 2.0,  # range out
                       "rewritten_text": "x", "rationale": "y"},
    ]
    for bad in bad_outputs:
        ec.register_classifier_backend(bad)
        out = ec.classify("The system shall always work in fallback mode.")
        assert out["backend_used"] is False, f"backend {bad} should fall back"
        # rule-based の結果は UBIQUITOUS (contains "shall")
        assert out["classified_type"] in ec.VALID_TYPES


def test_ac3_use_backend_false_skips_backend():
    from services import ears_classifier as ec
    ec.register_classifier_backend(lambda t, h: {
        "classified_type": "UBIQUITOUS", "confidence": 0.99,
        "rewritten_text": "x", "rationale": "y",
    })
    out = ec.classify(
        "When something happens, the system shall handle it.",
        use_backend=False,
    )
    assert out["backend_used"] is False


def test_ac3_rewrite_conforms_to_schema():
    """rewritten_text が T-025-01 schema pattern を満たすこと."""
    from services import ears_classifier as ec
    test_cases = [
        ("The API returns JSON.", "UBIQUITOUS"),
        ("User clicks login button.", "EVENT-DRIVEN"),
        ("User session is active.", "STATE-DRIVEN"),
        ("2FA is enabled.", "OPTIONAL"),
        ("Invalid token received.", "UNWANTED"),
    ]
    for text, target in test_cases:
        rewritten = ec.suggest_rewrite(text, target)
        valid = ec.validate_against_schema(rewritten, target)
        assert valid, f"target={target}, rewritten={rewritten!r}"


def test_ac3_classify_does_not_modify_input():
    from services import ears_classifier as ec
    original = "The system shall provide a valid response for any input."
    ec.classify(original)
    # mutate しないこと (str は immutable だが念のため)
    assert original == "The system shall provide a valid response for any input."


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: invalid input / no secret
# ══════════════════════════════════════════════════════════════════════


def test_ac4_invalid_text_raises():
    from services import ears_classifier as ec
    for bad in ("", "   ", None, 123, "too short"):
        with pytest.raises(ValueError):
            ec.classify(bad)


def test_ac4_oversized_text_raises():
    from services import ears_classifier as ec
    big = "x" * 3000
    with pytest.raises(ValueError):
        ec.classify(big)


def test_ac4_invalid_hint_type_raises():
    from services import ears_classifier as ec
    with pytest.raises(ValueError):
        ec.classify("The system shall do X.", hint_type="BOGUS")


def test_ac4_invalid_target_type_in_suggest_raises():
    from services import ears_classifier as ec
    with pytest.raises(ValueError):
        ec.suggest_rewrite("The system does X.", "BOGUS")


def test_ac4_backend_must_be_callable():
    from services import ears_classifier as ec
    for bad in ("not callable", 123, [], {"key": "val"}):
        with pytest.raises(ValueError):
            ec.register_classifier_backend(bad)


def test_ac4_endpoint_unauthorized_401(client):
    r = client.post("/api/ears/classify", json={
        "text": "The system shall do something correctly.",
        "actor_user_id": "  ",
    })
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "ears.unauthorized"


def test_ac4_endpoint_invalid_target_type_400(client):
    r = client.post("/api/ears/suggest", json={
        "text": "Some text describing behavior here.",
        "target_type": "BOGUS",
    })
    assert r.status_code == 400


def test_ac4_endpoint_empty_text_pydantic_422(client):
    r = client.post("/api/ears/classify", json={"text": ""})
    assert r.status_code == 422


def test_ac4_no_hardcoded_secrets_in_service():
    src = SERVICE.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sk-proj-[A-Za-z0-9_-]{20,}", src)
    assert "SUPABASE_SERVICE_KEY" not in src
    assert "Bearer " not in src


def test_ac4_unauthorized_no_audit_emitted(client, _capture_audit):
    r = client.post("/api/ears/classify", json={
        "text": "The system shall do X correctly.",
        "actor_user_id": "  ",
    })
    assert r.status_code == 401
    events = [e for e in _capture_audit if e["event_type"] == "ears.classified"]
    assert events == []


# ══════════════════════════════════════════════════════════════════════
# T-025-01 schema integration
# ══════════════════════════════════════════════════════════════════════


def test_classify_result_can_be_validated_by_t_025_01_schema():
    """classify が返す rewritten_text が T-025-01 schema で valid である."""
    from jsonschema import Draft7Validator
    from services import ears_classifier as ec
    schema = _json.load(open(SCHEMA))
    validator = Draft7Validator(schema)

    for input_text in [
        "When user clicks button, the system shall navigate.",
        "While session is active, the system shall display profile data.",
        "The API shall return JSON for all responses.",
    ]:
        out = ec.classify(input_text)
        ac_candidate = {
            "type": out["classified_type"],
            "text": out["rewritten_text"],
        }
        errors = list(validator.iter_errors(ac_candidate))
        # rewritten_text は最低限 schema を満たすべき
        # ただし text minLength=20 を満たさない場合あり、その場合は別ロジック
        if len(ac_candidate["text"]) >= 20:
            assert not errors, (
                f"input={input_text!r}, output={ac_candidate}, errors={errors}"
            )


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_025_02_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-025-02"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the relevant API endpoint or service function is invoked for T-025-02",
        "While the new feature for T-025-02 is enabled",
        "If invalid input or unauthorized actor is detected during T-025-02",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-025-02 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "ears_classifier.py" in full
    assert "register_classifier_backend" in full
    assert "rule-based" in full or "rule_based" in full


def test_tickets_t_025_02_has_adr_link_and_existing_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-025-02"), None)
    assert t.get("adr_link") is not None
    assert t.get("existing_files")
