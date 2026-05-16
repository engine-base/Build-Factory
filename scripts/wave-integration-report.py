#!/usr/bin/env python3
"""Wave 完了集計レポート生成 (T-FOUNDATION-04).

distributed-dev が出力する各 task の branch-package.json を集計し、
skills/integration/references/v3-core.md §119 で定義された
Wave Integration Report スキーマで Markdown / JSON を出力する。

集計ロジック:
  1. branch-packages 入力から N 件の task entry を読む
     - directory mode: <dir>/*.json (default: .claude/branches/)
     - file mode    : 単一の JSON file (consolidated fixture / wave wrapper)
  2. final_state を 4 カテゴリへ分類:
     auto-merged / retried / escalated / rolled-back
  3. deliverable_layer (foundation / backend / ui / polish / drift_fix) で集計
  4. <branch-packages>/_drift.json (T-FOUNDATION-05 出力) があれば rule_id ごとに集計
     無ければ drift = 0 で stderr に warning
  5. failure_count >= 3 の task を failure analysis section に抽出
  6. Jinja2 template (scripts/templates/wave-integration-report.md.jinja2) でレンダリング
  7. --format json では同データを JSON で出力
  8. --self-test では fixture 2 件 (small-3task / large-30task) を golden と byte-identical 比較

Usage:
  python3 scripts/wave-integration-report.py --wave W0a \
      --branch-packages .claude/branches/ \
      --output docs/integration/2026-05-16_W0a.md
  python3 scripts/wave-integration-report.py --wave W0a \
      --branch-packages scripts/tests/fixtures/wave-report/small-3task.json \
      --format json
  python3 scripts/wave-integration-report.py --self-test

Exit code:
  0 = success / self-test PASS
  1 = self-test FAIL or rendering error
  2 = argument / IO error
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BRANCHES_DIR = ROOT / ".claude/branches"
DEFAULT_TEMPLATE = ROOT / "scripts/templates/wave-integration-report.md.jinja2"
DRIFT_FILE_NAME = "_drift.json"

VALID_LAYERS = ("foundation", "backend", "ui", "polish", "drift_fix")
VALID_STATES = ("auto-merged", "retried", "escalated", "rolled-back")
# final_state -> internal key (replace dash with underscore for Jinja attribute access)
STATE_KEYS = {
    "auto-merged": "auto_merged",
    "retried": "retried",
    "escalated": "escalated",
    "rolled-back": "rolled_back",
}
FAILURE_THRESHOLD = 3


@dataclass
class TaskEntry:
    """1 task 分の branch-package 情報 (集計に必要な fields のみ)."""

    task_id: str
    final_state: str
    failure_count: int
    deliverable_layer: str
    last_gate_failure: str | None = None
    last_failure_reason: str | None = None


@dataclass
class WaveContext:
    """template render に必要な集計済み context."""

    wave_id: str
    phase_id: str
    period_start: str
    period_end: str
    parallel_sessions: int
    task_total: int
    layer_counts: dict[str, int]
    state_layer: dict[str, dict[str, int]]
    failure_analysis: list[dict[str, Any]] = field(default_factory=lambda: [])
    drift_present: bool = False
    drift_rows: list[dict[str, Any]] = field(default_factory=lambda: [])
    next_wave: str = ""
    git_state: dict[str, Any] = field(default_factory=lambda: {})


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------


def _normalize_task(raw: dict[str, Any]) -> TaskEntry:
    """branch-package dict を TaskEntry へ正規化.

    flexible schema 対応: final_state 欠落 / failure_count 欠落 / 旧 fields も許容.
    """
    task_id = str(raw.get("task_id") or raw.get("id") or "T-UNKNOWN")
    raw_state = str(raw.get("final_state") or raw.get("status") or "auto-merged").lower()
    # alias map: 旧 format の "merged" / "merge" を auto-merged に寄せる
    state_aliases = {
        "merged": "auto-merged",
        "merge": "auto-merged",
        "auto_merged": "auto-merged",
        "rolled_back": "rolled-back",
        "rollback": "rolled-back",
        "rolledback": "rolled-back",
        "human_escalated": "escalated",
    }
    final_state = state_aliases.get(raw_state, raw_state)
    if final_state not in VALID_STATES:
        # unknown は escalated 扱いで可視化 (silent drop は危険)
        print(
            f"warning: task {task_id} unknown final_state '{raw_state}' -> escalated",
            file=sys.stderr,
        )
        final_state = "escalated"

    failure_count_raw = raw.get("failure_count", 0)
    try:
        failure_count = int(failure_count_raw)
    except (TypeError, ValueError):
        failure_count = 0

    layer = str(raw.get("deliverable_layer") or "foundation").lower()
    # alias: "drift-fix" → "drift_fix"
    if layer == "drift-fix":
        layer = "drift_fix"
    if layer not in VALID_LAYERS:
        print(
            f"warning: task {task_id} unknown deliverable_layer '{layer}' -> foundation",
            file=sys.stderr,
        )
        layer = "foundation"

    last_gate = raw.get("last_gate_failure")
    last_reason = raw.get("last_failure_reason")
    return TaskEntry(
        task_id=task_id,
        final_state=final_state,
        failure_count=failure_count,
        deliverable_layer=layer,
        last_gate_failure=str(last_gate) if last_gate else None,
        last_failure_reason=str(last_reason) if last_reason else None,
    )


def _load_consolidated(path: Path) -> dict[str, Any]:
    """consolidated JSON (wrapper) を読む."""
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"error: failed to read {path}: {e}") from e
    if not isinstance(data, dict):
        raise SystemExit(f"error: {path} must be a JSON object")
    return cast(dict[str, Any], data)


def load_branch_packages(
    branch_packages: Path,
) -> tuple[list[TaskEntry], dict[str, Any] | None, dict[str, Any]]:
    """branch-packages 入力を読み (tasks, drift, wrapper_meta) を返す.

    対応形式:
      - directory: <dir>/*.json を glob, 各 file は 1 task の branch-package.json.
                   <dir>/_drift.json (任意) を drift として扱う.
      - file: 単一 wrapper JSON.
              `branch_packages: [...]` 配列 + 任意の `drift` / `git_state` / wave meta を持つ.
    """
    if branch_packages.is_dir():
        wrapper_meta: dict[str, Any] = {}
        tasks: list[TaskEntry] = []
        drift: dict[str, Any] | None = None
        for entry in sorted(branch_packages.glob("*.json")):
            if entry.name == DRIFT_FILE_NAME:
                try:
                    drift_raw: Any = json.loads(entry.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as e:
                    print(
                        f"warning: failed to read drift {entry}: {e}",
                        file=sys.stderr,
                    )
                    continue
                if isinstance(drift_raw, dict):
                    drift = cast(dict[str, Any], drift_raw)
                continue
            try:
                raw: Any = json.loads(entry.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                print(
                    f"warning: skip malformed branch-package {entry}: {e}",
                    file=sys.stderr,
                )
                continue
            if not isinstance(raw, dict):
                print(
                    f"warning: skip non-object branch-package {entry}",
                    file=sys.stderr,
                )
                continue
            tasks.append(_normalize_task(cast(dict[str, Any], raw)))
        return tasks, drift, wrapper_meta

    if not branch_packages.is_file():
        raise SystemExit(
            f"error: --branch-packages path not found: {branch_packages}"
        )

    data = _load_consolidated(branch_packages)
    raw_tasks_value: Any = data.get("branch_packages") or data.get("tasks") or []
    if not isinstance(raw_tasks_value, list):
        raise SystemExit("error: wrapper.branch_packages must be a list")
    raw_tasks: list[Any] = cast(list[Any], raw_tasks_value)
    tasks = [
        _normalize_task(cast(dict[str, Any], t))
        for t in raw_tasks
        if isinstance(t, dict)
    ]
    drift_value: Any = data.get("drift")
    drift = cast(dict[str, Any], drift_value) if isinstance(drift_value, dict) else None
    wrapper_meta = {
        k: v for k, v in data.items() if k not in ("branch_packages", "tasks", "drift")
    }
    return tasks, drift, wrapper_meta


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _empty_layer_counts() -> dict[str, int]:
    return {layer: 0 for layer in VALID_LAYERS}


def aggregate(
    tasks: list[TaskEntry],
    drift: dict[str, Any] | None,
    *,
    next_wave: str,
    wave_id: str,
) -> tuple[dict[str, int], dict[str, dict[str, int]], list[dict[str, Any]], bool, list[dict[str, Any]]]:
    """tasks + drift を集計し template context fragments を返す."""
    # layer counts
    layer_counts = _empty_layer_counts()
    for task in tasks:
        layer_counts[task.deliverable_layer] += 1

    # state x layer matrix
    state_layer: dict[str, dict[str, int]] = OrderedDict()
    for state in VALID_STATES:
        key = STATE_KEYS[state]
        state_layer[key] = _empty_layer_counts()
        state_layer[key]["total"] = 0
    for task in tasks:
        key = STATE_KEYS[task.final_state]
        state_layer[key][task.deliverable_layer] += 1
        state_layer[key]["total"] += 1

    # failure analysis: failure_count >= 3 (decisive な連続失敗のみ)
    failure_analysis: list[dict[str, Any]] = []
    for task in tasks:
        if task.failure_count >= FAILURE_THRESHOLD:
            failure_analysis.append(
                {
                    "task_id": task.task_id,
                    "failure_count": task.failure_count,
                    "last_gate_failure": task.last_gate_failure,
                    "last_failure_reason": task.last_failure_reason,
                }
            )

    # drift aggregation
    drift_present = False
    drift_rows: list[dict[str, Any]] = []
    if drift is None:
        print(
            "warning: _drift.json absent -> drift = 0 (assume no lint drift in this wave)",
            file=sys.stderr,
        )
    else:
        entries: Any = drift.get("entries") or drift.get("drift") or []
        # entries may be a list of {rule_id, task_id?} or a dict {rule_id: count}
        rule_counts: dict[str, int] = {}
        rule_tasks: dict[str, list[str]] = {}
        if isinstance(entries, dict):
            entries_dict = cast(dict[str, Any], entries)
            for rid_any, count_any in entries_dict.items():
                try:
                    rule_counts[str(rid_any)] = int(count_any)
                except (TypeError, ValueError):
                    continue
        elif isinstance(entries, list):
            entries_list = cast(list[Any], entries)
            for e in entries_list:
                if not isinstance(e, dict):
                    continue
                e_dict = cast(dict[str, Any], e)
                rule_id = str(e_dict.get("rule_id") or "unknown")
                rule_counts[rule_id] = rule_counts.get(rule_id, 0) + 1
                fix_value: Any = e_dict.get("fix_task") or e_dict.get("task_id")
                if fix_value:
                    rule_tasks.setdefault(rule_id, []).append(str(fix_value))

        if rule_counts:
            drift_present = True
            for idx, rule_id in enumerate(sorted(rule_counts.keys()), start=1):
                tasks_str = (
                    ", ".join(sorted(set(rule_tasks.get(rule_id, []))))
                    if rule_tasks.get(rule_id)
                    else f"T-DRIFT-{next_wave}-{idx:02d}"
                )
                drift_rows.append(
                    {
                        "rule_id": rule_id,
                        "count": rule_counts[rule_id],
                        "fix_tasks": tasks_str,
                    }
                )

    return layer_counts, state_layer, failure_analysis, drift_present, drift_rows


# ---------------------------------------------------------------------------
# Context build & rendering
# ---------------------------------------------------------------------------


def build_context(
    wave_id: str,
    tasks: list[TaskEntry],
    drift: dict[str, Any] | None,
    wrapper_meta: dict[str, Any],
) -> WaveContext:
    """集計を実行し WaveContext を生成."""
    phase_id = str(wrapper_meta.get("phase_id") or "Foundation")
    period_start = str(wrapper_meta.get("period_start") or "")
    period_end = str(wrapper_meta.get("period_end") or "")
    parallel_sessions = int(wrapper_meta.get("parallel_sessions") or len(tasks))
    next_wave = str(wrapper_meta.get("next_wave") or _infer_next_wave(wave_id))

    layer_counts, state_layer, failure_analysis, drift_present, drift_rows = aggregate(
        tasks, drift, next_wave=next_wave, wave_id=wave_id
    )

    raw_git: Any = wrapper_meta.get("git_state")
    git_state_raw: dict[str, Any] = (
        cast(dict[str, Any], raw_git) if isinstance(raw_git, dict) else {}
    )
    git_state: dict[str, Any] = {
        "main_ahead": git_state_raw.get("main_ahead", 0),
        "main_head": git_state_raw.get("main_head", "unknown"),
        "backend_test_coverage": git_state_raw.get("backend_test_coverage", "n/a"),
        "frontend_type_check": git_state_raw.get("frontend_type_check", "n/a"),
        "all_gates_status": git_state_raw.get("all_gates_status", "unknown"),
    }

    return WaveContext(
        wave_id=wave_id,
        phase_id=phase_id,
        period_start=period_start,
        period_end=period_end,
        parallel_sessions=parallel_sessions,
        task_total=len(tasks),
        layer_counts=layer_counts,
        state_layer=state_layer,
        failure_analysis=failure_analysis,
        drift_present=drift_present,
        drift_rows=drift_rows,
        next_wave=next_wave,
        git_state=git_state,
    )


def _infer_next_wave(wave_id: str) -> str:
    """W0a → W0b / W0 → W1 / W12 → W13 のような簡易推定."""
    if not wave_id:
        return ""
    # try suffix letter increment (W0a -> W0b)
    last = wave_id[-1]
    if last.isalpha() and len(wave_id) > 1:
        prev = wave_id[:-1]
        next_char = chr(ord(last) + 1)
        return prev + next_char
    # try numeric tail increment
    digits = ""
    i = len(wave_id) - 1
    while i >= 0 and wave_id[i].isdigit():
        digits = wave_id[i] + digits
        i -= 1
    if digits:
        prefix = wave_id[: i + 1]
        return f"{prefix}{int(digits) + 1}"
    return f"{wave_id}-next"


def render_markdown(ctx: WaveContext, template_path: Path) -> str:
    """Jinja2 template で Markdown 文字列を生成."""
    try:
        import jinja2
    except ImportError as e:  # pragma: no cover - jinja2 is required
        raise SystemExit(
            "error: jinja2 not available. Install with 'pip install jinja2'."
        ) from e

    if not template_path.exists():
        raise SystemExit(f"error: template not found: {template_path}")

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_path.parent)),
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )
    template = env.get_template(template_path.name)
    return template.render(
        wave_id=ctx.wave_id,
        phase_id=ctx.phase_id,
        period_start=ctx.period_start,
        period_end=ctx.period_end,
        parallel_sessions=ctx.parallel_sessions,
        task_total=ctx.task_total,
        layer_counts=ctx.layer_counts,
        state_layer=ctx.state_layer,
        failure_analysis=ctx.failure_analysis,
        drift_present=ctx.drift_present,
        drift_rows=ctx.drift_rows,
        next_wave=ctx.next_wave,
        git_state=ctx.git_state,
    )


def render_json(ctx: WaveContext) -> str:
    """同データを JSON 文字列で生成 (--format json)."""
    payload = {
        "version": "v3",
        "skill": "integration",
        "wave_id": ctx.wave_id,
        "phase_id": ctx.phase_id,
        "period_start": ctx.period_start,
        "period_end": ctx.period_end,
        "parallel_sessions": ctx.parallel_sessions,
        "task_total": ctx.task_total,
        "layer_counts": ctx.layer_counts,
        "state_layer": ctx.state_layer,
        "failure_analysis": ctx.failure_analysis,
        "drift_present": ctx.drift_present,
        "drift_rows": ctx.drift_rows,
        "next_wave": ctx.next_wave,
        "git_state": ctx.git_state,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def run_self_test() -> int:
    """fixture 2 件 (small-3task / large-30task) を golden と byte-identical 比較."""
    fixtures_dir = ROOT / "scripts/tests/fixtures/wave-report"
    cases: list[tuple[str, str, Path, Path]] = [
        (
            "small-3task",
            "W0a",
            fixtures_dir / "small-3task.json",
            fixtures_dir / "expected-small.md",
        ),
        (
            "large-30task",
            "W1",
            fixtures_dir / "large-30task.json",
            fixtures_dir / "expected-large.md",
        ),
    ]
    print("self-test: wave-integration-report")
    print("=" * 60)
    all_ok = True
    for label, wave_id, fixture_path, expected_path in cases:
        if not fixture_path.exists():
            print(f"  [FAIL] {label}: fixture missing {fixture_path}")
            all_ok = False
            continue
        if not expected_path.exists():
            print(f"  [FAIL] {label}: golden missing {expected_path}")
            all_ok = False
            continue
        tasks, drift, wrapper_meta = load_branch_packages(fixture_path)
        ctx = build_context(wave_id, tasks, drift, wrapper_meta)
        actual = render_markdown(ctx, DEFAULT_TEMPLATE)
        expected = expected_path.read_text(encoding="utf-8")
        if actual == expected:
            print(f"  [PASS] {label}: byte-identical ({len(actual)} bytes)")
        else:
            print(f"  [FAIL] {label}: rendered output differs from golden")
            _show_diff(expected, actual)
            all_ok = False

    print("=" * 60)
    if all_ok:
        print("self-test: OK (2/2)")
        return 0
    print("self-test: FAIL")
    return 1


def _show_diff(expected: str, actual: str, max_lines: int = 20) -> None:
    """簡易 diff 表示."""
    exp_lines = expected.splitlines()
    act_lines = actual.splitlines()
    shown = 0
    for i, (e, a) in enumerate(zip(exp_lines, act_lines)):
        if e != a:
            print(f"    line {i + 1}: expected={e!r}")
            print(f"    line {i + 1}: actual  ={a!r}")
            shown += 1
            if shown >= max_lines:
                print(f"    ... (truncated at {max_lines} diff lines)")
                return
    if len(exp_lines) != len(act_lines):
        print(
            f"    length differs: expected={len(exp_lines)} actual={len(act_lines)}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="wave-integration-report",
        description="Wave 完了集計レポート生成 (Markdown / JSON)",
    )
    parser.add_argument(
        "--wave",
        default=None,
        help="wave id (e.g. W0a). Required unless --self-test.",
    )
    parser.add_argument(
        "--branch-packages",
        default=str(DEFAULT_BRANCHES_DIR),
        help="branch-package.json directory or consolidated wrapper JSON "
        f"(default: {DEFAULT_BRANCHES_DIR.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="出力 path (default: stdout)",
    )
    parser.add_argument(
        "--format",
        choices=("md", "json"),
        default="md",
        help="出力 format (default: md)",
    )
    parser.add_argument(
        "--template",
        default=str(DEFAULT_TEMPLATE),
        help="Jinja2 template path",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="2 fixture (small-3task / large-30task) と golden を byte-identical 比較",
    )

    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if args.wave is None:
        print("error: --wave is required (or --self-test)", file=sys.stderr)
        return 2

    branch_packages_path = Path(args.branch_packages)
    if not branch_packages_path.is_absolute():
        branch_packages_path = (Path.cwd() / branch_packages_path).resolve()

    template_path = Path(args.template)
    if not template_path.is_absolute():
        template_path = (Path.cwd() / template_path).resolve()

    tasks, drift, wrapper_meta = load_branch_packages(branch_packages_path)
    ctx = build_context(args.wave, tasks, drift, wrapper_meta)

    if args.format == "md":
        text = render_markdown(ctx, template_path)
    else:
        text = render_json(ctx)

    if args.output:
        out_path = Path(args.output)
        if not out_path.is_absolute():
            out_path = (Path.cwd() / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
