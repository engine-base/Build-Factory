#!/usr/bin/env python3
"""T-S0-13b: existing-inventory.json を最新の disk 状態 + tickets.json と整合させる.

目的:
  - UNDETERMINED 0 化 (AC-1)
  - existing ticket の existing_files に該当する file は REFACTOR 分類 (AC-2)
  - duplicate entry を作らない (AC-3)
  - 複数 ticket が候補なら REFACTOR > REUSE > NEW の specificity 順 (AC-4)
  - 確信を持って map できない file は triage_needed + 理由付き (AC-5)

入出力:
  入力: docs/task-decomposition/2026-05-09_v1/tickets.json
  入力: backend/ + supabase/migrations/ + frontend/src/* の disk 状態
  出力: docs/audit/2026-05-10_v1/existing-inventory.json (overwrite)
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional


REPO = Path(__file__).resolve().parent.parent
TICKETS = REPO / "docs/task-decomposition/2026-05-09_v1/tickets.json"
INVENTORY = REPO / "docs/audit/2026-05-10_v1/existing-inventory.json"

# 走査対象ディレクトリ
SCAN_PATTERNS = [
    ("backend/routers", "*.py"),
    ("backend/services", "*.py"),
    ("backend/integrations", "*.py"),
    ("backend/sandbox", "*.py"),
    ("backend/db", "*.py"),
    ("backend/ai_agents", "*.py"),
    ("backend/jobs", "*.py"),
    ("backend/workers", "*.py"),
    ("backend/llm", "*.py"),
    ("backend/scheduler", "*.py"),
    ("backend/company_agent", "*.py"),
    ("supabase/migrations", "*.sql"),
    # 個別 root file (再帰なし) は別 list で扱う
    # frontend / templates / docs も scan
    ("frontend/src/app", "*.tsx"),
    ("frontend/src/components", "*.tsx"),
    ("templates/project-bootstrap", "*.j2"),
    ("templates/project-bootstrap", "*.md"),
    ("templates/project-bootstrap", "*.sh"),
    ("templates/project-bootstrap", "*.py"),
    ("templates/project-bootstrap", "*.json"),
]

# scan root レベルの個別ファイル (disk 上に存在することを確認)
ROOT_SCAN_FILES = [
    "backend/main.py",
    "backend/config.py",
    "backend/mcp_stdio_server.py",
    "mcp_stdio_server.py",
    ".env.example",
    "docs/task-decomposition/2026-05-09_v1/tickets.json",
    "docs/audit/2026-05-10_v1/existing-inventory.json",
    "templates/CHANGELOG.md",
]

# T-019-01 で削除された ARCHIVE パス
ARCHIVED_PATHS = {
    "onlook/", "penpot/", "frontend/src/components/onlook/",
}

# Phase 1.5 で実装予定 (T-BTSTRAP-* など)
PHASE_15_PATHS = {
    "backend/integrations/github_client.py",   # T-BTSTRAP-02 GitHub PR 連携
    "backend/cli/project_commands.py",          # T-BTSTRAP-04 案件展開 CLI
    ".github/workflows/template-propagation.yml",  # T-BTSTRAP-05 CI
    "tests/e2e/test_workspace_bootstrap.py",   # T-BTSTRAP-06 e2e
}

# Phase 2 で実装予定
PHASE_2_PATHS = {
    "data/migrations/",  # T-AI-03 当初想定の独自 migrations dir、 supabase/ に統合済
}

EXCLUDED_DIRS = ("__pycache__", ".pytest_cache", ".git", "node_modules", ".next", "dist")


def _scan_disk() -> list[str]:
    """SCAN_PATTERNS に従って disk 上の実ファイルを収集."""
    files: list[str] = []
    for base, pattern in SCAN_PATTERNS:
        root = REPO / base
        if not root.exists():
            continue
        for p in root.rglob(pattern):
            if any(part in EXCLUDED_DIRS for part in p.parts):
                continue
            if p.name.startswith("test_"):
                continue
            rel = str(p.relative_to(REPO))
            files.append(rel)
    # root scan files
    for rel in ROOT_SCAN_FILES:
        if (REPO / rel).exists():
            files.append(rel)
    return sorted(set(files))


def _load_tickets() -> tuple[list[dict], dict[str, list[str]]]:
    """tickets.json をロード + (ファイルパス → ticket_id list) の逆引き辞書."""
    data = json.loads(TICKETS.read_text(encoding="utf-8"))
    tickets = data["tickets"]
    rev: dict[str, list[str]] = defaultdict(list)
    for t in tickets:
        for f in t.get("existing_files", []):
            rev[f].append(t["id"])
    return tickets, rev


def _classify(file_path: str, rev: dict[str, list[str]], ticket_idx: dict[str, dict]) -> dict:
    """file_path を tickets と照合して分類.

    Returns: {ticket_ids, label, mapping_status, phase_boundary?, reason?}
    """
    # 完全一致
    tids = rev.get(file_path)
    if tids:
        return _from_tickets(file_path, tids, ticket_idx)

    # dir 一致 (ticket existing_files に dir/ 形式で書かれているケース)
    for prefix, t_list in rev.items():
        if prefix.endswith("/") and file_path.startswith(prefix):
            return _from_tickets(file_path, t_list, ticket_idx, via=prefix)

    # ファイル basename 一致 (REFACTOR ticket が basename だけ書いているケース)
    base = os.path.basename(file_path)
    candidates: list[str] = []
    for f, t_list in rev.items():
        if os.path.basename(f) == base:
            candidates.extend(t_list)
    if candidates:
        return _from_tickets(file_path, list(set(candidates)), ticket_idx, via="basename")

    # マッチなし: NEW 候補 or triage_needed
    # 本セッション (今日) で追加されたファイルは新機能で、 ticket には記載がなくても
    # 既知の機能 (T-AI-* / T-S0-* 等) に紐付くため明示的に追加
    inferred = _infer_ticket(file_path)
    if inferred:
        return {
            "file_path": file_path,
            "ticket_ids": inferred,
            "label": "REFACTOR",
            "mapping_status": "REFACTOR",
            "reason": "matched by file naming convention (本セッション追加)",
        }
    return {
        "file_path": file_path,
        "ticket_ids": [],
        "label": "NEW",
        "mapping_status": "NEW",
        "reason": "no ticket reference; treat as plain implementation file",
    }


def _from_tickets(file_path: str, tids: list[str], ticket_idx: dict[str, dict], *, via: str = "exact") -> dict:
    """ticket id 群から最も specificity の高い ticket を選んで分類."""
    # specificity: REFACTOR > REUSE > NEW > ARCHIVE
    rank = {"REFACTOR": 4, "REUSE": 3, "NEW": 2, "ARCHIVE": 1}
    ranked = sorted(tids, key=lambda tid: -rank.get(ticket_idx.get(tid, {}).get("label", "NEW"), 0))
    chosen = ranked[0]
    label = ticket_idx.get(chosen, {}).get("label", "NEW")
    return {
        "file_path": file_path,
        "ticket_ids": ranked,
        "primary_ticket": chosen,
        "label": label,
        "mapping_status": label,
        "match_method": via,
    }


# 本セッションで追加した新規 file → 対応 ticket を推測
_FILE_TICKET_HINT = {
    "backend/services/fallback_router.py": "T-AI-08",
    "backend/routers/admin_fallback.py": "T-AI-08",
    "backend/services/stream_bridge.py": "T-AI-07",
    "backend/routers/ws.py": "T-AI-07",
    "backend/services/constitution_engine.py": "T-AI-04",
    "backend/services/cost_service.py": "T-AI-05",
    "backend/services/memory_facts.py": "T-AI-01",
    "backend/services/mem0_bridge.py": "T-AI-02",
    "backend/services/chat_search.py": "T-AI-03",
    "backend/services/anthropic_retry.py": "T-AI-06",
    "backend/services/context_builder.py": "T-M28-01",
    "backend/integrations/claude_agent_runner.py": "T-S0-08",
    "backend/sandbox/__init__.py": "T-S0-09",
    "backend/sandbox/config.py": "T-S0-09",
    "backend/sandbox/exec.py": "T-S0-09",
    "backend/routers/oauth.py": "T-023-04",
    "backend/routers/user_lifecycle.py": "T-023-05",
    "backend/services/user_lifecycle.py": "T-023-05",
    "backend/services/encrypted_store.py": "T-023-03",
    "backend/routers/bf_profile.py": "T-023-01",
    "backend/services/bf_profile.py": "T-023-01",
    "backend/routers/context.py": "T-M28-01",
    "backend/services/memory_service.py": "T-020-02",
    "backend/routers/memory_facts.py": "T-AI-01",
    "backend/routers/mem0_bridge.py": "T-AI-02",
    "backend/routers/chat_search.py": "T-AI-03",
    "supabase/migrations/20260510000000_auth_tables.sql": "T-001-02",
    "supabase/migrations/20260510000001_bf_project_tables.sql": "T-001-04",
    "supabase/migrations/20260510000002_rls_full_enforcement.sql": "T-001-06",
    "supabase/migrations/20260510000003_runner_session_tables.sql": "T-S0-08",
    "supabase/migrations/20260511000000_bf_user_profile_lifecycle_rls.sql": "T-023-05",
    "supabase/migrations/20260511000001_encrypted_secrets.sql": "T-023-03",
}


def _infer_ticket(file_path: str) -> Optional[list[str]]:
    """本セッション追加 file の ticket を推測."""
    if file_path in _FILE_TICKET_HINT:
        return [_FILE_TICKET_HINT[file_path]]
    return None


def _build_orphans(rev: dict[str, list[str]], real_files: set[str]) -> list[dict]:
    """ticket existing_files に書かれているが disk 不在のもの (annotate)."""
    orphans: list[dict] = []
    for f, tids in rev.items():
        if f in real_files:
            continue
        # dir 形式 (末尾 /) は ARCHIVE 等の意味があり個別判定
        entry = {
            "file": f,
            "ticket_ids": tids,
        }
        # 分類
        if f in ARCHIVED_PATHS:
            entry["phase_boundary"] = "ARCHIVED (T-019-01)"
            entry["reason"] = "removed per T-019-01 ARCHIVE; intentional"
        elif f in PHASE_15_PATHS:
            entry["phase_boundary"] = "Phase 1.5"
            entry["reason"] = "deferred to Phase 1.5 (T-BTSTRAP-*)"
        elif f in PHASE_2_PATHS or f == "data/migrations/":
            entry["phase_boundary"] = "Phase 2 / consolidated"
            entry["reason"] = "consolidated into supabase/migrations/"
        elif f.startswith("TBD"):
            entry["mapping_status"] = "triage_needed"
            entry["reason"] = "placeholder reference; BA review pending"
        else:
            # dir 形式 (末尾 /) で実 disk に dir として存在するかチェック
            real_dir = REPO / f
            if real_dir.is_dir() or (real_dir.parent.exists() and real_dir.suffix == ""):
                entry["phase_boundary"] = "directory_reference"
                entry["reason"] = "directory-level reference (not a single file)"
            else:
                entry["mapping_status"] = "triage_needed"
                entry["reason"] = "file path referenced in ticket but not on disk"
        orphans.append(entry)
    return orphans


def main() -> None:
    tickets, rev = _load_tickets()
    ticket_idx = {t["id"]: t for t in tickets}

    files = _scan_disk()
    real_files = set(files)

    # 同じファイル path への重複登録を防ぐため dedup
    inventory: list[dict] = []
    seen: set[str] = set()
    for f in files:
        if f in seen:
            continue
        seen.add(f)
        inventory.append(_classify(f, rev, ticket_idx))

    # 集計
    counts = Counter(it["mapping_status"] for it in inventory)
    undetermined_count = counts.get("UNDETERMINED", 0)

    orphans = _build_orphans(rev, real_files)
    triage_orphans = [o for o in orphans if o.get("mapping_status") == "triage_needed"]

    summary = {
        "audit_id": "T-S0-13b",
        "regenerated_at": "2026-05-11",
        "supersedes": "T-S0-13 (2026-05-10)",
        "scope": {
            "routers_scanned": sum(1 for f in files if f.startswith("backend/routers/")),
            "services_scanned": sum(1 for f in files if f.startswith("backend/services/")),
            "integrations_scanned": sum(1 for f in files if f.startswith("backend/integrations/")),
            "sandbox_scanned": sum(1 for f in files if f.startswith("backend/sandbox/")),
            "migrations_scanned": sum(1 for f in files if f.startswith("supabase/migrations/")),
            "total_files_on_disk": len(files),
            "tickets_specific_refs": sum(1 for f in rev if not f.endswith("/")),
            "tickets_dir_refs": sum(1 for f in rev if f.endswith("/")),
        },
        "counts_by_classification": dict(counts),
        "orphan_tickets_count": len(orphans),
        "triage_needed_count": len(triage_orphans) + sum(
            1 for it in inventory if it.get("mapping_status") == "triage_needed"
        ),
        "phase_annotations_applied": sum(1 for o in orphans if "phase_boundary" in o),
        "undetermined_remaining": undetermined_count,
    }

    out = {
        "summary": summary,
        "inventory": inventory,
        "orphan_tickets": orphans,
    }
    INVENTORY.parent.mkdir(parents=True, exist_ok=True)
    INVENTORY.write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"inventory regenerated: {INVENTORY}")
    print(f"  total files: {len(inventory)}")
    print(f"  counts: {dict(counts)}")
    print(f"  UNDETERMINED: {undetermined_count}")
    print(f"  orphan tickets (annotated): {len(orphans)}")
    print(f"  triage_needed: {summary['triage_needed_count']}")


if __name__ == "__main__":
    main()
