"""
design_pipeline.py — Phase A デザインスキル連鎖

brand-voice → design-md → frontend-design → ui-mockup の 4 ステップを
順次実行し、それぞれの出力を artifact として保存する。

各ステップ:
  1. 該当 AI 社員（PM 秘書 + アーキテクト + デザイン担当）に skill 発火を指示
  2. 出力 artifact を workspace に紐付け
  3. 次のステップにコンテキストとして渡す

最終出力:
  workspace の design_system_ref が確定し、
  Onlook 起動時に「決定済みのデザイン方針 + 選択された design-system」を渡せる状態になる。
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import aiosqlite

from db.queries import DB_PATH


PHASE_A_STEPS = [
    {
        "step":         1,
        "skill":        "brand-voice",
        "title":        "ブランドボイス確定",
        "optional":     True,    # 自社プロダクトでスキップ可
        "owner":        "secretary",
        "category_tag": "design-brand-voice",
    },
    {
        "step":         2,
        "skill":        "design-md",
        "title":        "デザインシステム確定（Google Labs design.md 形式）",
        "optional":     False,
        "owner":        "architect",
        "category_tag": "design-system",
    },
    {
        "step":         3,
        "skill":        "frontend-design",
        "title":        "フロントエンドスタイル方針",
        "optional":     False,
        "owner":        "engineer",
        "category_tag": "design-frontend",
    },
    {
        "step":         4,
        "skill":        "ui-mockup",
        "title":        "UI モック方針（Onlook への入力準備）",
        "optional":     False,
        "owner":        "engineer",
        "category_tag": "design-mockup-spec",
    },
]


async def get_pipeline_state(workspace_id: int) -> dict:
    """workspace の design pipeline 進捗を返す。

    各ステップが既に artifact として完了しているか確認する。
    """
    state = {"workspace_id": workspace_id, "steps": []}
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        for step in PHASE_A_STEPS:
            cur = await db.execute(
                """SELECT id, title, type, created_at, updated_at
                   FROM artifacts
                   WHERE workspace_id = ? AND is_archived = 0
                     AND category_tags LIKE ?
                   ORDER BY updated_at DESC LIMIT 1""",
                (workspace_id, f'%"{step["category_tag"]}"%'),
            )
            row = await cur.fetchone()
            state["steps"].append({
                "step": step["step"],
                "skill": step["skill"],
                "title": step["title"],
                "optional": step["optional"],
                "owner": step["owner"],
                "completed": bool(row),
                "artifact_id": row["id"] if row else None,
                "completed_at": row["updated_at"] if row else None,
            })
    state["all_required_done"] = all(
        s["completed"] for s in state["steps"]
        if not next((p for p in PHASE_A_STEPS if p["step"] == s["step"]), {}).get("optional")
    )
    return state


async def kickoff_step(
    workspace_id: int,
    step_no: int,
    *,
    user_input: Optional[str] = None,
    helper_provider: str = "openai",
    helper_model: str = "gpt-4o-mini",
) -> dict:
    """1 ステップ実行: 該当スキルを LLM に渡して artifact を生成・保存する。

    実装はシンプル: SKILL.md を読んで LLM に system prompt として渡し、
    user_input から「設計確定書」を生成。
    """
    step = next((s for s in PHASE_A_STEPS if s["step"] == step_no), None)
    if not step:
        raise ValueError(f"unknown step: {step_no}")

    # workspace 情報取得
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
        ws = await cur.fetchone()
    if not ws:
        raise FileNotFoundError(f"workspace {workspace_id} not found")
    ws = dict(ws)

    # SKILL.md ロード
    from services import skill_manager as sm
    skill = await sm.get_skill(step["skill"])
    skill_md = skill.get("skill_md_full") if skill else None

    # 直前 step までのコンテキスト
    prior_artifacts = []
    for prev in PHASE_A_STEPS:
        if prev["step"] >= step_no:
            break
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT title, data, type FROM artifacts
                   WHERE workspace_id = ? AND is_archived = 0
                     AND category_tags LIKE ?
                   ORDER BY updated_at DESC LIMIT 1""",
                (workspace_id, f'%"{prev["category_tag"]}"%'),
            )
            row = await cur.fetchone()
        if row:
            prior_artifacts.append({
                "step": prev["step"], "skill": prev["skill"],
                "title": row["title"],
                "data": row["data"][:3000] if row["data"] else "",
            })

    # LLM 呼び出し
    if not os.environ.get("OPENAI_API_KEY") and helper_provider == "openai":
        return {
            "step": step_no, "status": "skipped",
            "reason": "OPENAI_API_KEY 未設定",
        }

    system_prompt = (
        "あなたは Build-Factory の設計フェーズを担当する AI 社員です。\n"
        f"今回のタスク: {step['title']}\n"
        f"使用するスキル: {step['skill']}\n\n"
        + (skill_md or f"({step['skill']} の SKILL.md が見つかりません・自分の知識で実行してください)")
    )
    user_prompt = (
        f"# Workspace: {ws['name']}\n"
        f"{ws.get('description') or ''}\n\n"
        f"# Project meta\n```json\n{ws.get('project_meta') or '{}'}\n```\n\n"
        f"# 前ステップの成果\n"
        + "".join(
            f"\n## Step {a['step']} - {a['skill']}\n{a['title']}\n```\n{a['data']}\n```\n"
            for a in prior_artifacts
        )
        + f"\n# あなたへの指示\n{user_input or '上記のコンテキストを踏まえて、このステップの成果を出力してください'}\n\n"
        "出力は Markdown で・要点は箇条書きで・後続ステップで参照できる構造にしてください。"
    )

    try:
        from llm.config import get_openai_client, LLMProvider
        try:
            pe = LLMProvider(helper_provider)
        except ValueError:
            pe = LLMProvider.OPENAI
        client = get_openai_client(pe, dict(os.environ))
        resp = await client.chat.completions.create(
            model=helper_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens=2000,
            temperature=0.3,
        )
        text = resp.choices[0].message.content or ""
    except Exception as e:
        return {"step": step_no, "status": "failed", "error": str(e)}

    # artifact 保存
    from services import artifact_service as art
    a = await art.create_artifact(
        type="markdown",
        title=f"[Phase A · Step {step_no}] {step['title']}",
        data={"text": text},
        category_tags=[step["category_tag"], "phase-a"],
        thread_id=None,
        employee_id=None,
        created_by=f"phase-a:{step['skill']}",
        actor=f"phase-a:{step['skill']}",
    )
    # workspace_id 後付け
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE artifacts SET workspace_id = ? WHERE id = ?",
            (workspace_id, a["id"]),
        )
        await db.commit()

    return {
        "step": step_no, "status": "completed",
        "artifact_id": a["id"], "title": a["title"],
        "preview": text[:300],
    }


async def run_full_pipeline(
    workspace_id: int,
    user_input: str,
    *,
    skip_optional: bool = True,
    helper_provider: str = "openai",
    helper_model: str = "gpt-4o-mini",
) -> dict:
    """Phase A の 4 ステップを順番に実行する。"""
    results = []
    for step in PHASE_A_STEPS:
        if skip_optional and step["optional"]:
            results.append({"step": step["step"], "status": "skipped",
                            "reason": "optional"})
            continue
        try:
            r = await kickoff_step(
                workspace_id, step["step"], user_input=user_input,
                helper_provider=helper_provider, helper_model=helper_model,
            )
            results.append(r)
        except Exception as e:
            results.append({"step": step["step"], "status": "failed", "error": str(e)})
            break  # 失敗したら止める
    return {"workspace_id": workspace_id, "results": results}
