"""T-023-05: クローン opt-in + GDPR 削除権 (30 日 grace) — 5 AC.

Production artifact 完成済
(backend/services/user_lifecycle.py + backend/routers/user_lifecycle.py +
frontend/src/app/settings/profile/page.tsx CloneOptinCard + DeleteAccount
Card + workspace-api.ts {fetchCloneOptin, setCloneOptin,
requestUserDeletion}).
本 module は **spec contract layer**.

AC マッピング:
  AC-1 UBIQUITOUS    : set/get_clone_optin + request/cancel_deletion +
                       list_pending + execute_due / router prefix
                       /api/user 6 endpoints.
  AC-2 EVENT-DRIVEN  : pending pre-check → AlreadyPendingError /
                       INSERT pending + execute_after = now + GRACE_DAYS
                       / audit user.deletion_requested.
  AC-3 STATE-DRIVEN  : cancel UPDATE status='cancelled' + audit
                       user.deletion_cancelled / execute_due 0 rows when
                       not yet due.
  AC-4 OPTIONAL      : grace_days clamp ge=0 le=365 / dry_run=True
                       returns {would_execute, ids}.
  AC-5 UNWANTED      : AlreadyPendingError → 409 {code:already_pending}
                       / no langgraph / no plain personal data log /
                       no hardcoded secret.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PY = REPO_ROOT / "backend" / "services" / "user_lifecycle.py"
ROUTER_PY = REPO_ROOT / "backend" / "routers" / "user_lifecycle.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — public API + 6 endpoints
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_and_router_exist():
    assert SERVICE_PY.exists()
    assert ROUTER_PY.exists()


def test_ac1_service_public_api_async():
    from services import user_lifecycle as ul
    for name in (
        "set_clone_optin", "get_clone_optin",
        "request_deletion", "cancel_deletion",
        "list_pending_deletions", "execute_due_deletions",
    ):
        fn = getattr(ul, name, None)
        assert callable(fn), f"user_lifecycle missing {name}"
        assert inspect.iscoroutinefunction(fn), f"{name} must be async"


def test_ac1_already_pending_error_class_exists():
    from services.user_lifecycle import AlreadyPendingError
    assert issubclass(AlreadyPendingError, Exception)


def test_ac1_router_prefix_api_user():
    src = ROUTER_PY.read_text(encoding="utf-8")
    assert re.search(
        r"APIRouter\(\s*prefix\s*=\s*[\"']/api/user[\"']",
        src,
    )


def test_ac1_six_endpoints():
    src = ROUTER_PY.read_text(encoding="utf-8")
    # POST /clone-optin
    assert re.search(r"@router\.post\(\s*[\"']/clone-optin[\"']", src)
    # GET /clone-optin
    assert re.search(r"@router\.get\(\s*[\"']/clone-optin[\"']", src)
    # POST /deletion
    assert re.search(r"@router\.post\(\s*[\"']/deletion[\"']", src)
    # DELETE /deletion/{request_id}
    assert re.search(r"@router\.delete\(\s*[\"']/deletion/\{request_id\}[\"']", src)
    # GET /deletion/pending
    assert re.search(r"@router\.get\(\s*[\"']/deletion/pending[\"']", src)
    # POST /deletion/execute-due
    assert re.search(r"@router\.post\(\s*[\"']/deletion/execute-due[\"']", src)


def test_ac1_grace_days_constant_30():
    from services.user_lifecycle import GRACE_DAYS
    assert GRACE_DAYS == 30


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — pending pre-check + INSERT + execute_after + audit
# ══════════════════════════════════════════════════════════════════════


def test_ac2_request_deletion_pre_checks_pending():
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def request_deletion[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    # SELECT id FROM user_deletion_requests WHERE user_id = ? AND status = 'pending'
    assert re.search(
        r"SELECT\s+id\s+FROM\s+user_deletion_requests\s+WHERE\s+user_id\s*=\s*\?\s+AND\s+status\s*=\s*'pending'",
        body,
        re.IGNORECASE,
    )
    assert "AlreadyPendingError" in body


def test_ac2_insert_pending_with_execute_after():
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def request_deletion[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert re.search(
        r"INSERT\s+INTO\s+user_deletion_requests\s*\([^)]*execute_after",
        body,
        re.IGNORECASE,
    )
    assert "'pending'" in body
    assert "execute_after" in body


def test_ac2_emits_deletion_requested_audit():
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def request_deletion[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "user.deletion_requested" in body


def test_ac2_response_includes_request_id_execute_after():
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def request_deletion[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "request_id" in body
    assert "execute_after" in body


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — cancel sets cancelled + audit / execute_due no-op
# ══════════════════════════════════════════════════════════════════════


def test_ac3_cancel_updates_status_cancelled():
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def cancel_deletion[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert re.search(
        r"UPDATE\s+user_deletion_requests[\s\S]+?status\s*=\s*'cancelled'",
        body,
        re.IGNORECASE,
    )
    assert "cancelled_at" in body


def test_ac3_cancel_emits_audit():
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def cancel_deletion[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "user.deletion_cancelled" in body


def test_ac3_execute_due_only_processes_overdue():
    src = SERVICE_PY.read_text(encoding="utf-8")
    # list_pending_deletions due_only=True で execute_after <= now の filter
    m = re.search(
        r"async def list_pending_deletions[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "due_only" in body
    assert re.search(r"execute_after\s*<=", body)


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — grace_days clamp + dry_run preview
# ══════════════════════════════════════════════════════════════════════


def test_ac4_grace_days_clamped_in_request_body():
    src = ROUTER_PY.read_text(encoding="utf-8")
    # grace_days: int = Field(default=GRACE_DAYS, ge=0, le=365)
    assert re.search(
        r"grace_days\s*:\s*int\s*=\s*Field\([\s\S]+?ge\s*=\s*0[\s\S]+?le\s*=\s*365",
        src,
    )


def test_ac4_execute_due_dry_run_returns_preview():
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def execute_due_deletions[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "dry_run" in body
    assert "would_execute" in body


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — AlreadyPending → 409 / no langgraph / no plain log
# ══════════════════════════════════════════════════════════════════════


def test_ac5_router_maps_already_pending_to_409():
    src = ROUTER_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def request_user_deletion[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    # except AlreadyPendingError as e: raise HTTPException(409, ...)
    assert "AlreadyPendingError" in body
    assert re.search(
        r"status_code\s*=\s*409[\s\S]+?already_pending",
        body,
    )


def test_ac5_no_langgraph_langchain_litellm():
    for path in (SERVICE_PY, ROUTER_PY):
        src = path.read_text(encoding="utf-8").lower()
        for bad in ("langgraph", "langchain", "litellm"):
            assert bad not in src, f"{path.name} imports {bad}"


def test_ac5_no_plain_personal_data_in_print_logger():
    """reason / user_id 等の personal data を print / logger に出力していない."""
    for path in (SERVICE_PY, ROUTER_PY):
        src = path.read_text(encoding="utf-8")
        # print(... reason ...) 等の直接出力が無い
        leaks = re.findall(
            r"(?:print|logger\.\w+)\([^)]*\breason\b[^)]*\)",
            src,
        )
        assert not leaks, f"{path.name} prints reason: {leaks}"


def test_ac5_no_hardcoded_supabase_or_anthropic_key():
    for path in (SERVICE_PY, ROUTER_PY):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_023_05_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-023-05"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == [
        "UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED",
    ]


def test_tickets_t_023_05_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-023-05"), None)
    assert t.get("adr_link") is not None
    assert "ADR-010" in t["adr_link"]
    files = t.get("existing_files", [])
    assert "backend/services/user_lifecycle.py" in files
    assert "backend/routers/user_lifecycle.py" in files


def test_tickets_t_023_05_ac_mentions_concrete_symbols():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-023-05"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "set_clone_optin",
        "get_clone_optin",
        "request_deletion",
        "cancel_deletion",
        "execute_due_deletions",
        "AlreadyPendingError",
        "GRACE_DAYS",
        "user_deletion_requests",
        "already_pending",
        "user.deletion_requested",
        "user.deletion_cancelled",
        "dry_run",
        "ADR-010",
    ):
        assert sym in full, f"T-023-05 AC missing: {sym}"
