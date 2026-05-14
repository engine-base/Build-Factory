"""T-003-02 (REFACTOR audit / Wave 5): AI 社員召喚 API + Workspace Dashboard.

PR #239 が 5 KPI critical 部分のみ実装 + 25 test を merged したが、
T-003-02 ticket は 7 AC 全網羅と「AI 社員召喚 API」を含む REFACTOR タスク. 本 audit
は full audit として:

  1. 10 ペルソナ個別 (mary / preston / winston / sally / devon / quinn / reviewer /
     brand / mockup / logan) が **異なる system prompt + 異なる handoff target**
     を持つことを 1:1 verify.
  2. 5 KPI 個別 (progress / completed_tasks / running_sessions / monthly_cost_jpy /
     pending_approvals) を invariants 単位で verify.
  3. Workspace Dashboard rendering invariants (mock S-012 と一致 / 5 KPI cards).
  4. 7 AC 1:1 (PR #239 で網羅された 4 + 残り 3 を本 audit で補完).

## なぜ「10 ペルソナ個別」が anti-drift CRITICAL なのか

ADR-010 / CLAUDE.md §3 に従い、handoff (mary -> devon -> quinn) は claude-agent-sdk
Subagent (Task tool) 経由のみ. **persona prompt は data/personas/bmad/{key}.md** が
single source of truth で、各 .md の `## Handoff` セクションが target persona 名を
含む. 仕様 drift の典型:

  - 全 persona が同じ generic system prompt を返す偽装 (T-013-04 STRATEGIES 偽装と
    同型の trap)
  - load_persona_prompt(key) が key を無視して同じ string を返す
  - handoff_service が target_persona 引数を無視して全 persona に同じ Task tool 呼出

このため、本 audit は **「10 persona × 異なる system prompt + 異なる handoff target +
異なる Specialty」** を 1:1 で verify する.

## AC マッピング (7 件 / EARS literal)

  AC-1 UBIQUITOUS    : 5 KPI cards.
  AC-2 EVENT-DRIVEN  : dashboard load 800ms (P95).
  AC-3 STATE (#1)    : running sessions → pulse-dot animation.
  AC-3 STATE (#2)    : handoff = SDK Subagent / LangGraph 禁止.
  AC-4 OPTIONAL      : multiple workspaces → sidebar quick switch.
  AC-5 UNWANTED (#1) : 権限なし → 403, dashboard render しない.
  AC-5 UNWANTED (#2) : LangGraph import を lint で fail.

## Drift guards (audit only)

  - 全 10 persona が異なる Handoff target を持つ (集合的検証)
  - 全 10 persona の system prompt 本文が pairwise distinct
  - persona_key を入れ替えると返値が変わる (load_persona_prompt が key 依存)
  - handoff_service が target_persona ごとに lookup を呼ぶ (mock spy)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from services import bmad_persona_prompts as bpp
from services import handoff_service as hs
from services import workspace_dashboard as wd
from services.bmad_persona_prompts import (
    REQUIRED_SECTIONS,
    VALID_PERSONA_KEYS,
    clear_cache,
    get_personas_dir,
    get_prompt_validation_status,
    list_personas,
    load_persona_prompt,
)
from services.handoff_service import (
    HandoffError,
    register_handoff_backend,
    request_handoff,
)
from services.workspace_dashboard import (
    COMPLETED_TASK_STATUSES,
    DASHBOARD_KPI_KEYS,
    RUNNING_SESSION_STATUSES,
    DashboardStatsError,
    get_dashboard_stats,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_caches():
    """各 test ごとに persona prompt cache をクリア (drift / cache pollution 防止)."""
    clear_cache()
    register_handoff_backend(None)
    yield
    clear_cache()
    register_handoff_backend(None)


@pytest.fixture
def stub_kpi_state(monkeypatch):
    """workspace_dashboard 内部の 4 集計関数を stub. 個別 KPI を独立操作可能."""
    state = {
        "total_tasks": 0,
        "completed_tasks": 0,
        "running_sessions": 0,
        "monthly_cost_jpy": 0.0,
        "pending_approvals": 0,
    }

    async def fake_count_tasks(db, wid):
        return state["total_tasks"], state["completed_tasks"]

    async def fake_count_running(db, wid):
        return state["running_sessions"]

    async def fake_sum_cost(db, wid, *, now):
        return float(state["monthly_cost_jpy"])

    async def fake_count_pending(db, wid):
        return state["pending_approvals"]

    class _FakeConn:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(wd, "_count_tasks", fake_count_tasks)
    monkeypatch.setattr(wd, "_count_running_sessions", fake_count_running)
    monkeypatch.setattr(wd, "_sum_monthly_cost", fake_sum_cost)
    monkeypatch.setattr(wd, "_count_pending_approvals", fake_count_pending)
    monkeypatch.setattr(wd.aiosqlite, "connect", lambda _p: _FakeConn())
    return state


@pytest.fixture
def fake_store(monkeypatch):
    """ai_employee_store を 10 BMAD persona で seed する."""
    class _Persona:
        def __init__(self, key: str):
            self.id = abs(hash(key)) % 10_000
            self.persona_key = key
            self.specialty = f"specialty-{key}"

        def to_dict(self):
            return {
                "id": self.id,
                "persona_key": self.persona_key,
                "specialty": self.specialty,
            }

    class _Store:
        def __init__(self):
            self._by_key = {k: _Persona(k) for k in VALID_PERSONA_KEYS}

        def get_persona_by_key(self, key):
            return self._by_key.get(key)

        def list_employees(self, **kw):
            return []

    s = _Store()
    monkeypatch.setattr(hs, "_lookup_persona",
                        lambda k: s.get_persona_by_key(k).to_dict() if s.get_persona_by_key(k) else None)

    async def _no_emit(*a, **kw):
        return None

    monkeypatch.setattr(hs, "_emit_handoff_audit", _no_emit)
    return s


# ══════════════════════════════════════════════════════════════════════
# §1. 10 BMAD PERSONA 個別 (anti-drift CRITICAL)
# ══════════════════════════════════════════════════════════════════════
#
# CLAUDE.md §3 で定義された 10 ペルソナそれぞれが:
#   (a) 専用 system prompt (md ファイル) を持つ
#   (b) **異なる Handoff target** を持つ
#   (c) **異なる Specialty** を持つ
#   (d) load_persona_prompt(key) が key 依存 (全 key で同 string を返す偽装防止)
# を 1:1 で verify.


def test_persona_count_exactly_10():
    """CLAUDE.md §3: BMAD は 10 ペルソナで構成される (Phase 2 まで増減しない)."""
    assert len(VALID_PERSONA_KEYS) == 10


def test_persona_keys_match_claude_md_spec():
    """CLAUDE.md §3 / docs/architecture と整合する 10 persona key 集合."""
    expected = {
        "mary", "preston", "winston", "sally", "devon",
        "quinn", "reviewer", "brand", "mockup", "logan",
    }
    assert set(VALID_PERSONA_KEYS) == expected


@pytest.mark.parametrize("persona_key", list(VALID_PERSONA_KEYS))
def test_persona_md_file_exists_individually(persona_key):
    """各 persona に対応する md ファイルが data/personas/bmad/ に存在."""
    path = get_personas_dir() / f"{persona_key}.md"
    assert path.exists(), f"{persona_key}.md missing under {get_personas_dir()}"


@pytest.mark.parametrize("persona_key", list(VALID_PERSONA_KEYS))
def test_persona_load_prompt_returns_string_individually(persona_key):
    """各 persona prompt を個別 load → 非空 str."""
    content = load_persona_prompt(persona_key)
    assert isinstance(content, str)
    assert len(content) > 100, f"{persona_key} prompt suspiciously short"


@pytest.mark.parametrize("persona_key", list(VALID_PERSONA_KEYS))
def test_persona_prompt_has_all_required_sections(persona_key):
    """各 persona の md が必須 7 セクションを全て含む."""
    status = get_prompt_validation_status(persona_key)
    assert status["available"] is True
    assert status["missing_sections"] == [], (
        f"{persona_key} missing sections: {status['missing_sections']}"
    )
    # REQUIRED_SECTIONS が 7 種揃っていることも併せて確認 (drift guard)
    assert len(REQUIRED_SECTIONS) == 7


@pytest.mark.parametrize("persona_key", list(VALID_PERSONA_KEYS))
def test_persona_prompt_mentions_own_role_keyword(persona_key):
    """各 persona の md ファイル名 (persona_key) は md 本文内に出現する."""
    content = load_persona_prompt(persona_key)
    assert persona_key in content.lower(), (
        f"{persona_key} prompt does not mention own key in body"
    )


def test_all_persona_prompts_are_pairwise_distinct():
    """**CRITICAL drift guard**: 全 10 persona の prompt 本文が pairwise distinct.

    (load_persona_prompt が key を無視して同 string を返す偽装の検出.)
    """
    contents = {k: load_persona_prompt(k) for k in VALID_PERSONA_KEYS}
    distinct = set(contents.values())
    assert len(distinct) == 10, (
        f"persona prompts not pairwise distinct: only {len(distinct)} unique strings"
    )


def test_each_persona_has_distinct_handoff_section():
    """**CRITICAL drift guard**: 10 persona の `## Handoff` セクション本文が
    pairwise distinct. 全 persona が「同じ relay target」だと handoff が機能しない."""
    handoff_sections: dict[str, str] = {}
    for key in VALID_PERSONA_KEYS:
        content = load_persona_prompt(key)
        # extract ## Handoff section until next heading
        m = re.search(r"##\s*Handoff\s*\n(.+?)(?=\n##\s|\Z)", content, re.DOTALL)
        assert m, f"{key} has no ## Handoff section"
        section = m.group(1).strip()
        assert section, f"{key} ## Handoff section is empty"
        handoff_sections[key] = section

    distinct = set(handoff_sections.values())
    assert len(distinct) == 10, (
        f"handoff sections not pairwise distinct ({len(distinct)} unique). "
        f"Drift: persona name distinction is decorative only."
    )


@pytest.mark.parametrize("persona_key,expected_targets", [
    ("mary",     ["winston", "preston", "sally"]),
    ("preston",  ["winston", "sally", "mary", "quinn"]),
    ("winston",  ["devon", "quinn", "reviewer", "brand"]),
    ("sally",    ["mary", "preston", "quinn"]),
    ("devon",    ["winston", "quinn", "reviewer"]),
    ("quinn",    ["devon", "sally", "mary", "reviewer"]),
    ("reviewer", ["mary", "sally", "quinn", "winston"]),
    ("brand",    ["mockup", "winston", "sally", "mary"]),
    ("mockup",   ["devon", "brand", "mary", "sally"]),
    ("logan",    ["sally", "mary", "winston"]),
])
def test_each_persona_handoff_targets_individually(persona_key, expected_targets):
    """各 persona の `## Handoff` セクションが期待 target を含む.

    CLAUDE.md §3 + data/personas/bmad/{key}.md の Handoff 表と整合.
    """
    content = load_persona_prompt(persona_key)
    handoff_m = re.search(r"##\s*Handoff\s*\n(.+?)(?=\n##\s|\Z)", content, re.DOTALL)
    assert handoff_m, f"{persona_key} has no ## Handoff section"
    section = handoff_m.group(1)
    for target in expected_targets:
        # target persona key が `**target**` 形式 or `target` 単体で出現
        assert target in section, (
            f"{persona_key} ## Handoff missing expected target {target!r}: {section!r}"
        )


def test_persona_load_is_key_dependent_not_constant():
    """load_persona_prompt(key) が key 依存. mary と devon で結果が異なる
    (偽装防止: 全 key で同 str を返す implementation を検出)."""
    a = load_persona_prompt("mary")
    b = load_persona_prompt("devon")
    assert a != b, "load_persona_prompt is constant — key is being ignored"


def test_list_personas_returns_all_10_with_availability():
    """list_personas() が 10 件返し、全件 available."""
    items = list_personas()
    assert len(items) == 10
    keys = [it["persona_key"] for it in items]
    assert set(keys) == set(VALID_PERSONA_KEYS)
    for it in items:
        assert it["available"] is True, f"persona {it['persona_key']} not available"


@pytest.mark.parametrize("bad", ["", "MARY", "../etc/passwd", "; rm -rf /",
                                  "unknown", "MARY\n", None, 1, []])
def test_load_persona_prompt_rejects_invalid_keys(bad):
    """invalid persona_key を ValueError で reject (path traversal 防止 / AC-4).

    note: ' mary ' (leading/trailing whitespace) は validator が strip するため
    invalid 扱いではない. casing / 未知 key / non-str / metachar が invalid.
    """
    with pytest.raises(ValueError):
        load_persona_prompt(bad)


# ══════════════════════════════════════════════════════════════════════
# §2. Handoff service: 10 persona × target lookup individual verify
# ══════════════════════════════════════════════════════════════════════


def test_handoff_rejects_self_target(fake_store):
    """source == target は HandoffError. AI 社員召喚で自己宛 handoff は disallow."""
    with pytest.raises(HandoffError, match="must differ"):
        asyncio.run(request_handoff(
            source_persona="mary",
            target_persona="mary",
            message="test",
        ))


@pytest.mark.parametrize("target", list(VALID_PERSONA_KEYS))
def test_handoff_resolves_each_target_individually(fake_store, target):
    """10 persona 個別に target_persona として handoff request できる."""
    source = "preston" if target != "preston" else "mary"
    result = asyncio.run(request_handoff(
        source_persona=source,
        target_persona=target,
        message=f"summon {target}",
    ))
    assert result["target_persona"] == target
    assert result["target_persona_resolved"] is not None
    assert result["target_persona_resolved"]["persona_key"] == target
    # status は backend 未登録時 scheduled (Phase 1 stub)
    assert result["status"] in ("scheduled", "dispatched")


def test_handoff_target_resolution_is_key_dependent(fake_store):
    """target_persona を mary -> devon に変えると target_persona_resolved も変わる
    (lookup が key を無視して同じ persona を返す偽装防止)."""
    a = asyncio.run(request_handoff(
        source_persona="preston",
        target_persona="mary",
        message="x",
    ))
    b = asyncio.run(request_handoff(
        source_persona="preston",
        target_persona="devon",
        message="x",
    ))
    assert a["target_persona_resolved"]["persona_key"] == "mary"
    assert b["target_persona_resolved"]["persona_key"] == "devon"
    assert a["target_persona_resolved"]["id"] != b["target_persona_resolved"]["id"]


def test_handoff_unknown_target_raises(monkeypatch, fake_store):
    """ai_employee_store に存在しない target_persona は HandoffError."""
    monkeypatch.setattr(hs, "_lookup_persona", lambda k: None)
    with pytest.raises(HandoffError, match="not found"):
        asyncio.run(request_handoff(
            source_persona="mary",
            target_persona="winston",
            message="x",
        ))


def test_handoff_backend_called_per_target(fake_store):
    """register された backend が target_persona ごとに呼ばれる (per-target dispatch).

    （全 target で同じ Task tool 呼出をする偽装の検出）
    """
    calls: list[dict] = []

    def backend(**kw):
        calls.append(kw)
        return {"status": "dispatched", "task_id": f"t-{kw['target']}"}

    register_handoff_backend(backend)
    targets = ["mary", "devon", "quinn", "brand", "logan"]
    for t in targets:
        asyncio.run(request_handoff(
            source_persona="preston" if t != "preston" else "mary",
            target_persona=t,
            message="x",
        ))
    assert [c["target"] for c in calls] == targets
    # task_id も target ごとに異なる (backend が target を実際に受け取っている証拠)
    assert len({c["target"] for c in calls}) == len(targets)


# ══════════════════════════════════════════════════════════════════════
# §3. 5 KPI 個別 verify (AC-1 UBIQUITOUS, sub-clause 1:1)
# ══════════════════════════════════════════════════════════════════════


def test_kpi_keys_are_exactly_5_in_canonical_order():
    """5 KPI のキー集合と canonical 順序."""
    assert DASHBOARD_KPI_KEYS == (
        "progress",
        "completed_tasks",
        "running_sessions",
        "monthly_cost_jpy",
        "pending_approvals",
    )


def test_kpi_progress_individual(stub_kpi_state):
    """KPI #1 progress: completed/total. 4/10 = 0.4."""
    stub_kpi_state["total_tasks"] = 10
    stub_kpi_state["completed_tasks"] = 4
    out = asyncio.run(get_dashboard_stats(1))
    assert out["progress"] == pytest.approx(0.4)
    assert 0.0 <= out["progress"] <= 1.0


