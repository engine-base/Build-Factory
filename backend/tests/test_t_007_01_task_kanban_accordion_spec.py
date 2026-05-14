"""T-007-01 SPEC AUDIT (v2 / pre-flight 1:1 AC coverage).

This complements the baseline `test_t_007_01_task_kanban_accordion.py` (20 tests)
with **literal Spec expansion** + **anti-drift guards** required by the v2 audit
protocol (see `docs/audit/2026-05-13_v2/T-013-04.md`).

The TaskKanbanAccordion.tsx implementation is a REFACTOR target: it must
materialise CLAUDE.md §5.5 (機能別アコーディオン / 4 列 Todo・In Progress・
Review・Done / 進行中のみ default 展開) while leaving the existing flat
6-column `TaskKanban.tsx` untouched (REUSE invariant).

Static structural checks only (Python string / regex / AST over the .tsx
source). No Node runtime is required.

AC mapping (1:1, REFACTOR-invariant):

  AC-1 UBIQUITOUS
       TaskKanbanAccordion.tsx is published with the public surface
       required by CLAUDE.md §5.5 (機能別アコーディオン + 各機能内 4 列).
       Existing TaskKanban.tsx MUST NOT be modified by this task.

  AC-2 EVENT-DRIVEN
       props change → React.useMemo recompute; user click →
       onTaskClick(task); pure helpers exposed via __testing__.

  AC-3 STATE-DRIVEN
       Features whose children include in_progress are default-expanded;
       fully-completed features are default-collapsed; only eb-* palette
       classes; Lucide icons only; no emojis.

  AC-4 UNWANTED
       null / undefined / non-array tasks render the empty fallback
       (data-testid=kanban-accordion-empty) without crashing; no
       hardcoded color literal outside the eb-* palette (#1a6648).

  DRIFT-GUARD
       The source must NOT regress to a Hermes-style flat 6-column board
       (columns: 6 / <Column index={5}> / "blocked" + "failed" status
       column flattened at the top level).

  VARIANT-RENDERING (anti-drift requirement)
       The `defaultAllOpen` prop is the sole variant control; when true,
       it forces all `<details open>` regardless of feature status.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ACCORDION = REPO_ROOT / "frontend" / "src" / "components" / "tasks" / "TaskKanbanAccordion.tsx"
EXISTING_KANBAN = REPO_ROOT / "frontend" / "src" / "components" / "tasks" / "TaskKanban.tsx"
TICKETS_JSON = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
S027_MOCK = REPO_ROOT / "docs" / "mocks" / "2026-05-09_v1" / "task" / "S-027-task-kanban.html"
AUDIT_DOC = REPO_ROOT / "docs" / "audit" / "2026-05-13_v2" / "T-007-01.md"


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def src() -> str:
    return ACCORDION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def existing_src() -> str:
    return EXISTING_KANBAN.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def ticket() -> dict:
    data = json.loads(TICKETS_JSON.read_text(encoding="utf-8"))
    for t in data["tickets"]:
        if t["id"] == "T-007-01":
            return t
    pytest.fail("T-007-01 ticket missing from tickets.json")


def _strip_comments(text: str) -> str:
    """Strip // line comments and /* ... */ block comments (best-effort)."""
    out: list[str] = []
    in_block = False
    for raw in text.splitlines():
        line = raw
        if in_block:
            if "*/" in line:
                line = line.split("*/", 1)[1]
                in_block = False
            else:
                continue
        if "/*" in line:
            before, _, after = line.partition("/*")
            if "*/" in after:
                line = before + after.split("*/", 1)[1]
            else:
                line = before
                in_block = True
        if "//" in line:
            idx = line.find("//")
            if idx >= 0:
                line = line[:idx] if idx > 0 else ""
        if line.strip():
            out.append(line)
    return "\n".join(out)


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — public surface + REUSE invariant
# ══════════════════════════════════════════════════════════════════════


def test_ac1_accordion_module_exists():
    """1.1 — TaskKanbanAccordion.tsx file is present."""
    assert ACCORDION.exists(), "TaskKanbanAccordion.tsx not found"


def test_ac1_existing_kanban_module_exists():
    """1.2 — existing TaskKanban.tsx still present (REUSE invariant)."""
    assert EXISTING_KANBAN.exists()


