#!/usr/bin/env python3
"""tickets-v2 generator: 既存 tickets.json を **無傷で** 拡張する.

入力:
    docs/task-decomposition/2026-05-09_v1/tickets.json (187 task, 既存仕様)

出力:
    docs/task-decomposition/2026-05-14_v2/tickets-v2.json
        各 task に追加するフィールド:
          - slice          : "S1".."S8"  (8 Slice 構造)
          - wave           : "1.1", "1.2", ...  (Slice 内の波)
          - parallel_group : "P1.2-A", "P1.2-B", ...  (同 group は並列実行可)
          - dogfood_value  : "1 行で書く完了時の体感価値"
          - unlocks        : [next-task IDs]  (deps の逆向き)
          - done_status    : "done" | "pending"  (git log 検出ベース)

設計原則:
    - 既存フィールド (id, title, sprint, feature, AC, deps, etc.) は **1 文字も触らない**
    - 仕様 (M-1〜M-30 / ER / mocks) は完全に保持
    - audit MD と git log は履歴尊重して「done_status」だけ追加

Slice 設計 (vertical slice / dogfood-first):
    S1  認証 + Workspace + テナント階層
    S2  AI 社員 + Chat + Memory (3 tier)
    S3  ヒアリング → 要件定義
    S4  アーキ設計 → 機能分解 → タスク分解
    S5  Kanban + DAG + Phase 管理
    S6  MCP + Constitution + Reviewer
    S7  Swarm 並列実行 + Worktree (= 靴を履く)
    S8  GitHub/Slack/Obsidian + 観測 + 監査 + 配信
"""
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC = ROOT / "docs/task-decomposition/2026-05-09_v1/tickets.json"
DST_DIR = ROOT / "docs/task-decomposition/2026-05-14_v2"
DST_JSON = DST_DIR / "tickets-v2.json"

# ────────────────────────────────────────────────────────────────────
# Slice 定義 — feature ID と task ID prefix をベースに 8 Slice に分類
# ────────────────────────────────────────────────────────────────────
SLICE_DEFINITIONS = {
    "S1": {
        "name": "認証 + Workspace + テナント階層",
        "dogfood": "ログインして workspace に入れる / 招待 / 権限 / OAuth で外部 API キー登録",
        "feature_ids": ["F-002", "F-004", "F-021", "F-023"],
        "extra_task_ids": [
            "T-001-01", "T-001-01b", "T-001-02",  # auth DDL + module基盤
        ],
    },
    "S2": {
        "name": "AI 社員 + Chat + Memory (3 tier)",
        "dogfood": "workspace 内で AI 社員と会話できる + 短期/中期/長期 memory が回る",
        "feature_ids": ["F-003", "F-020", "F-022", "F-AI", "F-M12", "M-27", "M-28", "M-30"],
        "extra_task_ids": [
            "T-001-03", "T-001-04", "T-001-05", "T-001-06", "T-001-07", "T-001-08",
            "T-001-09", "T-001-10", "T-001-11",  # DB 全部 = AI 動作の前提
            "T-026-01", "T-026-02", "T-026-03",  # Constitution
            "T-024-04",  # search RLS
        ],
    },
    "S3": {
        "name": "ヒアリング → 要件定義 AI ペルソナ",
        "dogfood": "Mary (BA) がヒアリング, Preston (PM) が要件定義書を出す",
        "feature_ids": ["F-005", "F-005b"],
        "extra_task_ids": [],
    },
    "S4": {
        "name": "アーキ設計 → 機能分解 → タスク分解 AI",
        "dogfood": "Winston (Architect) → Sally (PO) → Devon (Dev) の連携で 1 案件分が組み立つ",
        "feature_ids": ["F-006", "F-025"],
        "extra_task_ids": [],
    },
    "S5": {
        "name": "Kanban + DAG + Phase 管理 + 横断検索",
        "dogfood": "タスク化 → Kanban で進捗 → DAG で依存可視化 → Cmd+K で横断検索",
        "feature_ids": ["F-007", "F-008", "F-009", "F-024"],
        "extra_task_ids": [
            "T-AI-03",  # search index AI
        ],
    },
    "S6": {
        "name": "MCP + Reviewer + Constitution 適用",
        "dogfood": "Quinn (QA/Reviewer) が動く + MCP server 経由で Claude Code に bf tools が見える + red-line 監視",
        "feature_ids": ["F-010a", "F-010b", "F-011", "F-012"],
        "extra_task_ids": [
            "T-AI-04",  # constitution 注入
        ],
    },
    "S7": {
        "name": "Swarm 並列実行 + Worktree (= 靴屋に靴を履かせる)",
        "dogfood": "1 人の operator が Swarm UI で複数 task を並列実行できる",
        "feature_ids": ["F-010c", "F-010d", "M-29"],
        "extra_task_ids": [
            "T-021-03",  # Swarm orchestrator
        ],
    },
    "S8": {
        "name": "GitHub + Slack + Obsidian + 観測 + 監査 + 配信",
        "dogfood": "PR 自動化 / Slack 通知 / Obsidian エクスポート / Langfuse / 監査ログ / 納品まで完走",
        "feature_ids": ["F-013", "F-014", "F-015", "F-016", "F-017", "F-018", "F-019"],
        "extra_task_ids": [],
    },
}