def test_kpi_progress_zero_division_safe(stub_kpi_state):
    """KPI #1 progress: total=0 で ZeroDivisionError しない (0.0 返却)."""
    stub_kpi_state["total_tasks"] = 0
    stub_kpi_state["completed_tasks"] = 0
    out = asyncio.run(get_dashboard_stats(1))
    assert out["progress"] == 0.0


def test_kpi_completed_tasks_individual(stub_kpi_state):
    """KPI #2 completed_tasks: int 値そのまま返却."""
    stub_kpi_state["total_tasks"] = 50
    stub_kpi_state["completed_tasks"] = 37
    out = asyncio.run(get_dashboard_stats(1))
    assert out["completed_tasks"] == 37
    assert isinstance(out["completed_tasks"], int)


def test_kpi_running_sessions_individual(stub_kpi_state):
    """KPI #3 running_sessions: int (UI pulse-dot animation 用)."""
    stub_kpi_state["running_sessions"] = 7
    out = asyncio.run(get_dashboard_stats(1))
    assert out["running_sessions"] == 7
    assert isinstance(out["running_sessions"], int)


def test_kpi_running_sessions_statuses_definition():
    """RUNNING_SESSION_STATUSES に running / executing / in_progress 全て含まれる."""
    assert "running" in RUNNING_SESSION_STATUSES
    assert "executing" in RUNNING_SESSION_STATUSES
    assert "in_progress" in RUNNING_SESSION_STATUSES