def test_ac1_existing_kanban_unchanged_no_accordion_dep(existing_src: str):
    """1.3 — existing TaskKanban.tsx must NOT import the new accordion."""
    assert "TaskKanbanAccordion" not in existing_src, (
        "Existing TaskKanban.tsx must remain REUSE / untouched by T-007-01."
    )


def test_ac1_existing_kanban_still_flat_6_columns(existing_src: str):
    """1.4 — existing flat 6-column board is intentionally preserved (REUSE)."""
    # The flat board (groupBy='status') has 6 STATUS_COLUMNS entries (Hermes
    # legacy). The CLAUDE.md §5.5 NG note targets this shape ONLY when it is
    # used for the kanban_accordion screen. The existing component coexists.
    assert "STATUS_COLUMNS" in existing_src
    matches = re.findall(r"id:\s*\"(todo|doing|blocked|review|done|failed)\"", existing_src)
    assert len(matches) == 6, f"existing flat board expected 6 columns, got {matches}"


@pytest.mark.parametrize(
    "name",
    [
        "TaskKanbanAccordion",
        "AccordionTask",
        "TaskKanbanAccordionProps",
        "statusToColumnId",
        "isFeatureInProgress",
        "isFeatureCompleted",
        "__testing__",
        "FOUR_COLUMNS",
        "VALID_COLUMN_IDS",
    ],
)
def test_ac1_required_public_symbols(src: str, name: str):
    """1.5 — required public + __testing__ symbols are all present."""
    assert name in src, f"missing symbol: {name}"


def test_ac1_four_columns_literal_definition(src: str):
    """1.6 — 4 columns Todo / In Progress / Review / Done are spelled out."""
    expected_ids = ('"todo"', '"in_progress"', '"review"', '"done"')
    for col_id in expected_ids:
        assert col_id in src, f"missing column id: {col_id}"
    # human-facing titles
    for title in ('"Todo"', '"In Progress"', '"Review"', '"Done"'):
        assert title in src, f"missing column title: {title}"


def test_ac1_documents_claude_md_section_5_5(src: str):
    """1.7 — source self-cites CLAUDE.md §5.5 (links spec → impl)."""
    assert "5.5" in src or "§5.5" in src
    assert "アコーディオン" in src or "accordion" in src.lower()


def test_ac1_mock_screen_id_s027_present(src: str):
    """1.8 — source references S-027 mock (cross-doc traceability)."""
    assert "S-027" in src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — useMemo + callbacks + helpers
# ══════════════════════════════════════════════════════════════════════


def test_ac2_uses_react_use_memo(src: str):
    """2.1 — props change triggers recompute via React.useMemo."""
    assert "React.useMemo" in src
    # at least 3 useMemo's: validTasks / features / childrenByFeature
    assert src.count("React.useMemo") >= 3


def test_ac2_on_task_click_invoked(src: str):
    """2.2 — onTaskClick callback is invoked with the task object."""
    assert "onTaskClick" in src
    # button onClick wires onTaskClick(task) (optional chain accepted)
    assert (
        "onTaskClick?.(task)" in src
        or "onTaskClick && onTaskClick(task)" in src
    )


def test_ac2_pure_helpers_in_testing_namespace(src: str):
    """2.3 — __testing__ exports the three pure helpers for unit testing."""
    # find __testing__ block and assert it lists all three helpers
    m = re.search(r"export const __testing__\s*=\s*\{([^}]+)\}", src, re.DOTALL)
    assert m, "__testing__ object literal not found"
    body = m.group(1)
    for helper in ("statusToColumnId", "isFeatureInProgress", "isFeatureCompleted"):
        assert helper in body, f"__testing__ missing helper: {helper}"


@pytest.mark.parametrize(
    "status,column_id",
    [
        ("pending", "todo"),
        ("in_progress", "in_progress"),
        ("review_needed", "review"),
        ("completed", "done"),
    ],
)
def test_ac2_status_to_column_mapping_present(src: str, status: str, column_id: str):
    """2.4 — each canonical status appears mapped to its 4-column id."""
    code = _strip_comments(src)
    assert f'"{status}"' in code, f"missing status literal {status!r}"
    assert f'"{column_id}"' in code, f"missing column literal {column_id!r}"


