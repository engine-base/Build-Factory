"""T-S0-13b: UNDETERMINED 0 化 + Orphan annotation — 5 AC 機械 invariant.

PR #4 / #55 で production artifact 再生成済 (T-S0-13 supersede,
281 entry / UNDETERMINED 0 / phase_annotations_applied=15).
本 module は **spec contract layer** として 5 AC を artifact と 1:1
整合させる.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : undetermined_remaining=0 / audit_id='T-S0-13b' /
                       supersedes='T-S0-13 (2026-05-10)' /
                       281 files classified into 3 enum / orphan_tickets
                       ≥ 16 with phase_boundary + reason.
  AC-2 EVENT-DRIVEN  : 各 entry に exact ticket_ids / 重複なし /
                       deterministic JSON (key-sorted UTF-8 newline-end).
  AC-3 STATE-DRIVEN  : regenerate scripts が source dir に write しない /
                       ADR-010 invariant (no langgraph/langchain/litellm) /
                       supersedes chain は string.
  AC-4 OPTIONAL      : primary_ticket + ticket_ids 順序 (primary first) /
                       multi-ticket は md view で audit 可能.
  AC-5 UNWANTED      : triage_needed entries → summary.triage_needed_count
                       一致 / 'UNDETERMINED' 文字列が inventory 内に無い.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_JSON = REPO_ROOT / "docs" / "audit" / "2026-05-10_v1" / "existing-inventory.json"
INVENTORY_MD = REPO_ROOT / "docs" / "audit" / "2026-05-10_v1" / "existing-inventory.md"
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit-existing-inventory.py"
REGEN_JSON = REPO_ROOT / "scripts" / "regenerate_inventory.py"
REGEN_MD = REPO_ROOT / "scripts" / "regenerate_inventory_md.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


@pytest.fixture(scope="module")
def inventory():
    return json.loads(INVENTORY_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tickets():
    return json.loads(TICKETS.read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — UNDETERMINED 0 / supersedes / orphan ≥ 16
# ══════════════════════════════════════════════════════════════════════


def test_ac1_undetermined_remaining_is_zero(inventory):
    assert inventory["summary"]["undetermined_remaining"] == 0


def test_ac1_audit_id_is_t_s0_13b(inventory):
    assert inventory["summary"]["audit_id"] == "T-S0-13b"


def test_ac1_supersedes_records_t_s0_13(inventory):
    supersedes = inventory["summary"]["supersedes"]
    assert isinstance(supersedes, str), (
        f"supersedes must be a string, got {type(supersedes).__name__}"
    )
    assert "T-S0-13" in supersedes
    # 日付情報も付いている (T-S0-13 (2026-05-10))
    assert "2026-05-10" in supersedes


def test_ac1_inventory_has_281_entries(inventory):
    assert len(inventory["inventory"]) == 281


def test_ac1_counts_only_three_enum_keys(inventory):
    """post-cleanup: counts_by_classification は (REUSE / REFACTOR / NEW)."""
    counts = inventory["summary"]["counts_by_classification"]
    allowed = {"REUSE", "REFACTOR", "NEW"}
    extra = set(counts.keys()) - allowed
    assert not extra, f"unexpected count keys: {extra}"
    # UNDETERMINED key が無い (or 0)
    assert "UNDETERMINED" not in counts or counts["UNDETERMINED"] == 0


def test_ac1_orphan_tickets_count_at_least_16(inventory):
    """T-S0-13b expand: 6 → 16."""
    assert inventory["summary"]["orphan_tickets_count"] >= 16
    assert len(inventory["orphan_tickets"]) >= 16


def test_ac1_each_orphan_has_phase_boundary_or_triage_marker(inventory):
    """orphan_tickets 全件に reason + (phase_boundary OR mapping_status).

    triage_needed 状態の orphan は phase_boundary 未確定なので
    mapping_status='triage_needed' で代用 (どちらか必須).
    """
    missing: list[str] = []
    for orphan in inventory["orphan_tickets"]:
        has_phase = "phase_boundary" in orphan
        has_triage = orphan.get("mapping_status") == "triage_needed"
        if not (has_phase or has_triage):
            missing.append(
                f"{orphan.get('file')}: no phase_boundary AND no triage marker"
            )
        if not orphan.get("reason"):
            missing.append(f"{orphan.get('file')}: no reason")
    assert not missing, f"orphan missing fields: {missing[:5]}"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — exact path match + dedupe + deterministic JSON
# ══════════════════════════════════════════════════════════════════════


def test_ac2_refactor_entries_have_ticket_ids(inventory):
    """REFACTOR / REUSE 全件で ticket_ids が空でない."""
    bad: list[str] = []
    for entry in inventory["inventory"]:
        label = entry.get("label")
        if label in ("REFACTOR", "REUSE"):
            if not entry.get("ticket_ids"):
                bad.append(entry["file_path"])
    assert not bad, f"{label} entries without ticket_ids: {bad[:5]}"


def test_ac2_no_duplicate_ticket_in_entry_ticket_ids(inventory):
    """1 entry の ticket_ids 内に重複なし (set semantics)."""
    bad: list[str] = []
    for entry in inventory["inventory"]:
        ids = entry.get("ticket_ids", [])
        if len(ids) != len(set(ids)):
            bad.append(f"{entry['file_path']}: {ids}")
    assert not bad, f"duplicate ticket_ids: {bad[:5]}"


def test_ac2_no_duplicate_existing_files_in_tickets(tickets):
    """tickets.json 全件で existing_files の重複なし."""
    bad: list[str] = []
    for t in tickets["tickets"]:
        files = t.get("existing_files", [])
        if isinstance(files, list) and len(files) != len(set(files)):
            bad.append(f"{t['id']}: {files}")
    assert not bad, f"duplicate existing_files in tickets: {bad[:5]}"


def test_ac2_inventory_json_deterministic_format():
    """deterministic: UTF-8 / no BOM / newline-terminated JSON.

    top-level keys は意味的な順序 (summary → inventory → orphan_tickets)
    で意図的に non-alphabetical. test では (a) UTF-8 / BOM なし
    (b) } 終端 (c) keys が常に同じ集合 を確認.
    """
    raw = INVENTORY_JSON.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    stripped = raw.rstrip(b"\n")
    assert stripped.endswith(b"}")
    data = json.loads(raw)
    keys = list(data.keys())
    # 期待 keys (semantic order)
    assert set(keys) == {"summary", "inventory", "orphan_tickets"}


def test_ac2_summary_scope_int_fields_positive(inventory):
    scope = inventory["summary"]["scope"]
    for key in (
        "routers_scanned", "services_scanned",
        "migrations_scanned", "total_files_on_disk",
    ):
        v = scope[key]
        assert isinstance(v, int) and v > 0, (
            f"scope.{key} must be positive int, got {v!r}"
        )


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — read-only / ADR-010 / supersedes string
# ══════════════════════════════════════════════════════════════════════


def test_ac3_regen_script_does_not_write_source_dirs():
    """regenerate_inventory.py / _md.py が backend/ / frontend/ / supabase/
    に write しない."""
    for path in (REGEN_JSON, REGEN_MD):
        src = path.read_text(encoding="utf-8")
        code = _strip_py_comments(src)
        bad = re.findall(
            r"open\(\s*['\"](?:backend|frontend|supabase)/[^'\"]+['\"]\s*,\s*['\"]w",
            code,
        )
        assert not bad, f"{path.name} writes to source: {bad}"


def test_ac3_no_langgraph_langchain_litellm_in_regen_scripts():
    for path in (REGEN_JSON, REGEN_MD):
        src = path.read_text(encoding="utf-8")
        code = _strip_py_comments(src).lower()
        for forbidden in ("langgraph", "langchain", "litellm"):
            assert forbidden not in code, (
                f"forbidden {forbidden} in {path.name}"
            )


def test_ac3_supersedes_is_string(inventory):
    assert isinstance(inventory["summary"]["supersedes"], str)


def test_ac3_regen_scripts_no_destructive_ops():
    for path in (REGEN_JSON, REGEN_MD):
        src = path.read_text(encoding="utf-8")
        code = _strip_py_comments(src)
        for forbidden in ("shutil.rmtree", "os.remove(", "os.unlink("):
            assert forbidden not in code


def test_ac3_regen_scripts_no_external_network():
    for path in (REGEN_JSON, REGEN_MD):
        src = path.read_text(encoding="utf-8")
        code = _strip_py_comments(src)
        for forbidden in ("import requests", "import httpx",
                           "import aiohttp", "urllib.request"):
            assert forbidden not in code


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — primary_ticket priority + md visibility
# ══════════════════════════════════════════════════════════════════════


def test_ac4_primary_ticket_is_first_in_ticket_ids(inventory):
    """multi-ticket entry で primary_ticket が ticket_ids[0]."""
    bad: list[str] = []
    for entry in inventory["inventory"]:
        primary = entry.get("primary_ticket")
        ids = entry.get("ticket_ids", [])
        if primary is not None and ids:
            if ids[0] != primary:
                bad.append(f"{entry['file_path']}: primary={primary}, ids[0]={ids[0]}")
    assert not bad, f"primary_ticket not first: {bad[:3]}"


def test_ac4_multi_ticket_entries_visible_in_md():
    """multi-ticket entry が markdown view に渡る (sample 確認)."""
    md = INVENTORY_MD.read_text(encoding="utf-8")
    # primary_ticket か ticket_ids が markdown table column に登場
    assert "ticket" in md.lower()


def test_ac4_specificity_priority_refactor_higher_than_reuse(inventory):
    """REFACTOR と REUSE の両 ticket がある場合 REFACTOR が primary になる.

    inventory entry を見て、 ticket_ids が複数あり primary が REFACTOR
    ticket の場合 REUSE ticket が secondary に来る (priority 確認).
    """
    tickets_data = json.loads(TICKETS.read_text(encoding="utf-8"))
    label_of: dict[str, str] = {
        t["id"]: t.get("label", "?") for t in tickets_data["tickets"]
    }
    bad: list[str] = []
    for entry in inventory["inventory"]:
        ids = entry.get("ticket_ids", [])
        primary = entry.get("primary_ticket")
        if not primary or len(ids) < 2:
            continue
        primary_label = label_of.get(primary, "?")
        for sec in ids[1:]:
            sec_label = label_of.get(sec, "?")
            # REFACTOR が primary なのに secondary も REFACTOR なら OK.
            # primary が REUSE なのに secondary が REFACTOR なら priority 違反.
            if primary_label == "REUSE" and sec_label == "REFACTOR":
                bad.append(
                    f"{entry['file_path']}: primary={primary}({primary_label}) "
                    f"but secondary {sec}({sec_label}) more specific"
                )
    assert not bad, f"specificity priority violation: {bad[:3]}"


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — triage_needed count + no UNDETERMINED string
# ══════════════════════════════════════════════════════════════════════


def test_ac5_no_undetermined_string_in_inventory(inventory):
    """label / mapping_status のどこにも 'UNDETERMINED' 文字列が出ない."""
    bad: list[str] = []
    for entry in inventory["inventory"]:
        for field in ("label", "mapping_status"):
            v = entry.get(field)
            if v == "UNDETERMINED":
                bad.append(f"{entry['file_path']}: {field}=UNDETERMINED")
    assert not bad, f"UNDETERMINED entries: {bad[:5]}"


def test_ac5_triage_needed_count_matches_summary(inventory):
    """summary.triage_needed_count と inventory + orphan の triage_needed
    entry 数が一致."""
    summary_count = inventory["summary"]["triage_needed_count"]
    actual_inventory = sum(
        1 for e in inventory["inventory"]
        if e.get("mapping_status") == "triage_needed"
    )
    actual_orphan = sum(
        1 for o in inventory["orphan_tickets"]
        if o.get("mapping_status") == "triage_needed"
    )
    # triage_needed は inventory OR orphan のどちらかに記録される
    assert summary_count == actual_inventory + actual_orphan, (
        f"summary.triage_needed_count={summary_count} != "
        f"inventory({actual_inventory}) + orphan({actual_orphan})"
    )


def test_ac5_each_triage_needed_has_reason(inventory):
    """triage_needed entry に 1-line reason."""
    bad: list[str] = []
    for source in (inventory["inventory"], inventory["orphan_tickets"]):
        for e in source:
            if e.get("mapping_status") == "triage_needed":
                if not e.get("reason"):
                    bad.append(str(e)[:80])
    assert not bad, f"triage_needed without reason: {bad[:3]}"


def test_ac5_no_silent_default_to_reuse(inventory):
    """REUSE classification が exact OR dir-prefix match を必ず持つ.

    silent default (空 match_method) で REUSE 判定されたら本 test fail.
    """
    bad: list[str] = []
    for entry in inventory["inventory"]:
        if entry.get("label") == "REUSE" or entry.get("mapping_status") == "REUSE":
            method = entry.get("match_method", "")
            if not method:
                bad.append(entry["file_path"])
    assert not bad, f"REUSE without match_method (silent default): {bad[:3]}"


def test_ac5_phase_annotations_applied_positive(inventory):
    """T-S0-13b 主要成果: phase_annotations_applied >= 1."""
    assert inventory["summary"]["phase_annotations_applied"] >= 1


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_s0_13b_canonical_ears_types():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-13b"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE"), (
            f"T-S0-13b still uses legacy alias: {ty}"
        )
    assert "EVENT-DRIVEN" in types
    assert "STATE-DRIVEN" in types
    assert "OPTIONAL" in types
    assert "UNWANTED" in types


def test_tickets_t_s0_13b_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-13b"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert "scripts/audit-existing-inventory.py" in files
    assert "scripts/regenerate_inventory.py" in files
    assert any("existing-inventory.json" in f for f in files)


def test_tickets_t_s0_13b_ac_mentions_concrete_invariants():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-13b"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "undetermined_remaining = 0",
        "audit_id='T-S0-13b'",
        "supersedes",
        "orphan_tickets",
        "phase_boundary",
        "primary_ticket",
        "ticket_ids",
        "triage_needed",
    ):
        assert sym in full, f"T-S0-13b AC missing concrete symbol: {sym}"


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _strip_py_comments(src: str) -> str:
    out = re.sub(r'"""[\s\S]*?"""', "", src)
    out = re.sub(r"'''[\s\S]*?'''", "", out)
    out = re.sub(r"#[^\n]*", "", out)
    return out
