#!/usr/bin/env python3
"""Wave 起動前の file-level mutex 検証スクリプト (T-FOUNDATION-03).

Wave 内の全 task の `work_package_boundary` を読み、以下 3 種の violation を検出する:

  1. mutex_violation       : 2 つ以上の task が同 file を `editable` に宣言
  2. forbidden_violation   : ある task の `editable` が、別 task の `forbidden` に該当
  3. shared_misuse         : `shared_no_concurrent_edit` 宣言された file を、
                             2 つ以上の task が `editable` に持つ

検出結果は stdout に JSON で出力する。`--strict` を付けると violation が 1 件でも
あれば exit 1 を返す (CI gate 用)。tickets.json schema が壊れている場合は
exit 2 + `invalid tickets schema` を stderr に出して停止する。

Usage:
  python3 scripts/check-wave-mutex.py --wave 0a
  python3 scripts/check-wave-mutex.py --wave 0a \\
      --tickets docs/task-decomposition/2026-05-16_v3_phase0/tickets.json --strict
  python3 scripts/check-wave-mutex.py --self-test

外部依存なし (Python 3.13 標準ライブラリのみ / json + argparse + pathlib + typing).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
SELF_TEST_DIR = Path(__file__).resolve().parent / "tests" / "fixtures" / "wave-mutex"
DEFAULT_TICKETS_GLOB_DIR = ROOT / "docs" / "task-decomposition"

EXIT_OK = 0
EXIT_STRICT_VIOLATION = 1
EXIT_INVALID_SCHEMA = 2

REQUIRED_BOUNDARY_KEYS = ("editable", "shared_no_concurrent_edit", "readonly", "forbidden")


# -----------------------------------------------------------------------------
# Data classes
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Task:
    """tickets.json 1 entry を mutex 検証用に正規化したもの."""

    id: str
    wave: str
    editable: frozenset[str]
    shared_no_concurrent_edit: frozenset[str]
    readonly: frozenset[str]
    forbidden: frozenset[str]


def _empty_dict_list() -> list[dict[str, Any]]:
    return []


@dataclass
class Violations:
    """3 種 violation のコンテナ. stdout には JSON で dump する."""

    mutex_violation: list[dict[str, Any]] = field(default_factory=_empty_dict_list)
    forbidden_violation: list[dict[str, Any]] = field(default_factory=_empty_dict_list)
    shared_misuse: list[dict[str, Any]] = field(default_factory=_empty_dict_list)

    def total(self) -> int:
        return (
            len(self.mutex_violation)
            + len(self.forbidden_violation)
            + len(self.shared_misuse)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutex_violation": self.mutex_violation,
            "forbidden_violation": self.forbidden_violation,
            "shared_misuse": self.shared_misuse,
            "total_violations": self.total(),
        }


# -----------------------------------------------------------------------------
# Parsing
# -----------------------------------------------------------------------------


def _fail_schema(msg: str) -> "None":
    """invalid schema 検出時の共通 exit (exit 2)."""
    print(f"invalid tickets schema: {msg}", file=sys.stderr)
    sys.exit(EXIT_INVALID_SCHEMA)


def load_tickets(path: Path) -> list[dict[str, Any]]:
    """tickets.json を読んで `tasks` または `tickets` キーで list を返す.

    schema が壊れている場合は exit 2 で停止する.
    """
    if not path.is_file():
        _fail_schema(f"file not found: {path}")
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail_schema(f"JSON parse error in {path}: {exc}")
        return []  # unreachable (kept for type-checker)

    # 受け入れる schema 形:
    #   1) {"tasks": [...]}
    #   2) {"tickets": [...]}
    #   3) [...]  (素の list)
    raw_tasks_any: Any
    if isinstance(data, dict):
        data_dict = cast(dict[str, Any], data)
        if "tasks" in data_dict:
            raw_tasks_any = data_dict["tasks"]
        elif "tickets" in data_dict:
            raw_tasks_any = data_dict["tickets"]
        else:
            _fail_schema("top-level dict has neither 'tasks' nor 'tickets'")
            return []
    elif isinstance(data, list):
        raw_tasks_any = cast(list[Any], data)
    else:
        _fail_schema(f"top-level must be dict or list, got {type(data).__name__}")
        return []

    if not isinstance(raw_tasks_any, list):
        _fail_schema("'tasks'/'tickets' must be a list")
        return []

    raw_tasks: list[dict[str, Any]] = []
    raw_tasks_list = cast(list[Any], raw_tasks_any)
    for idx, entry in enumerate(raw_tasks_list):
        if not isinstance(entry, dict):
            _fail_schema(f"task[{idx}] is not an object")
            return []
        entry_dict = cast(dict[str, Any], entry)
        raw_tasks.append(entry_dict)

    return raw_tasks


def _coerce_str_list(value: Any, where: str) -> list[str]:
    """work_package_boundary 配下の 4 区分 list を str list に正規化."""
    if value is None:
        return []
    if not isinstance(value, list):
        _fail_schema(f"{where} must be a list, got {type(value).__name__}")
        return []
    value_list = cast(list[Any], value)
    out: list[str] = []
    for v in value_list:
        if not isinstance(v, str):
            _fail_schema(f"{where} entries must be string, got {type(v).__name__}")
            return []
        out.append(v)
    return out


def parse_task(raw: dict[str, Any], wave_filter: str) -> Task | None:
    """1 task entry を Task に変換. wave_filter に一致しなければ None."""
    tid = raw.get("id")
    if not isinstance(tid, str) or not tid:
        _fail_schema("task missing 'id' or 'id' not a non-empty string")
        return None

    wave = raw.get("wave")
    if wave is None:
        # wave 未指定 task は対象外
        return None
    if not isinstance(wave, str):
        _fail_schema(f"task {tid}: 'wave' must be a string")
        return None
    if wave != wave_filter:
        return None

    boundary_any: Any = raw.get("work_package_boundary")
    if boundary_any is None:
        # boundary 未宣言 task は (Foundation 着手前は普通) violation 対象外
        return Task(
            id=tid,
            wave=wave,
            editable=frozenset[str](),
            shared_no_concurrent_edit=frozenset[str](),
            readonly=frozenset[str](),
            forbidden=frozenset[str](),
        )
    if not isinstance(boundary_any, dict):
        _fail_schema(f"task {tid}: work_package_boundary must be an object")
        return None
    boundary = cast(dict[str, Any], boundary_any)

    for key in REQUIRED_BOUNDARY_KEYS:
        if key not in boundary:
            _fail_schema(f"task {tid}: work_package_boundary missing '{key}'")

    return Task(
        id=tid,
        wave=wave,
        editable=frozenset(
            _coerce_str_list(boundary.get("editable"), f"task {tid}.editable")
        ),
        shared_no_concurrent_edit=frozenset(
            _coerce_str_list(
                boundary.get("shared_no_concurrent_edit"),
                f"task {tid}.shared_no_concurrent_edit",
            )
        ),
        readonly=frozenset(
            _coerce_str_list(boundary.get("readonly"), f"task {tid}.readonly")
        ),
        forbidden=frozenset(
            _coerce_str_list(boundary.get("forbidden"), f"task {tid}.forbidden")
        ),
    )


# -----------------------------------------------------------------------------
# Mutex check
# -----------------------------------------------------------------------------


def detect_violations(tasks: list[Task]) -> Violations:
    """3 種 violation を検出して Violations に詰めて返す."""
    out = Violations()

    # 1) mutex_violation: editable file -> [task_id, ...]
    editable_owners: dict[str, list[str]] = defaultdict(list)
    for t in tasks:
        for f in t.editable:
            editable_owners[f].append(t.id)
    for file_path in sorted(editable_owners):
        owners = sorted(editable_owners[file_path])
        if len(owners) >= 2:
            out.mutex_violation.append({"file": file_path, "tasks": owners})

    # 2) forbidden_violation: 別 task の editable と forbidden の交差
    #    出力は deterministic にするため task ペアでソート.
    forbidden_index: dict[str, list[str]] = defaultdict(list)
    for t in tasks:
        for f in t.forbidden:
            forbidden_index[f].append(t.id)
    pair_violations: list[tuple[str, str, str]] = []
    for t in tasks:
        for f in t.editable:
            if f in forbidden_index:
                for owner in forbidden_index[f]:
                    if owner == t.id:
                        continue
                    pair_violations.append((f, t.id, owner))
    pair_violations.sort()
    for file_path, editing_task, forbidding_task in pair_violations:
        out.forbidden_violation.append(
            {
                "file": file_path,
                "editing_task": editing_task,
                "forbidding_task": forbidding_task,
            }
        )

    # 3) shared_misuse: shared_no_concurrent_edit 宣言 file が 2 task 以上の
    #    editable に登場 → 同時編集が走り得る. shared 宣言は対象 file につき
    #    どれか 1 task でもしていればチェック対象とみなす.
    shared_declared: set[str] = set()
    for t in tasks:
        shared_declared.update(t.shared_no_concurrent_edit)
    for file_path in sorted(shared_declared):
        owners = sorted(editable_owners.get(file_path, []))
        if len(owners) >= 2:
            out.shared_misuse.append({"file": file_path, "tasks": owners})

    return out


# -----------------------------------------------------------------------------
# Default tickets resolution
# -----------------------------------------------------------------------------


def resolve_default_tickets() -> Path | None:
    """docs/task-decomposition/*/tickets.json から最新の 1 件を返す.

    複数候補がある場合はディレクトリ名の lexical max (= 日付的に最新) を採用する.
    存在しない場合 None.
    """
    if not DEFAULT_TICKETS_GLOB_DIR.is_dir():
        return None
    candidates: list[Path] = []
    for child in DEFAULT_TICKETS_GLOB_DIR.iterdir():
        if not child.is_dir():
            continue
        candidate = child / "tickets.json"
        if candidate.is_file():
            candidates.append(candidate)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.parent.name)
    return candidates[-1]


# -----------------------------------------------------------------------------
# Main flow
# -----------------------------------------------------------------------------


def run_check(
    wave: str,
    tickets_path: Path,
    *,
    strict: bool,
    output_stream: Any = sys.stdout,
) -> int:
    """check を実行し、JSON を output_stream に dump して exit code を返す."""
    raw_tasks = load_tickets(tickets_path)
    tasks: list[Task] = []
    for entry in raw_tasks:
        t = parse_task(entry, wave_filter=wave)
        if t is not None:
            tasks.append(t)

    result: dict[str, Any]
    if not tasks:
        # 該当 task が 0 件 = warning + exit 0
        print(
            f"warning: no tasks found for wave='{wave}' in {tickets_path}",
            file=sys.stderr,
        )
        result = {
            "wave": wave,
            "tickets_path": str(tickets_path),
            "task_count": 0,
            "violations": Violations().to_dict(),
        }
        json.dump(result, output_stream, indent=2, sort_keys=True)
        output_stream.write("\n")
        return EXIT_OK

    violations = detect_violations(tasks)
    result = {
        "wave": wave,
        "tickets_path": str(tickets_path),
        "task_count": len(tasks),
        "task_ids": sorted(t.id for t in tasks),
        "violations": violations.to_dict(),
    }
    json.dump(result, output_stream, indent=2, sort_keys=True)
    output_stream.write("\n")

    if strict and violations.total() > 0:
        return EXIT_STRICT_VIOLATION
    return EXIT_OK


# -----------------------------------------------------------------------------
# Self-test
# -----------------------------------------------------------------------------


@dataclass
class SelfTestCase:
    fixture: str
    wave: str
    expected_mutex: int
    expected_forbidden: int
    expected_shared_misuse: int
    expected_strict_exit: int


_SELF_TEST_CASES: list[SelfTestCase] = [
    SelfTestCase(
        fixture="clean.json",
        wave="0a",
        expected_mutex=0,
        expected_forbidden=0,
        expected_shared_misuse=0,
        expected_strict_exit=EXIT_OK,
    ),
    SelfTestCase(
        fixture="conflict.json",
        wave="0a",
        expected_mutex=1,
        expected_forbidden=1,
        expected_shared_misuse=0,
        expected_strict_exit=EXIT_STRICT_VIOLATION,
    ),
    SelfTestCase(
        fixture="shared-misuse.json",
        wave="0a",
        expected_mutex=1,  # docs/shared-spec.md は editable 重複でもある
        expected_forbidden=0,
        expected_shared_misuse=1,
        expected_strict_exit=EXIT_STRICT_VIOLATION,
    ),
]


def run_self_test() -> int:
    """3 fixture を順に検証. 全て通れば 0, 1 件でも失敗で 1."""
    failures: list[str] = []
    for case in _SELF_TEST_CASES:
        fixture_path = SELF_TEST_DIR / case.fixture
        if not fixture_path.is_file():
            failures.append(f"[FAIL] fixture missing: {fixture_path}")
            continue

        raw_tasks = load_tickets(fixture_path)
        tasks: list[Task] = []
        for entry in raw_tasks:
            t = parse_task(entry, wave_filter=case.wave)
            if t is not None:
                tasks.append(t)
        violations = detect_violations(tasks)

        ok = True
        errors: list[str] = []
        if len(violations.mutex_violation) != case.expected_mutex:
            ok = False
            errors.append(
                f"mutex_violation: expected {case.expected_mutex}, "
                f"got {len(violations.mutex_violation)}"
            )
        if len(violations.forbidden_violation) != case.expected_forbidden:
            ok = False
            errors.append(
                f"forbidden_violation: expected {case.expected_forbidden}, "
                f"got {len(violations.forbidden_violation)}"
            )
        if len(violations.shared_misuse) != case.expected_shared_misuse:
            ok = False
            errors.append(
                f"shared_misuse: expected {case.expected_shared_misuse}, "
                f"got {len(violations.shared_misuse)}"
            )
        # strict exit code 検証 (= violations.total() > 0 で 1, else 0)
        strict_exit = (
            EXIT_STRICT_VIOLATION if violations.total() > 0 else EXIT_OK
        )
        if strict_exit != case.expected_strict_exit:
            ok = False
            errors.append(
                f"strict_exit: expected {case.expected_strict_exit}, got {strict_exit}"
            )

        if ok:
            print(f"[PASS] {case.fixture} (wave={case.wave})")
        else:
            print(f"[FAIL] {case.fixture} (wave={case.wave})")
            for e in errors:
                print(f"        - {e}")
            failures.append(case.fixture)

    print(
        f"self-test summary: {len(_SELF_TEST_CASES) - len(failures)} passed / "
        f"{len(failures)} failed ({len(_SELF_TEST_CASES)} cases)"
    )
    return 0 if not failures else 1


# -----------------------------------------------------------------------------
# Argparse
# -----------------------------------------------------------------------------


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="check-wave-mutex.py",
        description="Wave 起動前の file-level mutex 検証 (T-FOUNDATION-03).",
    )
    p.add_argument(
        "--wave",
        help="検証対象の wave_id (例: 0a). --self-test 時は不要.",
    )
    p.add_argument(
        "--tickets",
        type=Path,
        help=(
            "tickets.json path. 省略時は docs/task-decomposition/*/tickets.json "
            "の最新を自動選択."
        ),
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="violation が 1 件でもあれば exit 1.",
    )
    p.add_argument(
        "--self-test",
        action="store_true",
        help="3 fixture (clean/conflict/shared-misuse) を実行して期待値検証.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)

    if args.self_test:
        return run_self_test()

    if not args.wave:
        print("error: --wave is required (unless --self-test)", file=sys.stderr)
        return EXIT_INVALID_SCHEMA

    tickets_path: Path
    if args.tickets is not None:
        tickets_path = args.tickets
    else:
        resolved = resolve_default_tickets()
        if resolved is None:
            print(
                "error: --tickets not given and no docs/task-decomposition/*/tickets.json found",
                file=sys.stderr,
            )
            return EXIT_INVALID_SCHEMA
        tickets_path = resolved

    return run_check(args.wave, tickets_path, strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