def test_ac2_children_by_feature_groups_by_parent(src: str):
    """2.5 — childrenByFeature builds Map keyed by parent_task_id."""
    assert "childrenByFeature" in src
    assert "parent_task_id" in src
    assert "new Map" in src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — default expand rule + eb palette + Lucide
# ══════════════════════════════════════════════════════════════════════


def test_ac3_default_expand_uses_is_feature_in_progress(src: str):
    """3.1 — defaultOpen is decided by isFeatureInProgress."""
    assert "isFeatureInProgress" in src
    assert "defaultOpen" in src


def test_ac3_default_collapse_uses_is_feature_completed(src: str):
    """3.2 — completed features are explicitly NOT auto-opened."""
    assert "isFeatureCompleted" in src
    # invariant: default open = inProgress && !completed
    assert re.search(r"inProgress\s*&&\s*!completed", src), (
        "expected `inProgress && !completed` guard for defaultOpen"
    )


def test_ac3_details_element_renders_open_attribute(src: str):
    """3.3 — accordion fallback uses native <details open={defaultOpen}>."""
    assert "<details" in src
    assert "open={defaultOpen}" in src


@pytest.mark.parametrize(
    "klass",
    ["border-eb-500", "border-eb-400", "border-eb-200", "bg-eb-50"],
)
def test_ac3_uses_eb_palette_class(src: str, klass: str):
    """3.4 — only eb-* palette classes are used (parametrized)."""
    assert klass in src, f"missing eb-* class: {klass}"


def test_ac3_no_non_eb_hex_color_literal(src: str):
    """3.5 — drift guard: no hex literal outside the eb primary (#1a6648)."""
    code = _strip_comments(src)
    matches = [
        m for m in re.findall(r"#[0-9a-fA-F]{6}", code)
        if m.lower() != "#1a6648"
    ]
    assert not matches, f"non-eb hex colors leaked into source: {matches}"


@pytest.mark.parametrize(
    "icon",
    ["Clock", "CheckCircle", "AlertCircle", "ChevronDown", "Folder"],
)
def test_ac3_lucide_icon_imported(src: str, icon: str):
    """3.6 — every required Lucide icon is imported from lucide-react."""
    assert 'from "lucide-react"' in src
    assert icon in src, f"missing Lucide icon: {icon}"


def test_ac3_no_emoji_in_source_via_lint(src: str):
    """3.7 — global emoji baseline (lint-mock.sh) still passes."""
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--emoji"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=15,
    )
    assert r.returncode == 0, f"emoji baseline broken:\n{r.stdout}\n{r.stderr}"


def test_ac3_no_emoji_codepoint_in_accordion_file(src: str):
    """3.8 — direct codepoint scan in TaskKanbanAccordion.tsx."""
    for ch in src:
        cp = ord(ch)
        # block emoji-rich planes: misc symbols & pictographs / emoticons / etc.
        if 0x1F300 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF:
            pytest.fail(f"emoji codepoint U+{cp:04X} found in source")


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — null / non-array fallback + no secret leak
# ══════════════════════════════════════════════════════════════════════


def test_ac4_empty_fallback_testid(src: str):
    """4.1 — fallback element carries the agreed data-testid."""
    assert 'data-testid="kanban-accordion-empty"' in src


def test_ac4_features_length_zero_branch_renders_fallback(src: str):
    """4.2 — features.length === 0 returns the empty fallback early."""
    assert "features.length === 0" in src


def test_ac4_array_isarray_null_guard(src: str):
    """4.3 — non-array tasks are coerced to [] (no crash)."""
    assert "Array.isArray(tasks)" in src
    # validTasks is the coerced array
    assert "validTasks" in src


def test_ac4_no_hardcoded_secret_pattern(src: str):
    """4.4 — no anthropic / supabase / bearer secrets hardcoded."""
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code
    assert "Bearer " not in code


# ══════════════════════════════════════════════════════════════════════
# DRIFT GUARD — Hermes flat 6-column shape MUST NOT reappear here
# ══════════════════════════════════════════════════════════════════════