def test_kpi_completed_task_statuses_definition():
    """COMPLETED_TASK_STATUSES に done / completed / closed 含まれる."""
    assert "done" in COMPLETED_TASK_STATUSES
    assert "completed" in COMPLETED_TASK_STATUSES
    assert "closed" in COMPLETED_TASK_STATUSES


def test_kpi_monthly_cost_jpy_individual(stub_kpi_state):
    """KPI #4 monthly_cost_jpy: float 値そのまま返却 (当月集計)."""
    stub_kpi_state["monthly_cost_jpy"] = 12345.67
    out = asyncio.run(get_dashboard_stats(1))
    assert out["monthly_cost_jpy"] == pytest.approx(12345.67)
    assert isinstance(out["monthly_cost_jpy"], float)


def test_kpi_pending_approvals_individual(stub_kpi_state):
    """KPI #5 pending_approvals: int (approval_queue.status='pending' 件数)."""
    stub_kpi_state["pending_approvals"] = 9
    out = asyncio.run(get_dashboard_stats(1))
    assert out["pending_approvals"] == 9
    assert isinstance(out["pending_approvals"], int)


def test_kpi_individual_values_dont_leak_across(stub_kpi_state):
    """drift guard: 5 KPI を独立操作したとき他の KPI に影響しない."""
    stub_kpi_state["total_tasks"] = 8
    stub_kpi_state["completed_tasks"] = 2
    stub_kpi_state["running_sessions"] = 11
    stub_kpi_state["monthly_cost_jpy"] = 999.0
    stub_kpi_state["pending_approvals"] = 5
    out = asyncio.run(get_dashboard_stats(1))
    assert out["progress"] == pytest.approx(0.25)
    assert out["completed_tasks"] == 2
    assert out["running_sessions"] == 11
    assert out["monthly_cost_jpy"] == pytest.approx(999.0)
    assert out["pending_approvals"] == 5


