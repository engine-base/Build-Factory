#!/usr/bin/env python3
"""Phase gate 機械判定スクリプト (T-FOUNDATION-06).

Foundation / Backend / UI / Polish / Release の各 phase 移行を機械判定する。
profile (Markdown) から `## Phase gate criteria: <phase>` セクションを抽出し、
各 criterion の tool_command を実行 + evidence_path 存在確認で green/red を判定。

出力: phase-gate-decision.json schema (skills/integration/references/v3-core.md §172)
  - decision: OPEN_GATE | PENDING | BLOCKED
  - exit code: 0 (OPEN_GATE/PENDING) | 1 (BLOCKED) | 2 (invalid arg)

Usage:
  python3 scripts/check-phase-gate.py --phase foundation
  python3 scripts/check-phase-gate.py --phase backend --profile <path> --output out.json
  python3 scripts/check-phase-gate.py --self-test

Profile format (Markdown table):
  ## Phase gate criteria: <phase_name>

  | criterion_name | tool_command | evidence_path | description |
  |---|---|---|---|
  | name1 | `cmd1` | path/to/evidence | desc1 |

Note on security:
  subprocess.run(..., shell=True) is used because tool_command may be a shell
  pipeline. profile files are internal (committed to repo), not user-supplied
  at runtime. Do not run with profiles from untrusted sources.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE = ROOT / "skills/task-decomposition/references/profiles/build-factory.md"
VALID_PHASES = ("foundation", "backend", "ui", "polish", "release")
COMMAND_TIMEOUT_SEC = 60


@dataclass
class Criterion:
    """1 つの phase gate criterion."""

    name: str
    tool_command: str
    evidence_path: str
    description: str


@dataclass
class CriterionResult:
    """criterion 実行結果."""

    name: str
    status: str  # "green" | "red"
    evidence: str
    failure_reason: str = ""


@dataclass
class GateDecision:
    """phase gate 判定結果."""

    phase_transition: str
    evaluated_at: str
    criteria: list[CriterionResult] = field(default_factory=lambda: [])
    decision: str = "PENDING"  # OPEN_GATE | PENDING | BLOCKED
    block_release_until: list[str] | None = None


def parse_profile(profile_path: Path, phase: str) -> list[Criterion]:
    """profile MD から指定 phase の criteria を抽出する.

    対応 format:
      1. Markdown table: ``| name | `cmd` | evidence | desc |``
      2. List entry:     ``- name: tool=cmd evidence=path``

    section 不在の場合は空 list を返す (PENDING 判定の trigger).
    """
    if not profile_path.exists():
        return []

    text = profile_path.read_text(encoding="utf-8")
    # section header matching: case-insensitive (foundation / Foundation 両対応)
    header_pattern = re.compile(
        r"^##\s+Phase gate criteria:\s*(\S+)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )

    section_text = ""
    for match in header_pattern.finditer(text):
        section_phase = match.group(1).strip().lower()
        if section_phase != phase.lower():
            continue
        start = match.end()
        # 次の H2 か EOF まで
        rest = text[start:]
        next_h2 = re.search(r"^##\s+", rest, re.MULTILINE)
        section_text = rest[: next_h2.start()] if next_h2 else rest
        break

    if not section_text.strip():
        return []

    criteria: list[Criterion] = []

    # 1. Markdown table parsing
    table_rows = _parse_markdown_table(section_text)
    for row in table_rows:
        if len(row) < 2:
            continue
        name = row[0].strip()
        if not name or name.lower() in ("criterion_name", "---"):
            continue
        tool_command = _unwrap_backticks(row[1].strip()) if len(row) > 1 else ""
        evidence_path = row[2].strip() if len(row) > 2 else ""
        description = row[3].strip() if len(row) > 3 else ""
        if not tool_command and not evidence_path:
            continue
        criteria.append(
            Criterion(
                name=name,
                tool_command=tool_command,
                evidence_path=evidence_path,
                description=description,
            )
        )

    # 2. List entry parsing: `- name: tool=cmd evidence=path`
    list_pattern = re.compile(
        r"^-\s+(?P<name>[\w\-.]+):\s*"
        r"tool=(?P<tool>[^\n]*?)"
        r"(?:\s+evidence=(?P<evidence>\S+))?"
        r"\s*$",
        re.MULTILINE,
    )
    for m in list_pattern.finditer(section_text):
        name = m.group("name").strip()
        tool = _unwrap_backticks(m.group("tool").strip())
        evidence = (m.group("evidence") or "").strip()
        # dedup: table に同名がいたら skip
        if any(c.name == name for c in criteria):
            continue
        criteria.append(
            Criterion(
                name=name,
                tool_command=tool,
                evidence_path=evidence,
                description="",
            )
        )

    return criteria


def _parse_markdown_table(section_text: str) -> list[list[str]]:
    """Markdown table を行ごとの cell list として返す."""
    rows: list[list[str]] = []
    for line in section_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        # separator 行 (`|---|---|`) は skip
        inner = stripped.strip("|")
        if re.fullmatch(r"[\s\-:|]+", inner):
            continue
        cells = [c.strip() for c in inner.split("|")]
        rows.append(cells)
    return rows


def _unwrap_backticks(s: str) -> str:
    """Markdown 内の backtick を剥がす: `cmd` → cmd."""
    if len(s) >= 2 and s.startswith("`") and s.endswith("`"):
        return s[1:-1]
    return s


def evaluate_criterion(criterion: Criterion) -> CriterionResult:
    """1 criterion を評価し CriterionResult を返す."""
    failure_reasons: list[str] = []
    evidence_parts: list[str] = []

    # 1. tool_command 実行
    cmd_ok = True
    cmd_output_snippet = ""
    if criterion.tool_command:
        try:
            # NOTE: shell=True は profile が internal (committed) なので OK.
            # 外部 profile を渡す場合は再考すること.
            proc = subprocess.run(  # noqa: S602 (shell=True intentional)
                criterion.tool_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT_SEC,
                check=False,
            )
            combined = (proc.stdout + proc.stderr).strip()
            cmd_output_snippet = combined[:200]
            if proc.returncode != 0:
                cmd_ok = False
                failure_reasons.append(
                    f"tool_command exit {proc.returncode}: {cmd_output_snippet[:120]}"
                )
            else:
                suffix = f" output={cmd_output_snippet}" if cmd_output_snippet else ""
                evidence_parts.append(f"cmd exit 0{suffix}")
        except subprocess.TimeoutExpired:
            cmd_ok = False
            failure_reasons.append(f"tool_command timeout after {COMMAND_TIMEOUT_SEC}s")
        except OSError as e:
            cmd_ok = False
            failure_reasons.append(f"tool_command error: {e}")

    # 2. evidence_path 存在確認
    ev_ok = True
    if criterion.evidence_path:
        ep = Path(criterion.evidence_path)
        if not ep.is_absolute():
            ep = ROOT / ep
        if not ep.exists():
            ev_ok = False
            failure_reasons.append(f"evidence_path missing: {criterion.evidence_path}")
        else:
            # JSON parse の best-effort
            if ep.suffix == ".json":
                try:
                    json.loads(ep.read_text(encoding="utf-8"))
                    evidence_parts.append(
                        f"evidence_path exists (JSON ok): {criterion.evidence_path}"
                    )
                except json.JSONDecodeError as e:
                    ev_ok = False
                    failure_reasons.append(f"evidence_path JSON parse fail: {e}")
            else:
                evidence_parts.append(
                    f"evidence_path exists: {criterion.evidence_path}"
                )

    status = "green" if (cmd_ok and ev_ok) else "red"
    evidence_str = " | ".join(evidence_parts)[:200] if evidence_parts else ""
    failure_reason_str = "; ".join(failure_reasons)

    return CriterionResult(
        name=criterion.name,
        status=status,
        evidence=evidence_str,
        failure_reason=failure_reason_str,
    )


def build_decision(phase: str, results: list[CriterionResult]) -> GateDecision:
    """results 集計 → OPEN_GATE / PENDING / BLOCKED を決定."""
    evaluated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    decision = GateDecision(
        phase_transition=f"{phase} → next",
        evaluated_at=evaluated_at,
        criteria=results,
    )

    if not results:
        decision.decision = "PENDING"
        decision.block_release_until = None
        return decision

    failing = [r for r in results if r.status != "green"]
    if not failing:
        decision.decision = "OPEN_GATE"
        decision.block_release_until = None
    else:
        decision.decision = "BLOCKED"
        decision.block_release_until = [
            f"{r.name}: {r.failure_reason}" if r.failure_reason else r.name
            for r in failing
        ]
    return decision


def decision_to_dict(decision: GateDecision) -> dict[str, Any]:
    """phase-gate-decision.json schema に整形."""
    return {
        "version": "v3",
        "skill": "integration",
        "decisions": [
            {
                "phase_transition": decision.phase_transition,
                "evaluated_at": decision.evaluated_at,
                "criteria": [
                    {"name": r.name, "status": r.status, "evidence": r.evidence}
                    for r in decision.criteria
                ],
                "decision": decision.decision,
                "block_release_until": decision.block_release_until,
            }
        ],
    }


def run_phase_check(phase: str, profile: Path, output: Path | None) -> int:
    """1 phase 分の check を実行し exit code を返す."""
    criteria = parse_profile(profile, phase)
    results = [evaluate_criterion(c) for c in criteria]
    decision = build_decision(phase, results)
    payload = decision_to_dict(decision)
    text = json.dumps(payload, indent=2, ensure_ascii=False)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)

    if decision.decision == "BLOCKED":
        return 1
    return 0  # OPEN_GATE or PENDING


def run_self_test() -> int:
    """2 fixture (all-pass / one-fail) を実行し expected と一致確認."""
    fixtures_dir = ROOT / "scripts/tests/fixtures/phase-gate"
    cases: list[tuple[str, Path, str, int]] = [
        # (label, profile_path, expected_decision, expected_exit)
        ("all-pass", fixtures_dir / "profile-all-pass.md", "OPEN_GATE", 0),
        ("one-fail", fixtures_dir / "profile-one-fail.md", "BLOCKED", 1),
    ]
    all_ok = True
    print("self-test: phase gate checker")
    print("=" * 60)
    for label, profile_path, expected_decision, expected_exit in cases:
        if not profile_path.exists():
            print(f"  [FAIL] {label}: fixture missing {profile_path}")
            all_ok = False
            continue
        criteria = parse_profile(profile_path, "foundation")
        results = [evaluate_criterion(c) for c in criteria]
        decision = build_decision("foundation", results)
        actual_exit = 1 if decision.decision == "BLOCKED" else 0
        match_decision = decision.decision == expected_decision
        match_exit = actual_exit == expected_exit
        if match_decision and match_exit:
            print(
                f"  [PASS] {label}: decision={decision.decision} exit={actual_exit}"
            )
        else:
            print(
                f"  [FAIL] {label}: expected decision={expected_decision} "
                f"exit={expected_exit} actual decision={decision.decision} "
                f"exit={actual_exit}"
            )
            for r in results:
                print(f"         - {r.name}: {r.status} ({r.failure_reason})")
            all_ok = False

    print("=" * 60)
    if all_ok:
        print("self-test: OK")
        return 0
    print("self-test: FAIL")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="check-phase-gate",
        description="Phase gate 機械判定 (Foundation/Backend/UI/Polish/Release)",
    )
    parser.add_argument(
        "--phase",
        default=None,
        help=f"phase 名 ({'|'.join(VALID_PHASES)})",
    )
    parser.add_argument(
        "--profile",
        default=str(DEFAULT_PROFILE),
        help="profile Markdown path",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="JSON 出力 path (default: stdout)",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="2 fixture profile (all-pass / one-fail) で self-test",
    )

    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    if args.phase is None:
        print("error: --phase is required (or --self-test)", file=sys.stderr)
        return 2

    if args.phase not in VALID_PHASES:
        print(f"unknown phase: {args.phase}", file=sys.stderr)
        return 2

    profile_path = Path(args.profile)
    if not profile_path.is_absolute():
        profile_path = (Path.cwd() / profile_path).resolve()

    output_path: Path | None = None
    if args.output:
        op = Path(args.output)
        output_path = op if op.is_absolute() else (Path.cwd() / op).resolve()

    return run_phase_check(args.phase, profile_path, output_path)


if __name__ == "__main__":
    sys.exit(main())