def test_drift_guard_no_columns_count_six(src: str):
    """D.1 — no `columns: 6` / `columnsCount={6}` pattern in this file."""
    code = _strip_comments(src)
    forbidden_patterns = [
        r"columns\s*[:=]\s*6\b",
        r"columnsCount\s*=\s*\{?\s*6\s*\}?",
        r"COLUMN_COUNT\s*=\s*6\b",
    ]
    for pat in forbidden_patterns:
        m = re.search(pat, code)
        assert m is None, f"forbidden Hermes-6-col pattern matched: {pat} → {m!r}"


def test_drift_guard_no_column_index_5(src: str):
    """D.2 — no `<Column index={5}>` (signature of 6-col fixed layout)."""
    code = _strip_comments(src)
    assert not re.search(r"<Column[^>]*index\s*=\s*\{\s*5\s*\}", code)
    assert not re.search(r"<Column[^>]*idx\s*=\s*\{\s*5\s*\}", code)


def test_drift_guard_four_columns_array_length_is_four(src: str):
    """D.3 — FOUR_COLUMNS literal must contain exactly 4 entries."""
    # naive but effective: count `id:` lines inside FOUR_COLUMNS block
    m = re.search(r"FOUR_COLUMNS[^=]*=\s*\[(.+?)\];", src, re.DOTALL)
    assert m, "FOUR_COLUMNS array literal not found"
    block = m.group(1)
    id_count = len(re.findall(r"\bid:\s*\"", block))
    assert id_count == 4, f"FOUR_COLUMNS must have 4 entries, found {id_count}"


def test_drift_guard_no_blocked_status_top_level_column(src: str):
    """D.4 — `blocked_dependency` / `failed` / `cancelled` are NOT top-level columns.

    The Hermes shape used 6 top-level columns including "blocked" + "failed".
    The accordion design folds question/dependency blockers into Review and
    leaves failed/cancelled out of the active board entirely.
    """
    code = _strip_comments(src)
    # blocked_dependency is allowed in matches (no — accordion treats only
    # blocked_question as review). Assert blocked_dependency is NOT mapped
    # to any column id at all.
    m = re.search(r"FOUR_COLUMNS[^=]*=\s*\[(.+?)\];", code, re.DOTALL)
    assert m
    block = m.group(1)
    assert "blocked_dependency" not in block, (
        "blocked_dependency must not be a top-level column (avoid Hermes 6-col)"
    )
    assert '"failed"' not in block
    assert '"cancelled"' not in block


def test_drift_guard_review_collapses_question_into_single_column(src: str):
    """D.5 — review column matches review_needed (and at most blocked_question)."""
    m = re.search(r"FOUR_COLUMNS[^=]*=\s*\[(.+?)\];", src, re.DOTALL)
    assert m
    block = m.group(1)
    # the "review" entry must list review_needed
    assert "review_needed" in block
    # blocked_question may be folded in; blocked_dependency must NOT
    assert "blocked_dependency" not in block


# ══════════════════════════════════════════════════════════════════════
# VARIANT-RENDERING — defaultAllOpen prop produces a distinct DOM shape
# ══════════════════════════════════════════════════════════════════════


def test_variant_default_all_open_prop_declared(src: str):
    """V.1 — defaultAllOpen prop is part of the public surface."""
    assert "defaultAllOpen" in src
    # default value MUST be false (so behaviour matches CLAUDE.md §5.5 by
    # default; the prop is purely an override for tests / power users).
    assert re.search(r"defaultAllOpen\s*=\s*false", src)


def test_variant_default_all_open_forces_open_regardless_of_status(src: str):
    """V.2 — defaultAllOpen is ORed into defaultOpen (forces all <details open>).

    This guarantees the variant produces a *different DOM tree* (all
    `<details>` carry `open`) than the default mode (only in-progress
    features carry `open`).
    """
    # the expression must be `defaultAllOpen || (inProgress && !completed)`
    pattern = re.compile(
        r"defaultOpen\s*=\s*defaultAllOpen\s*\|\|\s*\(?\s*inProgress\s*&&\s*!completed",
    )
    assert pattern.search(src), (
        "expected `defaultOpen = defaultAllOpen || (inProgress && !completed)` to "
        "guarantee variant DOM divergence"
    )