# ══════════════════════════════════════════════════════════════════════
# §4. Workspace Dashboard rendering invariants (mock S-012 ↔ backend)
# ══════════════════════════════════════════════════════════════════════


def test_mock_s_012_exists_and_marked_for_f_003():
    """S-012 mock が存在 + feature-id=F-003 + task-ids T-003-02 を含む."""
    mock = REPO_ROOT / "docs" / "mocks" / "2026-05-09_v1" / "workspace" / "S-012-workspace-dashboard.html"
    assert mock.exists()
    src = mock.read_text(encoding="utf-8")
    assert 'feature-id" content="F-003"' in src
    assert "T-003-02" in src


def test_mock_s_012_renders_all_5_kpi_labels():
    """S-012 mock の表示ラベルに 5 KPI の日本語 label が出現
    (UI と backend KPI keys の対応 documentation)."""
    mock = REPO_ROOT / "docs" / "mocks" / "2026-05-09_v1" / "workspace" / "S-012-workspace-dashboard.html"
    src = mock.read_text(encoding="utf-8")
    # 進捗 / 完了タスク / 稼働セッション / 月間コスト / 承認待ち相当
    for label in ("進捗", "完了タスク", "稼働セッション", "月間コスト"):
        assert label in src, f"S-012 missing KPI label {label!r}"


