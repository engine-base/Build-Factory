#!/usr/bin/env python3
"""T-S0-13b: UNDETERMINED 64 + Orphan 6 のチケット紐付けクリーンアップ

high-confidence マッピング (curated): 各 UNDETERMINED ファイルを既存の REFACTOR
チケットの existing_files に追加。マッピングできないものは triage_needed として
オーディット出力に明示する (silently REUSE 化しない: ADR-011)。

Phase boundary 注釈:
  - Phase 1.5: GrapesJS 統合に伴い REFACTOR or 削除されるもの
  - Phase 2  : 後フェーズで再評価するもの

Orphan tickets (listed file 不在): 該当チケットの existing_files から削除する
                                    か、NEW なら output_file に残す
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TICKETS = ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"

# ────────────────────────────────────────────────────────────────────
# Curated mappings (file → list of ticket IDs that should claim this file)
# ────────────────────────────────────────────────────────────────────
MAPPINGS: dict[str, list[str]] = {
    # ── Routers ──────────────────────────────────────────
    "backend/routers/ai_system.py":         ["T-022-03"],   # AI 社員 (staff/employees) admin
    "backend/routers/artifacts.py":         ["T-003-05"],   # artifact 保存 + AC 検証
    "backend/routers/chat.py":              ["T-M30-01"],   # ChatThread/ChatMessage CRUD
    "backend/routers/chatwork.py":          ["T-014-01"],   # 外部統合 (Slack 系列で claim)
    "backend/routers/dashboard.py":         ["T-008-01"],
    "backend/routers/design_pipeline.py":   ["T-005b-02"],  # ui-mockup スキル統合
    "backend/routers/documents.py":         ["T-016-01"],   # obsidian docs
    "backend/routers/estimate.py":          ["T-005-01"],   # hearing 系 (estimate AI)
    "backend/routers/knowledge_actions.py": ["T-024-02"],   # knowledge search/action
    "backend/routers/llm.py":               ["T-020-02"],
    "backend/routers/llm_providers.py":     ["T-020-02"],
    "backend/routers/pricing_design.py":    ["T-005-01"],   # 要件 → 価格設計 (hearing 系)
    "backend/routers/proposal.py":          ["T-005-01"],   # hearing 系 (proposal output)
    "backend/routers/records.py":           ["T-016-01"],   # obsidian records
    "backend/routers/references.py":        ["T-024-02"],   # knowledge references
    "backend/routers/secretary.py":         ["T-003-02"],   # AI 社員召喚 (secretary persona)
    "backend/routers/secretary_stream.py":  ["T-003-02"],   # streaming endpoint
    "backend/routers/skill_creator.py":     ["T-002-01"],   # skill 管理
    "backend/routers/slot_admin.py":        ["T-005-02"],   # hearing slot 管理
    "backend/routers/staff.py":             ["T-022-03"],   # AI 社員 CRUD
    "backend/routers/template_builder.py":  ["T-015-01"],   # 共通テンプレ
    "backend/routers/uploads.py":           ["T-016-01"],   # ファイルアップロード→ obsidian
    "backend/routers/workflows.py":         ["T-010c-01"],  # asyncio queue / workflows

    # ── Services ─────────────────────────────────────────
    "backend/services/account_service.py":          ["T-004-01"],
    "backend/services/account_settings_service.py": ["T-004-01"],
    "backend/services/auth_middleware.py":          ["T-021-03", "T-S0-09"],
    "backend/services/briefing_service.py":         ["T-005-01"],   # hearing briefing
    "backend/services/catchup_service.py":          ["T-008-01"],   # dashboard catchup
    "backend/services/conversation_memory.py":      ["T-M30-03"],
    "backend/services/delegation_service.py":       ["T-003-02"],
    "backend/services/design_pipeline.py":          ["T-005b-02"],
    "backend/services/document_ingest_service.py":  ["T-016-01"],
    "backend/services/document_service.py":         ["T-016-01"],
    "backend/services/estimate_service.py":         ["T-005-01"],
    "backend/services/inbox_service.py":            ["T-014-01"],   # mail/slack inbox
    "backend/services/knowledge_curator.py":        ["T-M28-05"],
    "backend/services/knowledge_transfer.py":       ["T-M28-05"],
    "backend/services/obsidian_vault_sync.py":      ["T-M30-04"],   # 長期 layer 統合
    "backend/services/orchestrator_graph.py":       ["T-010b-01"],  # claude-agent-sdk 統合
    "backend/services/pricing_design_service.py":   ["T-005-01"],
    "backend/services/proposal_service.py":         ["T-005-01"],
    "backend/services/rag_context.py":              ["T-M28-05"],
    "backend/services/sales_service.py":            ["T-008-01"],
    "backend/services/scoped_knowledge.py":         ["T-024-02"],
    "backend/services/secretary_chat.py":           ["T-003-02"],
    "backend/services/skill_detector.py":           ["T-M27-02"],
    "backend/services/skill_manager.py":            ["T-002-02"],
    "backend/services/slack_history.py":            ["T-014-01"],
    "backend/services/supabase_client.py":          ["T-S0-08"],
    "backend/services/template_builder_service.py": ["T-015-01"],
    "backend/services/template_render_service.py":  ["T-015-01"],
    "backend/services/upload_service.py":           ["T-016-01"],
    "backend/services/workflow_service.py":         ["T-010c-01"],

    # ── Migrations ───────────────────────────────────────
    "supabase/migrations/20260501220000_initial_schema.sql":      ["T-001-02"],
    "supabase/migrations/20260501220200_knowledge_scope.sql":     ["T-024-02"],
    "supabase/migrations/20260501220300_rls_skeleton.sql":        ["T-001-02"],
    "supabase/migrations/20260501230000_design_frames.sql":       ["T-005b-01"],
    "supabase/migrations/20260501230100_design_mockup_content.sql": ["T-005b-01"],
    "supabase/migrations/20260502000000_design_mocks.sql":        ["T-005b-01"],
}

# Files that legitimately have no Phase 1 ticket and should be annotated.
# (browser-use 系は Phase 2 で再評価、penpot は Phase 1.5 で REFACTOR)
PHASE_BOUNDARIES: dict[str, dict[str, str]] = {
    "backend/routers/browser_use.py": {
        "phase_boundary": "Phase 2",
        "phase_action": "browser-use の Phase 1 必要性を再評価 (現状 UNDETERMINED)",
    },
    "backend/services/browser_use_service.py": {
        "phase_boundary": "Phase 2",
        "phase_action": "browser-use の Phase 1 必要性を再評価 (現状 UNDETERMINED)",
    },
    "backend/services/browser_queue.py": {
        "phase_boundary": "Phase 2",
        "phase_action": "browser-use キューイング、Phase 1 では不使用",
    },
    "backend/services/penpot_client.py": {
        "phase_boundary": "Phase 1.5",
        "phase_action": "S-3 GrapesJS 統合に伴い REFACTOR (Penpot 依存除去)",
    },
    "backend/services/tool_ui_postprocess.py": {
        "phase_boundary": "Phase 1.5",
        "phase_action": "tool UI / postprocess は Phase 1.5 でレビュー後にチケット化",
    },
}

# Orphan tickets (listed file が disk に不在) の処置:
# - REFACTOR で listed しているが file がない場合: ticket は NEW 相当に再分類が必要
# - NEW で listed しているが file がない場合: 想定どおり (将来作成)、何もしない
# 今回は既存ファイルに置き換え可能なものだけ補正する。
ORPHAN_FIXES: dict[str, dict] = {
    # T-001-02 lists backend/routers/auth.py (不在) — 認証は別ファイルに統合済み
    # 'backend/services/auth_middleware.py' をすでに上で T-001-02 ではなく
    # T-021-03/T-S0-09 にマップ済み。orphan は明示削除。
    "T-001-02": {"remove": ["backend/routers/auth.py"]},
    # T-020-02 lists backend/services/memory_service.py (不在) — conversation_memory に統合済み
    "T-020-02": {"remove": ["backend/services/memory_service.py"],
                 "add": ["backend/services/conversation_memory.py"]},
    # T-BTSTRAP-* は将来 NEW なので何もしない
}


def main() -> int:
    with TICKETS.open() as f:
        d = json.load(f)

    by_id = {t["id"]: t for t in d["tickets"]}

    # 1. Apply mappings: add file path to existing_files of matching tickets
    added = 0
    skipped_dup = 0
    for path, tids in MAPPINGS.items():
        for tid in tids:
            t = by_id.get(tid)
            if t is None:
                print(f"  [SKIP] mapping target ticket not found: {tid}")
                continue
            ef = t.setdefault("existing_files", []) or []
            if path in ef:
                skipped_dup += 1
                continue
            ef.append(path)
            t["existing_files"] = ef
            added += 1

    # 2. Apply orphan fixes
    fixed = 0
    for tid, ops in ORPHAN_FIXES.items():
        t = by_id.get(tid)
        if t is None:
            continue
        ef = t.get("existing_files") or []
        for r in ops.get("remove", []):
            if r in ef:
                ef.remove(r)
                fixed += 1
        for a in ops.get("add", []):
            if a not in ef:
                ef.append(a)
                fixed += 1
        t["existing_files"] = ef

    # 3. Save tickets.json
    with TICKETS.open("w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)

    print(f"OK: applied {added} mappings, {fixed} orphan fixes (skipped {skipped_dup} duplicates)")
    print(f"Phase boundary annotations: {len(PHASE_BOUNDARIES)} files (defined in audit script)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
