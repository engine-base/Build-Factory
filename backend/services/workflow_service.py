"""
workflow_service.py — マルチエージェント・ワークフロー実行エンジン

複雑な依頼を秘書が複数のスキルに分解 → 並列/順次で実行 → 統合する。

例:
  「○○社への提案書作って」
    → market-research（業界調査）+ competitive-analysis（競合）+ pricing-design（価格）を並列実行
    → 結果を proposal スキルに渡して最終提案書を生成
    → approval_queue へ
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from db import async_db as aiosqlite

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

# 秘書AIに「複数スキル協業のプラン」を立てさせるメタプロンプト
PLANNER_PROMPT = """以下のユーザー依頼に対して、複数のAI社員（スキル）が協業して達成するプランを設計してください。
各ステップは利用可能なスキルから選び、並列実行可能なものは parallel_group に同じグループ名を付けます。
最終的に1つの統合スキル（synthesis: true）が他のステップの結果を受け取って完成品を作ります。

利用可能なスキル例:
- market-research, competitive-analysis, customer-report, info-curation
- proposal, pricing-design, estimate
- sales-email, customer-followup, pipeline-management
- invoice-create, cashflow-forecast, expense-management, pl-management
- weekly-review, monthly-review, kpi-dashboard, kpi-monitoring
- sns-management, email-marketing, content-strategy, press-release
- contract-review, nda-review, business-contract
- support-response, cs-survey

出力（JSONのみ・コードブロック不要）:
{
  "is_multi_agent": true,
  "summary": "プラン概要（30字以内）",
  "steps": [
    {"step": 1, "skill": "...", "input": "そのステップへの指示", "parallel_group": "research", "synthesis": false},
    {"step": 2, "skill": "...", "input": "...", "parallel_group": "research", "synthesis": false},
    {"step": 3, "skill": "...", "input": "前ステップの結果を統合する指示", "depends_on": [1,2], "synthesis": true}
  ],
  "needs_approval": true
}

単一スキルで足りる単純な依頼の場合は is_multi_agent: false を返してください。

ユーザー依頼:
"""


async def run_workflow(user_request: str, channel_say=None) -> dict:
    """
    複数スキル協業のワークフローを実行する。

    Returns:
      {"workflow_id": int, "final_output": str, "approval_id": int|None}
    """
    say = channel_say or _print_say

    # 1. 秘書にプランを立てさせる
    await say("🧠 プランを設計中...")
    plan = await _ask_planner(user_request)
    if not plan:
        await say("⚠️ プラン設計に失敗しました。単一スキルで処理します。")
        return {"status": "fallback_single", "skill": None}

    if not plan.get("is_multi_agent", False):
        return {"status": "single_skill_recommended", "plan": plan}

    steps = plan.get("steps", [])
    if not steps:
        return {"status": "no_steps"}

    # 2. workflow_runs にレコード作成
    workflow_id = await _create_workflow_run(user_request, plan)

    summary = plan.get("summary", "")
    await say(f"📋 プラン: {summary}\n  ステップ数: {len(steps)}")

    # 3. ステップを並列グループ単位で実行
    completed_outputs: dict[int, str] = {}
    grouped = _group_by_parallel(steps)

    for group_steps in grouped:
        group_label = group_steps[0].get("parallel_group") or "順次"
        skill_names = [s["skill"] for s in group_steps]
        await say(f"  ▶ 実行中: {group_label} ({', '.join(skill_names)})")

        # depends_on の結果を input に追記
        tasks = []
        for step in group_steps:
            enriched_input = _enrich_input(step, completed_outputs)
            tasks.append(_run_step(workflow_id, step, enriched_input))

        # 並列実行
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for step, result in zip(group_steps, results):
            if isinstance(result, Exception):
                await say(f"    ❌ {step['skill']}: {result}")
                completed_outputs[step["step"]] = f"[エラー] {result}"
            else:
                completed_outputs[step["step"]] = result
                await say(f"    ✅ {step['skill']} 完了")

    # 4. synthesis ステップの結果を最終出力にする
    final_step = next((s for s in steps if s.get("synthesis")), None)
    if final_step:
        final_output = completed_outputs.get(final_step["step"], "")
    else:
        final_output = "\n\n".join(
            f"## ステップ{n} ({steps[n-1]['skill']})\n{out}"
            for n, out in completed_outputs.items()
        )

    # 5. 承認キューに積む（必要なら）
    approval_id = None
    if plan.get("needs_approval", True):
        approval_id = await _create_approval(user_request, final_output, plan)
        await say(f"✅ ワークフロー完了 → 承認キュー #{approval_id}")
    else:
        await say(f"✅ ワークフロー完了\n\n{final_output[:1500]}")

    # 6. workflow_runs を完了状態に
    await _complete_workflow_run(workflow_id, final_output, approval_id)

    return {
        "status": "completed",
        "workflow_id": workflow_id,
        "final_output": final_output,
        "approval_id": approval_id,
    }


# ── 内部ヘルパー ──────────────────────────────────────────────────────────

async def _ask_planner(user_request: str) -> Optional[dict]:
    """秘書AIにマルチエージェントプランを立てさせる。"""
    try:
        from integrations.skill_runner import invoke_skill
        prompt = PLANNER_PROMPT + user_request
        response = await invoke_skill(
            "secretary", prompt,
            provider="ollama", model="qwen2.5:7b",
            triggered_by="user"
        )
        m = re.search(r'\{.*\}', response, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        print(f"[workflow] プラン設計失敗: {e}")
    return None


def _group_by_parallel(steps: list[dict]) -> list[list[dict]]:
    """parallel_group が同じステップを1グループにまとめる（順序を保つ）。"""
    groups: list[list[dict]] = []
    seen_groups: set[str] = set()

    for step in steps:
        pg = step.get("parallel_group")
        if pg and pg not in seen_groups:
            # このグループの全ステップを一括追加
            same = [s for s in steps if s.get("parallel_group") == pg]
            groups.append(same)
            seen_groups.add(pg)
        elif not pg:
            # parallel_group が無い → 単独グループ
            groups.append([step])
    return groups


def _enrich_input(step: dict, completed: dict[int, str]) -> str:
    """depends_on のステップ結果を input の冒頭に追記する。"""
    base_input = step.get("input", "")
    deps = step.get("depends_on") or []
    if not deps:
        return base_input

    context_parts = ["## 前ステップの結果（参照してください）"]
    for d in deps:
        out = completed.get(d, "")
        if out:
            context_parts.append(f"\n### ステップ{d}の出力:\n{out[:1500]}")

    return "\n".join(context_parts) + "\n\n## このステップの指示\n" + base_input


async def _run_step(workflow_id: int, step: dict, enriched_input: str) -> str:
    """単一ステップを実行して結果を返す。"""
    from integrations.skill_runner import invoke_skill

    step_id = await _create_step(workflow_id, step, enriched_input)
    started = datetime.now()

    try:
        result = await invoke_skill(
            step["skill"], enriched_input,
            provider="ollama", model="qwen2.5:7b",
            triggered_by="workflow",
            trigger_id=workflow_id,
        )
        duration = (datetime.now() - started).total_seconds()
        await _complete_step(step_id, result, duration)
        return result
    except Exception as e:
        duration = (datetime.now() - started).total_seconds()
        await _fail_step(step_id, str(e), duration)
        raise


async def _create_workflow_run(user_request: str, plan: dict) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO workflow_runs
               (user_request, plan_json, status, steps_total)
               VALUES (?, ?, 'running', ?) RETURNING id""",
            (user_request, json.dumps(plan, ensure_ascii=False), len(plan.get("steps", [])))
        )
        _row = await cursor.fetchone()
        await db.commit()
        return _row["id"]