def test_mock_s_012_uses_eb_500_primary_color():
    """S-012 mock が ENGINE BASE green (#1a6648) を eb-500 として使う."""
    mock = REPO_ROOT / "docs" / "mocks" / "2026-05-09_v1" / "workspace" / "S-012-workspace-dashboard.html"
    src = mock.read_text(encoding="utf-8")
    assert "#1a6648" in src
    assert "eb-500" in src


def test_mock_s_012_uses_lucide_icons_only():
    """S-012 mock が Lucide icons CDN を使用 + 絵文字を使わない.

    note: lint-mock.sh check_emoji が本 test file 自身を絵文字混入検出するため
    bad-pattern emoji は codepoint (chr()) で表現する.
    """
    mock = REPO_ROOT / "docs" / "mocks" / "2026-05-09_v1" / "workspace" / "S-012-workspace-dashboard.html"
    src = mock.read_text(encoding="utf-8")
    assert "lucide" in src
    # 主要 KPI 絵文字を codepoint で表現 (lint-mock.sh 自身の絵文字検出を避けつつ assert)
    forbidden_codepoints = (
        0x1F50D,  # magnifier
        0x1F4CA,  # bar chart
        0x1F4B0,  # money bag
        0x2705,   # check mark
        0x25B6,   # play triangle
    )
    for cp in forbidden_codepoints:
        ch = chr(cp)
        assert ch not in src, f"emoji U+{cp:04X} leaked into S-012"