def test_variant_data_default_open_attribute_emitted(src: str):
    """V.3 — every <details> emits data-default-open for runtime introspection.

    This lets DOM-level tests / Storybook see *which* features opened,
    which is the runtime evidence that the variant changed the tree.
    """
    assert 'data-default-open=' in src
    assert "defaultOpen ?" in src


# ══════════════════════════════════════════════════════════════════════
# REFACTOR invariants (CLAUDE.md §5.3 + ticket label = REFACTOR)
# ══════════════════════════════════════════════════════════════════════


def test_refactor_invariant_existing_kanban_byte_baseline(existing_src: str):
    """R.1 — existing TaskKanban.tsx invariant: still exports flat board + groupBy."""
    # The REFACTOR contract is "introduce accordion as a *new* file, leave
    # existing TaskKanban.tsx unchanged for callers that still rely on it".
    assert "export function TaskKanban" in existing_src
    assert "GroupBy" in existing_src
    assert 'groupBy === "feature"' in existing_src


def test_refactor_invariant_no_langgraph_litellm_import(src: str):
    """R.2 — frontend bundle must not import banned AI stack libs (CLAUDE.md §3)."""
    code = _strip_comments(src)
    for banned in ("langgraph", "langchain", "litellm"):
        assert banned not in code.lower(), f"banned import found: {banned}"


def test_refactor_invariant_no_agpl_dep_reference(src: str):
    """R.3 — no AGPL-tagged dependency mention (SaaS license guard)."""
    code = _strip_comments(src)
    # bare grep — full lint covered by scripts/lint-mock.sh
    assert "AGPL" not in code


# ══════════════════════════════════════════════════════════════════════
# Ticket coherence (tickets.json metadata)
# ══════════════════════════════════════════════════════════════════════


def test_ticket_has_four_ears_ac(ticket: dict):
    """T.1 — ticket carries exactly 4 EARS ACs (UBIQUITOUS / EVENT / STATE / UNWANTED)."""
    types = [ac["type"] for ac in ticket["acceptance_criteria"]]
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "UNWANTED"], (
        f"unexpected EARS sequence: {types}"
    )


def test_ticket_label_is_refactor(ticket: dict):
    """T.2 — label = REFACTOR (this is an audit task)."""
    assert ticket["label"] == "REFACTOR"


def test_ticket_existing_files_points_to_taskkanban_tsx(ticket: dict):
    """T.3 — existing_files records TaskKanban.tsx as the REFACTOR target."""
    assert "frontend/src/components/tasks/TaskKanban.tsx" in ticket["existing_files"]


def test_ticket_ac_text_is_not_generic_stub(ticket: dict):
    """T.4 — drift guard: no leftover generic-stub phrasing in any AC."""
    generic = [
        "as specified by feature",
        "When the user interacts with the UI for T-007-01",
        "While refactoring for T-007-01 is in progress",
        "If invalid input or unauthorized actor is detected during T-007-01",
    ]
    full = " ".join(ac["text"] for ac in ticket["acceptance_criteria"])
    for phrase in generic:
        assert phrase not in full, f"generic-stub phrase leaked into AC: {phrase!r}"


def test_ticket_ac_cites_taskkanban_accordion_and_section_5_5(ticket: dict):
    """T.5 — AC text explicitly cites TaskKanbanAccordion.tsx + CLAUDE.md §5.5."""
    full = " ".join(ac["text"] for ac in ticket["acceptance_criteria"])
    assert "TaskKanbanAccordion.tsx" in full
    assert "CLAUDE.md §5.5" in full
    assert "Todo/In Progress/Review/Done" in full or "4 列" in full


def test_audit_doc_present():
    """T.6 — audit markdown exists alongside this test."""
    assert AUDIT_DOC.exists(), f"audit doc not found: {AUDIT_DOC}"


def test_mock_s027_meta_links_to_t_007_01():
    """T.7 — S-027 mock declares `task-ids` includes T-007-01."""
    html = S027_MOCK.read_text(encoding="utf-8")
    assert "T-007-01" in html
    assert 'name="feature-id" content="F-007"' in html