# META タスク (T-IT-* / T-S0-* / T-BTSTRAP-*) は別途マッピング
META_SLICE_MAP = {
    # Sprint 統合テスト → 対応 Slice
    "T-IT-S0": "S1", "T-IT-S2": "S2", "T-IT-S3": "S3", "T-IT-S4": "S5",
    "T-IT-S5": "S6", "T-IT-S6": "S7", "T-IT-S7": "S8",
    # bootstrap (project template) → S4 (案件作成時の品質担保)
    "T-BTSTRAP-01": "S4", "T-BTSTRAP-02": "S4", "T-BTSTRAP-03": "S4",
    "T-BTSTRAP-04": "S4", "T-BTSTRAP-05": "S4", "T-BTSTRAP-06": "S4",
    # Sprint 0 scaffold → S1 (土台)
    "T-S0-01": "S1", "T-S0-02": "S1", "T-S0-03": "S1", "T-S0-04": "S1",
    "T-S0-05": "S1", "T-S0-06": "S1", "T-S0-07": "S1",
    "T-S0-08": "S2", "T-S0-09": "S6", "T-S0-09b": "S6",
    "T-S0-10": "S8", "T-S0-11": "S8", "T-S0-12": "S8",
    "T-S0-13": "S1", "T-S0-13b": "S1", "T-S0-13c": "S1",
    # ARCHIVE (T-019-*)
    "T-019-01": "S1", "T-019-02": "S1", "T-019-03": "S1",
}


def assign_slice(t):
    """task に Slice を割り当てる."""
    tid = t["id"]
    feat = t.get("feature", "")
    # 1) META マップ優先
    if tid in META_SLICE_MAP:
        return META_SLICE_MAP[tid]
    # 2) extra_task_ids
    for slice_id, sd in SLICE_DEFINITIONS.items():
        if tid in sd["extra_task_ids"]:
            return slice_id
    # 3) feature ID で振り分け
    for slice_id, sd in SLICE_DEFINITIONS.items():
        if feat in sd["feature_ids"]:
            return slice_id
    # 4) 残り (フォールバック) — feature unmapped なら S2 (汎用 backend)
    return "S2"


def assign_wave(t, slice_id, all_tickets_by_id, done_set):
    """Slice 内で Wave (依存深さ) を割り当てる.

    Wave 命名: "{slice_num}.{wave_num}"
    Wave 1 = 当該 Slice 内の他 task に依存しないもの (foundational)
    Wave 2 = Wave 1 のいずれかに依存
    Wave 3 = ...

    Integration test (T-IT-*) は常に最終 Wave (.99) に固定.
    """
    slice_num = int(slice_id[1:])
    if t["id"].startswith("T-IT-"):
        return f"{slice_num}.99"

    # 同 Slice 内 task 集合
    same_slice_ids = {
        oid for oid, ot in all_tickets_by_id.items()
        if assign_slice(ot) == slice_id
    }
    deps = t.get("deps", [])
    deps_in_slice = [d for d in deps if d in same_slice_ids]
    if not deps_in_slice:
        return f"{slice_num}.1"
    # 最大依存深さ + 1 (簡易 BFS)
    max_depth = 0
    visited = set()
    queue = [(d, 1) for d in deps_in_slice]
    while queue:
        current_id, depth = queue.pop(0)
        if current_id in visited or current_id not in all_tickets_by_id:
            continue
        visited.add(current_id)
        max_depth = max(max_depth, depth)
        ct = all_tickets_by_id[current_id]
        sub_deps = [d for d in ct.get("deps", []) if d in same_slice_ids]
        for sd in sub_deps:
            queue.append((sd, depth + 1))
    wave_num = max_depth + 1
    return f"{slice_num}.{wave_num}"