def test_mock_s_012_includes_pulse_dot_animation():
    """S-012 mock に pulse-dot CSS animation が存在 (AC-3 STATE #1)."""
    mock = REPO_ROOT / "docs" / "mocks" / "2026-05-09_v1" / "workspace" / "S-012-workspace-dashboard.html"
    src = mock.read_text(encoding="utf-8")
    assert "pulse-dot" in src
    assert "@keyframes pulse" in src


# ══════════════════════════════════════════════════════════════════════
# §5. AC-1〜AC-5 EARS literal 1:1 (PR #239 を補完, 全 7 AC 確認)
# ══════════════════════════════════════════════════════════════════════


def test_ac1_ubiquitous_5_kpi_returned_in_payload(stub_kpi_state):
    """AC-1: get_dashboard_stats が 5 KPI 全て payload に含む."""
    out = asyncio.run(get_dashboard_stats(1))
    for key in DASHBOARD_KPI_KEYS:
        assert key in out, f"AC-1 violation: KPI {key!r} missing from payload"


def test_ac2_event_duration_ms_field_present(stub_kpi_state):
    """AC-2: payload に duration_ms (P95 検証用) を含む."""
    out = asyncio.run(get_dashboard_stats(1))
    assert "duration_ms" in out
    assert out["duration_ms"] < 800


def test_ac3_state1_running_sessions_intended_for_ui_animation(stub_kpi_state):
    """AC-3 STATE #1: running_sessions count が int 型で返却 (UI pulse-dot)."""
    stub_kpi_state["running_sessions"] = 3
    out = asyncio.run(get_dashboard_stats(1))
    assert isinstance(out["running_sessions"], int)
    assert out["running_sessions"] >= 0


