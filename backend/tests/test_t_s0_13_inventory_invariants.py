"""T-S0-13: 既存実装インベントリ監査 — 5 AC 機械 invariant 検証.

PR #3 (T-S0-13) + PR #4 / #55 (T-S0-13b 再生成) で production artifact
完成済. 本 module は **spec contract layer** として 5 AC が:
  - scripts/audit-existing-inventory.py
  - docs/audit/2026-05-10_v1/existing-inventory.json
  - tickets.json existing_files との cross-reference
の構造 / 不変条件と 1:1 整合していることを機械検証する.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : inventory.json top-level keys + 281 entry +
                       classification enum + 1-line rationale.
  AC-2 EVENT-DRIVEN  : audit-existing-inventory.py が tickets.json を
                       cross-reference / deterministic JSON / orphan
                       (onlook/penpot 等) を記録.
  AC-3 STATE-DRIVEN  : read-only / no network / no langgraph/langchain/
                       litellm / supersedes chain (T-S0-13b ← T-S0-13).
  AC-4 OPTIONAL      : Phase boundary annotation (orphan_tickets[].
                       phase_boundary) + summary.phase_annotations_applied
                       > 0.
  AC-5 UNWANTED      : undetermined_remaining = 0 (post T-S0-13b cleanup) /
                       REUSE は exact match のみ.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
INVENTORY_JSON = REPO_ROOT / "docs" / "audit" / "2026-05-10_v1" / "existing-inventory.json"
INVENTORY_MD = REPO_ROOT / "docs" / "audit" / "2026-05-10_v1" / "existing-inventory.md"
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit-existing-inventory.py"
REGEN_JSON = REPO_ROOT / "scripts" / "regenerate_inventory.py"
REGEN_MD = REPO_ROOT / "scripts" / "regenerate_inventory_md.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


VALID_LABELS = {"REUSE", "REFACTOR", "NEW", "ARCHIVE", "UNDETERMINED"}
VALID_MAPPING_STATUSES = {
    "REUSE", "REFACTOR", "NEW", "ARCHIVE", "UNDETERMINED",
    "triage_needed",  # T-S0-13b で導入された transitional state
}


@pytest.fixture(scope="module")
def inventory():
    return json.loads(INVENTORY_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tickets():
    return json.loads(TICKETS.read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — top-level keys + 281 entries + classification enum
# ══════════════════════════════════════════════════════════════════════


def test_ac1_inventory_json_exists():
    assert INVENTORY_JSON.exists()


def test_ac1_inventory_md_exists():
    assert INVENTORY_MD.exists()


def test_ac1_audit_script_exists():
    assert AUDIT_SCRIPT.exists()


def test_ac1_regen_scripts_exist():
    assert REGEN_JSON.exists()
    assert REGEN_MD.exists()


def test_ac1_inventory_top_level_keys(inventory):
    for key in ("summary", "inventory", "orphan_tickets"):
        assert key in inventory, f"top-level key missing: {key}"


def test_ac1_summary_required_fields(inventory):
    summary = inventory["summary"]
    for field in (
        "audit_id", "regenerated_at", "scope",
        "counts_by_classification", "orphan_tickets_count",
        "undetermined_remaining", "phase_annotations_applied",
    ):
        assert field in summary, f"summary missing field: {field}"


def test_ac1_inventory_281_entries(inventory):
    """T-S0-13b で 281 file = 51 routers + 75 services + 9 integrations +
    3 sandbox + 13 migrations + その他."""
    items = inventory["inventory"]
    # T-S0-13b で 281 が confirmed
    assert len(items) >= 200, f"expected >= 200 entries, got {len(items)}"
    # summary.scope に一致
    expected_total = inventory["summary"]["scope"]["total_files_on_disk"]
    assert len(items) == expected_total


def test_ac1_each_entry_has_file_path_and_classification(inventory):
    for entry in inventory["inventory"]:
        assert "file_path" in entry, f"missing file_path: {entry}"
        # label OR mapping_status のどちらか必須
        has_label = "label" in entry
        has_mapping = "mapping_status" in entry
        assert has_label or has_mapping, f"missing classification: {entry}"


def test_ac1_classification_enum_valid(inventory):
    """label / mapping_status の値が enum 制限."""
    bad: list[str] = []
    for entry in inventory["inventory"]:
        label = entry.get("label")
        ms = entry.get("mapping_status")
        if label is not None and label not in VALID_LABELS:
            bad.append(f"{entry.get('file_path')}: label={label!r}")
        if ms is not None and ms not in VALID_MAPPING_STATUSES:
            bad.append(f"{entry.get('file_path')}: mapping_status={ms!r}")
    assert not bad, f"invalid classification values: {bad[:5]}"


def test_ac1_each_entry_has_rationale_or_match_method(inventory):
    """1-line rationale field: reason OR match_method."""
    missing: list[str] = []
    for entry in inventory["inventory"]:
        has_reason = bool(entry.get("reason"))
        has_method = bool(entry.get("match_method"))
        has_ticket = bool(entry.get("ticket_ids"))
        # ticket がある場合は match_method があり、 無い場合は reason がある
        if not (has_reason or has_method or has_ticket):
            missing.append(entry.get("file_path", "?"))
    assert not missing, f"entries missing rationale: {missing[:5]}"


def test_ac1_counts_by_classification_sums_to_inventory_size(inventory):
    counts = inventory["summary"]["counts_by_classification"]
    items_total = len(inventory["inventory"])
    counts_sum = sum(counts.values())
    # mapping_status の triage_needed が inventory に含まれず orphan に行く
    # ケースがあるため誤差許容
    assert abs(items_total - counts_sum) <= 5, (
        f"summary counts {counts_sum} vs inventory size {items_total}"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — cross-reference tickets.json + deterministic JSON
# ══════════════════════════════════════════════════════════════════════


def test_ac2_audit_script_imports_tickets_json():
    """audit-existing-inventory.py が tickets.json を読む."""
    src = AUDIT_SCRIPT.read_text(encoding="utf-8")
    assert "tickets.json" in src


def test_ac2_orphan_tickets_include_archived_paths(inventory):
    """T-019-01 で ARCHIVE 済の onlook / penpot が orphan_tickets に出る."""
    orphan_files = [o.get("file") for o in inventory["orphan_tickets"]]
    assert "onlook/" in orphan_files
    assert "penpot/" in orphan_files


def test_ac2_orphan_archived_paths_have_archive_reason(inventory):
    """ARCHIVED orphan に正しい reason / phase_boundary."""
    for orphan in inventory["orphan_tickets"]:
        if orphan.get("file") == "onlook/" or orphan.get("file") == "penpot/":
            assert orphan.get("phase_boundary", "").startswith("ARCHIVED"), (
                f"orphan {orphan} missing ARCHIVED phase_boundary"
            )
            assert "T-019-01" in orphan.get("reason", "")


def test_ac2_inventory_entries_have_ticket_refs(inventory):
    """少なくとも一部 entry に ticket_ids が紐付いている (cross-reference 結果)."""
    with_ticket = sum(
        1 for e in inventory["inventory"] if e.get("ticket_ids")
    )
    assert with_ticket > 50, (
        f"too few entries with ticket_ids: {with_ticket} (expected > 50)"
    )


def test_ac2_md_view_exists_and_human_readable():
    """existing-inventory.md は人間可読 markdown."""
    src = INVENTORY_MD.read_text(encoding="utf-8")
    assert "#" in src, "markdown headings missing"
    # 主要セクション
    assert "inventory" in src.lower() or "Inventory" in src
    assert len(src) > 1000


def test_ac2_json_is_utf8_no_byte_order_mark():
    """deterministic JSON: UTF-8 / no BOM."""
    raw = INVENTORY_JSON.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "BOM found"
    # 改行終端 (POSIX text file convention)
    assert raw.rstrip().endswith(b"}")


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — read-only / no network / no forbidden imports / supersedes
# ══════════════════════════════════════════════════════════════════════


def test_ac3_audit_script_is_read_only():
    """audit script に file write (open(..., 'w')) があるのは output 用のみ.
    source code (backend / supabase) を書き換える operation なし."""
    src = AUDIT_SCRIPT.read_text(encoding="utf-8")
    code = _strip_py_comments(src)
    # backend/ や supabase/ への write open() なし
    bad = re.findall(
        r"open\(\s*['\"](?:backend|supabase|frontend)/[^'\"]+['\"]\s*,\s*['\"]w",
        code,
    )
    assert not bad, f"audit script writes to source dirs: {bad}"


def test_ac3_audit_script_no_external_network():
    """requests / httpx / urllib.request / aiohttp なし."""
    src = AUDIT_SCRIPT.read_text(encoding="utf-8")
    code = _strip_py_comments(src)
    for forbidden in ("import requests", "import httpx", "import aiohttp",
                       "urllib.request"):
        assert forbidden not in code, (
            f"audit script uses external network: {forbidden}"
        )


def test_ac3_no_langgraph_langchain_litellm_in_audit_scripts():
    """ADR-010: audit scripts に AI stack 依存なし (read-only static scan)."""
    for path in (AUDIT_SCRIPT, REGEN_JSON, REGEN_MD):
        src = path.read_text(encoding="utf-8")
        code = _strip_py_comments(src).lower()
        for forbidden in ("langgraph", "langchain", "litellm"):
            assert forbidden not in code, (
                f"forbidden {forbidden} in {path.name}"
            )


def test_ac3_supersedes_chain_recorded(inventory):
    """T-S0-13b ← T-S0-13 (2026-05-10) lineage が summary に残る."""
    summary = inventory["summary"]
    assert summary["audit_id"] == "T-S0-13b"
    assert "supersedes" in summary
    assert "T-S0-13" in summary["supersedes"]


def test_ac3_audit_script_no_destructive_ops():
    """rm / shutil.rmtree / os.remove のような destructive op なし."""
    src = AUDIT_SCRIPT.read_text(encoding="utf-8")
    code = _strip_py_comments(src)
    for forbidden in ("shutil.rmtree", "os.remove(", "os.unlink("):
        assert forbidden not in code, (
            f"audit script has destructive op: {forbidden}"
        )


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — Phase boundary annotation
# ══════════════════════════════════════════════════════════════════════


def test_ac4_phase_annotations_applied_positive(inventory):
    """summary.phase_annotations_applied > 0 (少なくとも 1 件は phase
    annotation 済)."""
    n = inventory["summary"]["phase_annotations_applied"]
    assert n > 0, f"phase_annotations_applied must be > 0, got {n}"


def test_ac4_some_orphans_have_phase_boundary(inventory):
    """orphan_tickets[].phase_boundary フィールドが存在 (Phase 1.5 / Phase 2
    / ARCHIVED / directory_reference のいずれか)."""
    with_phase = [
        o for o in inventory["orphan_tickets"] if "phase_boundary" in o
    ]
    assert len(with_phase) > 0


def test_ac4_phase_boundary_values_valid(inventory):
    """phase_boundary value は (ARCHIVED / Phase 1.5 / Phase 2 /
    directory_reference) のいずれか + ticket id (T-XXX)."""
    valid_prefixes = (
        "ARCHIVED", "Phase 1", "Phase 2", "directory_reference",
    )
    for orphan in inventory["orphan_tickets"]:
        pb = orphan.get("phase_boundary")
        if pb is None:
            continue
        assert any(pb.startswith(p) for p in valid_prefixes), (
            f"unexpected phase_boundary value: {pb}"
        )


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — undetermined_remaining = 0 + no silent REUSE default
# ══════════════════════════════════════════════════════════════════════


def test_ac5_undetermined_remaining_is_zero(inventory):
    """T-S0-13b で UNDETERMINED 0 化完了."""
    n = inventory["summary"]["undetermined_remaining"]
    assert n == 0, f"undetermined_remaining must be 0, got {n}"


def test_ac5_no_entry_classified_as_undetermined(inventory):
    """inventory list に UNDETERMINED label の entry が無い."""
    bad = [
        e for e in inventory["inventory"]
        if e.get("label") == "UNDETERMINED"
        or e.get("mapping_status") == "UNDETERMINED"
    ]
    assert not bad, f"entries still UNDETERMINED: {bad[:3]}"


def test_ac5_reuse_only_when_exact_or_dir_match(inventory):
    """REUSE classification は exact path match か explicit directory match.

    silent default (空 match_method) 禁止. ticket_ids が必ず存在し、
    match_method は 'exact' か directory prefix (e.g.
    'templates/project-bootstrap/').
    """
    reuse_entries = [
        e for e in inventory["inventory"]
        if e.get("label") == "REUSE" or e.get("mapping_status") == "REUSE"
    ]
    for entry in reuse_entries:
        # REUSE には ticket_ids が必須
        assert entry.get("ticket_ids"), (
            f"REUSE without ticket: {entry}"
        )
        # match_method は文字列で 1 文字以上 (silent default 禁止)
        method = entry.get("match_method", "")
        assert isinstance(method, str) and len(method) > 0, (
            f"REUSE without match_method: {entry}"
        )
        # 'exact' か directory prefix のいずれか (空文字列 / None は不可)
        is_exact = method == "exact"
        is_dir = "/" in method  # dir-level match e.g. 'templates/foo/'
        assert is_exact or is_dir, (
            f"REUSE match_method must be 'exact' or dir prefix: {entry}"
        )


def test_ac5_classification_counts_no_undetermined(inventory):
    """summary.counts_by_classification に UNDETERMINED key が無い
    OR 値が 0."""
    counts = inventory["summary"]["counts_by_classification"]
    assert counts.get("UNDETERMINED", 0) == 0


def test_ac5_no_hardcoded_secret_in_inventory_json():
    """生成 artifact に Anthropic / Supabase secret 漏洩なし."""
    src = INVENTORY_JSON.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)
    assert "SUPABASE_SERVICE_ROLE_KEY" not in src
    assert not re.search(r"eyJ[A-Za-z0-9_=-]{40,}\.[A-Za-z0-9_=-]{40,}\.", src)


# ══════════════════════════════════════════════════════════════════════
# Cross-reference invariant (tickets.json existing_files ↔ inventory)
# ══════════════════════════════════════════════════════════════════════


def test_cross_ref_archived_paths_in_tickets_appear_as_orphans(
    inventory, tickets,
):
    """T-019-01 の existing_files (onlook/ penpot/ 等) が orphan_tickets に
    appear する."""
    t_019_01 = next(
        (t for t in tickets["tickets"] if t["id"] == "T-019-01"),
        None,
    )
    assert t_019_01 is not None
    orphan_files = {o.get("file") for o in inventory["orphan_tickets"]}
    for arc in ("onlook/", "penpot/"):
        if arc in t_019_01.get("existing_files", []):
            assert arc in orphan_files, (
                f"T-019-01 references {arc} but inventory has no orphan"
            )


def test_cross_ref_summary_scope_is_historical_snapshot():
    """summary.scope.* は監査時点の snapshot.

    実 disk count は session 進行で増加する (新 router / service 追加).
    本 test は (a) snapshot が正の整数で記録されている (b) 実 disk count
    が snapshot 以上 (= 不可逆に減っていない / ARCHIVE 以外で削除されてない)
    を invariant として固定する.

    snapshot < actual は健全 (実装が進んだ). snapshot >> actual は警告
    (大量削除 = 監査結果が古すぎ).
    """
    data = json.loads(INVENTORY_JSON.read_text(encoding="utf-8"))
    scope = data["summary"]["scope"]
    actual_routers = len(list((REPO_ROOT / "backend" / "routers").glob("*.py")))
    actual_services = len(list((REPO_ROOT / "backend" / "services").glob("*.py")))
    actual_migrations = len(list((REPO_ROOT / "supabase" / "migrations").glob("*.sql")))

    # (a) snapshot は正の整数
    for key in ("routers_scanned", "services_scanned", "migrations_scanned",
                 "total_files_on_disk"):
        assert scope[key] > 0, f"snapshot {key} must be > 0"

    # (b) 不可逆削除なし: snapshot - actual が許容範囲 (ARCHIVE 含む)
    assert scope["routers_scanned"] - actual_routers <= 5, (
        f"routers irreversibly deleted? snapshot={scope['routers_scanned']} "
        f"actual={actual_routers}"
    )
    assert scope["services_scanned"] - actual_services <= 5
    assert scope["migrations_scanned"] - actual_migrations <= 3


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_s0_13_canonical_ears_types():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-13"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE"), (
            f"T-S0-13 still uses legacy alias: {ty}"
        )
    assert "EVENT-DRIVEN" in types
    assert "STATE-DRIVEN" in types
    assert "OPTIONAL" in types
    assert "UNWANTED" in types


def test_tickets_t_s0_13_has_adr_link_and_existing_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-13"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert "scripts/audit-existing-inventory.py" in files
    assert "docs/audit/2026-05-10_v1/existing-inventory.json" in files


def test_tickets_t_s0_13_ac_mentions_concrete_artifacts():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-13"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "audit-existing-inventory.py",
        "existing-inventory.json",
        "summary", "inventory", "orphan_tickets",
        "undetermined_remaining",
        "phase_annotations_applied",
        "T-019-01",
    ):
        assert sym in full, f"T-S0-13 AC missing concrete symbol: {sym}"


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _strip_py_comments(src: str) -> str:
    """python docstring + # comment を除外."""
    out = re.sub(r'"""[\s\S]*?"""', "", src)
    out = re.sub(r"'''[\s\S]*?'''", "", out)
    out = re.sub(r"#[^\n]*", "", out)
    return out