async def _complete_workflow_run(workflow_id: int, output: str, approval_id: Optional[int]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE workflow_runs
               SET status='completed', final_output=?, approval_id=?,
                   completed_at=datetime('now','localtime')
               WHERE id=?""",
            (output[:5000], approval_id, workflow_id)
        )
        await db.commit()


async def _create_step(workflow_id: int, step: dict, enriched_input: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO workflow_steps
               (workflow_run_id, step_number, skill_name, input,
                parallel_group, depends_on, status, started_at)
               VALUES (?, ?, ?, ?, ?, ?, 'running', datetime('now','localtime')) RETURNING id""",
            (
                workflow_id,
                step.get("step", 0),
                step["skill"],
                enriched_input[:2000],
                step.get("parallel_group"),
                json.dumps(step.get("depends_on", [])),
            )
        )
        _row = await cursor.fetchone()
        await db.commit()
        return _row["id"]


async def _complete_step(step_id: int, output: str, duration: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE workflow_steps
               SET status='completed', output=?, duration_sec=?,
                   completed_at=datetime('now','localtime')
               WHERE id=?""",
            (output[:3000], round(duration, 2), step_id)
        )
        await db.execute(
            "UPDATE workflow_runs SET steps_completed = steps_completed + 1 WHERE id=(SELECT workflow_run_id FROM workflow_steps WHERE id=?)",
            (step_id,)
        )
        await db.commit()


async def _fail_step(step_id: int, error: str, duration: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE workflow_steps
               SET status='failed', output=?, duration_sec=?,
                   completed_at=datetime('now','localtime')
               WHERE id=?""",
            (f"ERROR: {error}"[:3000], round(duration, 2), step_id)
        )
        await db.commit()


async def _create_approval(request: str, output: str, plan: dict) -> int:
    """ワークフロー結果を承認キューに登録する。"""
    from datetime import timedelta
    expires_at = (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO approval_queue
               (action_type, title, content, source_skill, expires_at, metadata)
               VALUES ('workflow_result', ?, ?, 'multi-agent', ?, ?) RETURNING id""",
            (
                request[:80],
                output,
                expires_at,
                json.dumps({"plan_summary": plan.get("summary", "")}, ensure_ascii=False),
            )
        )
        _row = await cursor.fetchone()
        await db.commit()
        return _row["id"]


async def _print_say(msg: str):
    print(f"[workflow] {msg}")


# ── 一覧取得API用 ─────────────────────────────────────────────────────────

async def list_workflows(limit: int = 30) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT id, user_request, status, steps_completed, steps_total,
                      approval_id, started_at, completed_at
               FROM workflow_runs
               ORDER BY started_at DESC LIMIT ?""",
            (limit,)
        )
    return [dict(r) for r in rows]


async def get_workflow_detail(workflow_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        run_rows = await db.execute_fetchall(
            "SELECT * FROM workflow_runs WHERE id=?", (workflow_id,)
        )
        if not run_rows:
            return {}
        step_rows = await db.execute_fetchall(
            "SELECT * FROM workflow_steps WHERE workflow_run_id=? ORDER BY step_number",
            (workflow_id,)
        )
    return {
        "run": dict(run_rows[0]),
        "steps": [dict(r) for r in step_rows]
    }