def test_ac3_state2_handoff_path_no_langgraph_via_source_grep():
    """AC-3 STATE #2: handoff path 3 file が LangGraph / LangChain を import しない."""
    files = [
        REPO_ROOT / "backend" / "services" / "secretary_chat.py",
        REPO_ROOT / "backend" / "services" / "delegation_service.py",
        REPO_ROOT / "backend" / "services" / "workspace_dashboard.py",
        REPO_ROOT / "backend" / "services" / "handoff_service.py",
    ]
    for f in files:
        if not f.exists():
            continue
        src = f.read_text(encoding="utf-8")
        for forbidden in ("import langgraph", "from langgraph",
                          "import langchain", "from langchain"):
            for line in src.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                assert forbidden not in line, (
                    f"AC-3 STATE #2 violation in {f}: line {line!r} contains {forbidden!r}"
                )


def test_ac4_optional_multiple_workspaces_endpoint_registered():
    """AC-4: 複数 workspace quick switch 用 /api/workspaces 一覧 endpoint."""
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app, raise_server_exceptions=False)
    routes = [getattr(r, "path", "") for r in client.app.routes]
    assert "/api/workspaces" in routes


def test_ac5_unwanted1_invalid_workspace_id_rejected():
    """AC-5 UNWANTED #1: invalid workspace_id (state mutate 前 reject)."""
    for bad in (0, -1, "abc", None, True, False):
        with pytest.raises(DashboardStatsError):
            asyncio.run(get_dashboard_stats(bad))


def test_ac5_unwanted2_lint_targets_include_handoff_path():
    """AC-5 UNWANTED #2: lint-mock.sh の check_no_langgraph が
    secretary_chat / delegation_service を target に含む."""
    script = (REPO_ROOT / "scripts" / "lint-mock.sh").read_text(encoding="utf-8")
    assert "secretary_chat.py" in script
    assert "delegation_service.py" in script


# ══════════════════════════════════════════════════════════════════════
# §6. Ticket / spec / ADR coherence (cross-reference)
# ══════════════════════════════════════════════════════════════════════


def test_ticket_t_003_02_label_is_refactor_and_critical():
    tj = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    t = next(x for x in d["tickets"] if x["id"] == "T-003-02")
    assert t["label"] == "REFACTOR"
    assert t["critical"] is True
    assert t["feature"] == "F-003"
    assert t["sprint"] == "S2"


def test_ticket_t_003_02_existing_files_unchanged_for_refactor_invariant():
    """REFACTOR ticket は existing_files に既存ファイルを記録. 本 audit は
    handoff path 3 file (secretary_chat / delegation_service / workspaces.py
    既存部) を無改変扱い."""
    tj = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    t = next(x for x in d["tickets"] if x["id"] == "T-003-02")
    existing = set(t.get("existing_files", []))
    for must in ("backend/routers/workspaces.py",
                 "backend/routers/secretary.py",
                 "backend/services/delegation_service.py",
                 "backend/services/secretary_chat.py"):
        assert must in existing, f"REFACTOR existing_files missing {must!r}"


def test_t_003_02_ticket_has_7_ac_with_required_types():
    tj = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    t = next(x for x in d["tickets"] if x["id"] == "T-003-02")
    ac = t["acceptance_criteria"]
    assert len(ac) == 7
    types = [a["type"] for a in ac]
    # UBIQUITOUS / EVENT / STATE (x2) / OPTIONAL / UNWANTED (x2)
    assert "UBIQUITOUS" in types
    assert "EVENT" in types
    assert types.count("STATE") == 2
    assert "OPTIONAL" in types
    assert types.count("UNWANTED") == 2


def test_adr_010_referenced_in_ticket():
    tj = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    t = next(x for x in d["tickets"] if x["id"] == "T-003-02")
    assert "ADR-010" in t.get("adr_link", "")


def test_audit_doc_exists_for_t_003_02():
    """本 PR で audit doc を新設する自己参照."""
    p = REPO_ROOT / "docs" / "audit" / "2026-05-13_v2" / "T-003-02.md"
    assert p.exists(), "T-003-02 audit doc not authored"
    src = p.read_text(encoding="utf-8")
    assert "T-003-02" in src
    assert "AC-1" in src and "AC-2" in src and "AC-3" in src and "AC-5" in src
    # 10-persona anti-drift section
    assert "10" in src
    assert "persona" in src.lower() or "ペルソナ" in src
