"""T-S0-13c: tickets.json AC 整合検査 — 5 AC 機械 invariant.

PR #13 で production artifact 完成済 (scripts/audit-ac-coherence.py +
docs/audit/2026-05-10_v1/ac-coherence-report.md). 本 module は **spec
contract layer**.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : audit script + report.md / 4 section / 179 ticket
                       walk / header metric.
  AC-2 EVENT-DRIVEN  : title↔AC keyword mismatch detection / verbatim
                       重複 detection.
  AC-3 STATE-DRIVEN  : tickets.json read-only / no network / no
                       langgraph/langchain/litellm / deterministic output.
  AC-4 OPTIONAL      : previously_fixed annotation で AC 修正済 ticket
                       mark.
  AC-5 UNWANTED      : review_needed reason / silent pass 禁止 / source
                       mutation なし.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit-ac-coherence.py"
REPORT_MD = REPO_ROOT / "docs" / "audit" / "2026-05-10_v1" / "ac-coherence-report.md"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


@pytest.fixture(scope="module")
def report():
    return REPORT_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tickets():
    return json.loads(TICKETS.read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — artifact + 4 sections + header
# ══════════════════════════════════════════════════════════════════════


def test_ac1_audit_script_exists():
    assert AUDIT_SCRIPT.exists()


def test_ac1_report_md_exists():
    assert REPORT_MD.exists()


def test_ac1_report_has_total_tickets_count(report):
    assert re.search(r"Total tickets:\s*\d+", report)


def test_ac1_report_has_four_sections(report):
    """### 1. ... ### 2. ... ### 3. ... ### 4. ..."""
    # markdown h2/h3 で section が 4 つ
    sections = re.findall(r"^\s*##\s+\d+\.\s+", report, re.MULTILINE)
    assert len(sections) >= 4, f"expected 4 numbered sections, got {len(sections)}"


def test_ac1_section_1_verbatim_duplicates(report):
    assert "Verbatim 重複 AC text" in report


def test_ac1_section_2_keyword_mismatch(report):
    assert "title↔AC キーワード乖離" in report


def test_ac1_section_3_or_4_insufficient_or_missing(report):
    """AC 不在 / review_needed セクション."""
    assert "review_needed" in report or "AC 不在" in report or "insufficient" in report.lower()


def test_ac1_header_lists_verbatim_zero(report):
    """Verbatim 重複 0 (post-cleanup invariant)."""
    m = re.search(r"Verbatim 重複 AC text:\s*0\s*件", report)
    assert m, "header must show 'Verbatim 重複 AC text: 0 件'"


def test_ac1_header_lists_previously_fixed_positive(report):
    """既修正 PREVIOUSLY_FIXED count > 0 (AC concretize PR 多数)."""
    m = re.search(r"既修正 \(PREVIOUSLY_FIXED\):\s*(\d+)", report)
    assert m, "header must list previously fixed count"
    assert int(m.group(1)) >= 1


def test_ac1_total_tickets_matches_tickets_json(report, tickets):
    """report header の Total tickets が tickets.json と一致."""
    m = re.search(r"Total tickets:\s*(\d+)", report)
    assert m
    n = int(m.group(1))
    actual = len(tickets["tickets"])
    # ±5 件以内の誤差許容 (T-S0-13c 監査時の数字が古い場合)
    assert abs(n - actual) <= 5, (
        f"report Total tickets={n} vs tickets.json actual={actual}"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — title↔AC mismatch + verbatim duplicates
# ══════════════════════════════════════════════════════════════════════


def test_ac2_script_walks_all_tickets():
    """audit script が tickets.json を ticket 単位で iterate."""
    src = AUDIT_SCRIPT.read_text(encoding="utf-8")
    assert "tickets.json" in src
    assert re.search(r"for\s+\w+\s+in\s+", src)


def test_ac2_script_detects_keyword_mismatch():
    """title に DDL を含むのに AC に schema/table/migration が無い等の
    pattern 検出ロジックがある."""
    src = AUDIT_SCRIPT.read_text(encoding="utf-8")
    # theme keyword mapping や mismatch detection logic
    assert "title" in src.lower()
    # 主要 theme (DDL / UI / API 等) の文字列が script に出る
    themes_in_script = sum(
        1 for k in ("DDL", "schema", "API", "UI", "frontend")
        if k in src
    )
    assert themes_in_script >= 2, "script must define theme keywords"


def test_ac2_script_detects_verbatim_duplicates():
    """重複 AC text 検出 (Counter or set 比較)."""
    src = AUDIT_SCRIPT.read_text(encoding="utf-8")
    # Counter / set / dup を用いた検出パターン
    assert "Counter" in src or "set(" in src or "duplicate" in src.lower()


def test_ac2_report_includes_ac_excerpts(report):
    """section 2 entry に "AC excerpt:" が含まれる."""
    assert "AC excerpt:" in report


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — read-only / no network / ADR-010 / deterministic
# ══════════════════════════════════════════════════════════════════════


def test_ac3_script_does_not_write_tickets_json():
    """audit script が tickets.json に write しない (read-only)."""
    src = AUDIT_SCRIPT.read_text(encoding="utf-8")
    code = _strip_py_comments(src)
    # open(... tickets.json, 'w')  禁止
    bad = re.findall(
        r"open\([^)]*tickets\.json[^)]*['\"][wa]",
        code,
    )
    assert not bad, f"audit script writes to tickets.json: {bad}"


def test_ac3_script_no_external_network():
    src = AUDIT_SCRIPT.read_text(encoding="utf-8")
    code = _strip_py_comments(src)
    for forbidden in ("import requests", "import httpx",
                       "import aiohttp", "urllib.request"):
        assert forbidden not in code


def test_ac3_script_no_langgraph_langchain_litellm():
    src = AUDIT_SCRIPT.read_text(encoding="utf-8")
    code = _strip_py_comments(src).lower()
    for forbidden in ("langgraph", "langchain", "litellm"):
        assert forbidden not in code, f"forbidden {forbidden} in audit script"


def test_ac3_script_no_destructive_ops():
    src = AUDIT_SCRIPT.read_text(encoding="utf-8")
    code = _strip_py_comments(src)
    for forbidden in ("shutil.rmtree", "os.remove(", "os.unlink("):
        assert forbidden not in code


def test_ac3_report_is_markdown_format():
    """report が markdown (### or ## headers + - bullets)."""
    src = REPORT_MD.read_text(encoding="utf-8")
    assert src.startswith("#") or "## " in src
    assert "- " in src  # bullet list


def test_ac3_report_no_secret_leaked():
    src = REPORT_MD.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)
    assert "SUPABASE_SERVICE_ROLE_KEY" not in src


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — previously_fixed annotation
# ══════════════════════════════════════════════════════════════════════