def assign_parallel_group(t, slice_id, wave, all_tickets_by_id):
    """同 Slice + 同 Wave 内で、互いに依存しない task を group 化.

    返り値: "P{wave}-A" / "P{wave}-B" など.
    実装簡略: feature ID をハッシュ化して group 文字を決める.
    完璧なグラフカラーリングではないが、運用上 "同 wave 同 group は並列 OK" の指針として機能する.
    """
    feat = t.get("feature", "")
    # feature ID 同じものは A/B/C... を順番に振る
    return f"P{wave}-{feat[-3:].upper().replace('-', '')[-3:]}"


def detect_done(commits_full):
    """git log 全文から done task ID 集合を抽出."""
    return commits_full


def slice_dogfood(slice_id):
    return SLICE_DEFINITIONS.get(slice_id, {}).get("dogfood", "")


def main():
    # 1) 既存 tickets.json 読み込み (完全保持)
    with SRC.open() as f:
        d = json.load(f)
    tickets = d["tickets"]
    by_id = {t["id"]: t for t in tickets}

    # 2) done 検出 (2 経路の OR):
    #    (a) git log の commit subject + body に task ID 出現
    #    (b) docs/audit/2026-05-13_v2/<TASK-ID>.md が存在 (= pre-flight/retroactive audit 済み)
    commits_full = subprocess.check_output(
        ["git", "log", "origin/main", "--pretty=format:%s%n%b%n---END---"]
    ).decode()
    audit_dir = ROOT / "docs/audit/2026-05-13_v2"
    audit_md_ids = (
        {p.stem for p in audit_dir.glob("T-*.md")} if audit_dir.is_dir() else set()
    )
    done_set = {
        tid for tid in by_id
        if re.search(r"\b" + re.escape(tid) + r"\b", commits_full)
        or tid in audit_md_ids
    }

    # 3) Slice 割り当て
    for t in tickets:
        t["slice"] = assign_slice(t)

    # 4) Wave 割り当て (Slice 内の依存深さで)
    for t in tickets:
        t["wave"] = assign_wave(t, t["slice"], by_id, done_set)

    # 5) parallel_group 割り当て
    for t in tickets:
        t["parallel_group"] = assign_parallel_group(t, t["slice"], t["wave"], by_id)

    # 6) dogfood_value (Slice 全体の dogfood description を継承)
    for t in tickets:
        t["dogfood_value"] = slice_dogfood(t["slice"])

    # 7) unlocks (deps の逆向き)
    unlocks_map = defaultdict(list)
    for t in tickets:
        for dep in t.get("deps", []):
            unlocks_map[dep].append(t["id"])
    for t in tickets:
        t["unlocks"] = sorted(unlocks_map.get(t["id"], []))

    # 8) done_status
    for t in tickets:
        t["done_status"] = "done" if t["id"] in done_set else "pending"

    # 9) meta / summary 拡張
    d["meta"]["v2_generated_at"] = "2026-05-14"
    d["meta"]["v2_source"] = "../2026-05-09_v1/tickets.json"
    d["meta"]["v2_slice_count"] = 8
    d["summary"]["v2_slices"] = {
        sid: {
            "name": sd["name"],
            "dogfood": sd["dogfood"],
            "task_count": sum(1 for t in tickets if t["slice"] == sid),
            "done_count": sum(1 for t in tickets if t["slice"] == sid and t["done_status"] == "done"),
        }
        for sid, sd in SLICE_DEFINITIONS.items()
    }

    # 10) 出力
    DST_DIR.mkdir(parents=True, exist_ok=True)
    with DST_JSON.open("w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)

    # 11) 集計サマリー
    print(f"=== tickets-v2 生成完了 ===")
    print(f"  入力:   {SRC}")
    print(f"  出力:   {DST_JSON}")
    print(f"  task:   {len(tickets)} 件")
    print(f"  done:   {sum(1 for t in tickets if t['done_status']=='done')}")
    print(f"  pending:{sum(1 for t in tickets if t['done_status']=='pending')}")
    print()
    print(f"=== Slice 別 進捗 ===")
    print(f"{'Slice':<6}{'Done':>6}{'Pending':>10}{'Total':>8}{'%':>8}  Name")
    print("-" * 80)
    for sid, sd in SLICE_DEFINITIONS.items():
        slice_tasks = [t for t in tickets if t["slice"] == sid]
        done = sum(1 for t in slice_tasks if t["done_status"] == "done")
        total = len(slice_tasks)
        pct = 100 * done / total if total else 0
        print(f"{sid:<6}{done:>6}{total - done:>10}{total:>8} {pct:>6.1f}%  {sd['name']}")


if __name__ == "__main__":
    main()
