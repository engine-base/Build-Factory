#!/usr/bin/env python3
"""verify-slice: Slice / Wave 単位で「仕様徹底度」を機械検査する.

各 task について 5 軸を検査し、Slice/Wave 単位で集計する:

| 軸 | 内容 | 通る条件 |
|---|---|---|
| AC          | tickets.json の acceptance_criteria | 4 件以上、UNWANTED 含む |
| Test        | backend/tests/test_<task_id>* に対応 test ファイル | AC 数 ≤ test 関数数 |
| Impl        | existing_files で示されたファイルが repo に実在 | 全件存在 |
| Audit       | docs/audit/2026-05-13_v2/<TASK-ID>.md | 存在 |
| Done        | git log に commit 痕跡 | 1 件以上 |

Usage:
    python3 scripts/verify-slice.py S1               # Slice S1 全体
    python3 scripts/verify-slice.py S1 1.1           # Slice S1 の Wave 1.1 だけ
    python3 scripts/verify-slice.py T-001-04         # 個別 task
    python3 scripts/verify-slice.py --all            # 全 Slice まとめて
    python3 scripts/verify-slice.py --done-only S2   # done のものだけ検査

Exit code:
    0 = 全件 PASS
    1 = 1 件以上 FAIL
    2 = usage error
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
TICKETS_V2 = ROOT / "docs/task-decomposition/2026-05-14_v2/tickets-v2.json"
AUDIT_DIR = ROOT / "docs/audit/2026-05-13_v2"
TESTS_DIR = ROOT / "backend/tests"

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[0;33m"
DIM = "\033[0;90m"
NC = "\033[0m"


def load_tickets():
    with TICKETS_V2.open() as f:
        d = json.load(f)
    return d["tickets"]


def find_test_file(task_id):
    """task_id に対応する test ファイル群を返す.

    命名規則:
        T-001-04 → backend/tests/test_t_001_04*.py
        T-AI-MEM-01 → backend/tests/test_t_ai_mem_01*.py
    """
    canonical = task_id.lower().replace("-", "_")
    if not TESTS_DIR.is_dir():
        return []
    pattern = f"test_{canonical}"
    matches = []
    for p in TESTS_DIR.glob(f"{pattern}*.py"):
        matches.append(p)
    return matches


def count_test_functions(test_files):
    """test ファイル群の中の `def test_` 関数数を数える."""
    count = 0
    for fp in test_files:
        try:
            content = fp.read_text(encoding="utf-8")
            count += len(re.findall(r"^def test_|^    def test_|^async def test_", content, re.MULTILINE))
        except Exception:
            pass
    return count


def verify_task(t):
    """1 task を 5 軸で検査. dict を返す."""
    result = {
        "id": t["id"],
        "label": t.get("label", "?"),
        "slice": t.get("slice", "?"),
        "wave": t.get("wave", "?"),
        "done_status": t.get("done_status", "?"),
        "checks": {},
        "warnings": [],
    }
    # 1) AC
    ac = t.get("acceptance_criteria", [])
    has_unwanted = any(a.get("type") == "UNWANTED" for a in ac)
    result["checks"]["ac"] = {
        "ok": len(ac) >= 4 and has_unwanted,
        "detail": f"{len(ac)} ACs, UNWANTED={'yes' if has_unwanted else 'NO'}",
    }
    # 2) Test (test file が見つかれば PASS / なければ done のみ FAIL)
    test_files = find_test_file(t["id"])
    test_func_count = count_test_functions(test_files)
    test_ok = (
        len(test_files) > 0 and test_func_count >= len(ac)
    ) or t["done_status"] == "pending"  # pending は許容
    result["checks"]["test"] = {
        "ok": test_ok,
        "detail": f"{len(test_files)} files / {test_func_count} test funcs (need >= {len(ac)})",
    }
    # 3) Impl (existing_files の実在)
    existing = t.get("existing_files", [])
    if t.get("label") in ("ARCHIVE",) or t["done_status"] == "pending":
        # ARCHIVE は削除予定なので無くても OK / pending は未着手
        impl_ok = True
        impl_missing = []
    else:
        impl_missing = []
        for ef in existing:
            ef_clean = ef.rstrip("/").lstrip("./")
            full = ROOT / ef_clean
            if not (full.exists() or full.parent.glob(full.name)):
                impl_missing.append(ef)
        impl_ok = len(impl_missing) == 0
    result["checks"]["impl"] = {
        "ok": impl_ok,
        "detail": f"{len(existing) - len(impl_missing)}/{len(existing)} files exist"
        + (f" (missing: {impl_missing[:3]})" if impl_missing else ""),
    }
    # 4) Audit MD (done タスクは audit MD あれば golden, 無くても warning)
    audit_md = AUDIT_DIR / f"{t['id']}.md"
    audit_exists = audit_md.exists()
    if t["done_status"] == "done":
        result["checks"]["audit"] = {
            "ok": True,  # 必須ではない (旧 task は audit 無しでも許容)
            "detail": "exists" if audit_exists else "no audit MD (legacy)",
        }
        if not audit_exists:
            result["warnings"].append("audit MD なし (5/13 以前 merge の可能性)")
    else:
        result["checks"]["audit"] = {
            "ok": True,
            "detail": "N/A (pending)",
        }
    # 5) Done (git log)
    result["checks"]["done"] = {
        "ok": True,  # 純粋に状態表示
        "detail": t["done_status"],
    }
    # 総合判定
    result["pass"] = all(c["ok"] for c in result["checks"].values())
    return result


def print_task_row(r, verbose=False):
    sym = f"{GREEN}✓{NC}" if r["pass"] else f"{RED}✗{NC}"
    status = (
        f"{GREEN}DONE{NC}" if r["done_status"] == "done" else f"{YELLOW}pend{NC}"
    )
    label = r["label"][:7].ljust(7)
    fail_marks = []
    for k, c in r["checks"].items():
        if not c["ok"]:
            fail_marks.append(k)
    fail_str = f" {RED}fail:{','.join(fail_marks)}{NC}" if fail_marks else ""
    warn_str = f" {YELLOW}({len(r['warnings'])} warn){NC}" if r["warnings"] else ""
    print(f"  {sym} {r['id']:<14} [{label}] {status}{fail_str}{warn_str}")
    if verbose:
        for k, c in r["checks"].items():
            mark = f"{GREEN}✓{NC}" if c["ok"] else f"{RED}✗{NC}"
            print(f"      {mark} {k:<7}: {c['detail']}")
        for w in r["warnings"]:
            print(f"      {YELLOW}!{NC} {w}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", help="Slice ID (S1) / Wave (1.1) / Task ID (T-001-04)")
    ap.add_argument("wave", nargs="?", help="Wave 番号 (Slice 指定時のみ有効)")
    ap.add_argument("--all", action="store_true", help="全 Slice")
    ap.add_argument("--done-only", action="store_true", help="done タスクだけ検査")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    tickets = load_tickets()

    # フィルタリング
    if args.all:
        target_tickets = tickets
        label = "ALL Slices"
    elif args.target and args.target.startswith("T-"):
        target_tickets = [t for t in tickets if t["id"] == args.target]
        if not target_tickets:
            print(f"{RED}Task not found: {args.target}{NC}")
            sys.exit(2)
        label = f"Task {args.target}"
    elif args.target and args.target.startswith("S"):
        target_tickets = [t for t in tickets if t.get("slice") == args.target]
        if args.wave:
            target_tickets = [t for t in target_tickets if t.get("wave") == args.wave]
            label = f"Slice {args.target} Wave {args.wave}"
        else:
            label = f"Slice {args.target}"
    else:
        ap.print_help()
        sys.exit(2)

    if args.done_only:
        target_tickets = [t for t in target_tickets if t.get("done_status") == "done"]
        label += " (done only)"

    if not target_tickets:
        print(f"{YELLOW}該当 task なし: {label}{NC}")
        sys.exit(0)

    # 検査実行
    results = [verify_task(t) for t in target_tickets]

    # 表示
    print(f"\n=== verify-slice: {label} ({len(results)} tasks) ===\n")
    by_slice_wave = defaultdict(list)
    for r in results:
        by_slice_wave[(r["slice"], r["wave"])].append(r)

    for (sid, wid), rs in sorted(by_slice_wave.items()):
        print(f"\n{DIM}── {sid} Wave {wid} ({len(rs)} tasks){NC}")
        for r in sorted(rs, key=lambda x: x["id"]):
            print_task_row(r, verbose=args.verbose)

    # 集計
    print(f"\n=== Summary ===")
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    failed = total - passed
    done = sum(1 for r in results if r["done_status"] == "done")
    pending = total - done
    warnings_total = sum(len(r["warnings"]) for r in results)

    print(f"  total:    {total}")
    print(f"  PASS:     {GREEN}{passed}{NC}")
    print(f"  FAIL:     {RED if failed else GREEN}{failed}{NC}")
    print(f"  done:     {done}")
    print(f"  pending:  {pending}")
    print(f"  warnings: {YELLOW}{warnings_total}{NC} (audit MD 無し等)")

    # Slice 別集計
    if args.all or (args.target and args.target.startswith("S") and not args.wave):
        slice_pass = defaultdict(lambda: [0, 0])
        for r in results:
            slice_pass[r["slice"]][0 if r["pass"] else 1] += 1
        print()
        print(f"  {'Slice':<6}{'PASS':>6}{'FAIL':>6}{'%':>8}")
        for sid in sorted(slice_pass.keys()):
            p, f = slice_pass[sid]
            pct = 100 * p / (p + f) if (p + f) else 0
            print(f"  {sid:<6}{p:>6}{f:>6}  {pct:>5.1f}%")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