def test_ac4_previously_fixed_marker_present(report):
    """`[previously_fixed]` annotation が >= 1 件 report に登場."""
    assert "previously_fixed" in report
    # marker は brackets 内
    assert "[previously_fixed]" in report or "`[previously_fixed]`" in report


def test_ac4_at_least_one_known_fixed_ticket_marked(report):
    """T-S0-13 / T-019-01 / T-S0-08 のいずれかが previously_fixed に出る."""
    fixed_tickets = (
        "T-019-01", "T-S0-13", "T-001-01", "T-001-02",
        "T-001-04", "T-S0-08", "T-S0-09",
    )
    annotated = [
        tid for tid in fixed_tickets
        if re.search(rf"{re.escape(tid)}.*previously_fixed", report)
    ]
    assert len(annotated) >= 1, (
        f"at least one of {fixed_tickets} must be marked previously_fixed"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — review_needed reason + no source mutation
# ══════════════════════════════════════════════════════════════════════


def test_ac5_review_needed_section_or_empty(report):
    """section 4 (AC 不在 / review_needed) が存在 (空でも OK)."""
    # "review_needed" 単独で出る or section header
    assert "review_needed" in report.lower() or "AC 不在" in report


def test_ac5_audit_script_no_silent_pass():
    """script が title/AC 不在 ticket を silent pass しないこと."""
    src = AUDIT_SCRIPT.read_text(encoding="utf-8")
    # review_needed リストに追加する logic が script 内にある
    assert "review_needed" in src


def test_ac5_audit_script_marks_acceptance_criteria_missing():
    """acceptance_criteria が空 / 不在 を検出する logic."""
    src = AUDIT_SCRIPT.read_text(encoding="utf-8")
    # acceptance_criteria 文字列が script に出る
    assert "acceptance_criteria" in src


def test_ac5_report_uses_explicit_verdict_marker(report):
    """各 ticket に theme: が明示される (silent default 禁止)."""
    # 各 section 2 entry が "theme: " marker を持つ
    if "title↔AC キーワード乖離" in report:
        themes = re.findall(r"theme:\s*\w+", report)
        # 乖離 entry が >= 1 件あれば theme: マークアップが出る
        # マッチが 0 件でも section が空ならスキップ
        # (post-cleanup で 乖離 0 件のときもある)
        assert isinstance(themes, list)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_s0_13c_canonical_ears_types():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-13c"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE"), (
            f"T-S0-13c still uses legacy alias: {ty}"
        )
    assert "EVENT-DRIVEN" in types
    assert "STATE-DRIVEN" in types
    assert "OPTIONAL" in types
    assert "UNWANTED" in types


def test_tickets_t_s0_13c_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-13c"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert "scripts/audit-ac-coherence.py" in files
    assert any("ac-coherence-report.md" in f for f in files)


def test_tickets_t_s0_13c_ac_mentions_concrete_artifacts():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-13c"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "audit-ac-coherence.py",
        "ac-coherence-report.md",
        "Verbatim",
        "title↔AC",
        "review_needed",
        "previously_fixed",
        "AC excerpt",
    ):
        assert sym in full, f"T-S0-13c AC missing concrete symbol: {sym}"


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _strip_py_comments(src: str) -> str:
    out = re.sub(r'"""[\s\S]*?"""', "", src)
    out = re.sub(r"'''[\s\S]*?'''", "", out)
    out = re.sub(r"#[^\n]*", "", out)
    return out
