"""
reviewer_loop.py — Build-Factory レビュアー AI（リン）の壁打ちループ

役割:
  1. **タスク単位の Evaluator 結果統括**: Claude Code 側 Evaluator が PASS したものを
     さらに高位視点でレビュー（要件適合性・設計判断・全体一貫性）
  2. **全体統合テストの指揮**: 全タスク完了後、納品前の最大テストを取りまとめる
  3. **3 ターン改善ルール**: 改善が収束しない場合は人間エスカレーション

moat の核心:
  下位 AI（実装 / Evaluator / 監視担当）の出力を
  「ナレッジ + スキル + クライアントすり合わせ」で完璧になるまで壁打ちする。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Optional

import aiosqlite

from db.queries import DB_PATH


REVIEWER_EMPLOYEE_NAME = "reviewer"   # ai_employee_config の employee_name


# ──────────────────────────────────────────
# レビュー実行
# ──────────────────────────────────────────

REVIEW_DIMENSIONS = {
    "task_review": [
        "受け入れ基準の充足",
        "設計通りに実装されているか",
        "テストカバレッジ（80% 以上）",
        "セキュリティ（赤線リスト抵触なし）",
        "可読性・保守性",
    ],
    "integration": [
        "機能間連携の整合性",
        "エンドツーエンドフロー",
        "パフォーマンス（規定範囲）",
        "セキュリティ（横断的）",
        "納品基準チェックリスト全項",
    ],
}


async def request_review(
    *,
    task_id: Optional[int] = None,
    workspace_id: Optional[int] = None,
    review_kind: str = "task_review",  # task_review / integration
    target_artifact_ids: Optional[list[str]] = None,
    summary: str = "",
) -> dict:
    """レビュアー AI にレビューを依頼する（pending エントリ作成）"""
    if review_kind not in REVIEW_DIMENSIONS:
        raise ValueError(f"unknown review_kind: {review_kind}")

    # reviewer_employee_id を取得
    reviewer_id = await _get_reviewer_id()

    findings = {
        "kind": review_kind,
        "dimensions": REVIEW_DIMENSIONS[review_kind],
        "target_artifact_ids": target_artifact_ids or [],
        "task_id": task_id,
        "workspace_id": workspace_id,
        "iteration": 1,
    }

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO reviews
               (pr_id, reviewer_employee_id, verdict, summary, findings_json)
               VALUES (?, ?, 'pending', ?, ?)""",
            (None, reviewer_id, summary or f"[{review_kind}] レビュー依頼",
             json.dumps(findings, ensure_ascii=False)),
        )
        review_id = cur.lastrowid
        await db.commit()
    return {
        "review_id": review_id,
        "kind": review_kind,
        "dimensions": REVIEW_DIMENSIONS[review_kind],
        "status": "pending",
    }


async def execute_review(
    review_id: int,
    *,
    helper_provider: str = "openai",
    helper_model: str = "gpt-4o-mini",
) -> dict:
    """pending review を実行: レビュアー AI が壁打ちして verdict を返す。

    返り値:
      verdict: approve / changes_requested / failed
      findings: 各 dimension のチェック結果
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM reviews WHERE id = ?", (review_id,))
        review = await cur.fetchone()
    if not review:
        raise FileNotFoundError(f"review {review_id} not found")
    review = dict(review)
    findings = json.loads(review.get("findings_json") or "{}")
    iteration = findings.get("iteration", 1)

    # ── レビュー対象 artifact 群を取得 ──
    target_ids = findings.get("target_artifact_ids") or []
    artifacts_data = []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        for aid in target_ids:
            cur = await db.execute("SELECT * FROM artifacts WHERE id = ?", (aid,))
            row = await cur.fetchone()
            if row:
                artifacts_data.append(dict(row))

    # ── タスク情報 ──
    task = None
    if findings.get("task_id"):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM tasks WHERE id = ?", (findings["task_id"],))
            row = await cur.fetchone()
            if row:
                task = dict(row)

    # ── workspace 情報 ──
    workspace = None
    if findings.get("workspace_id"):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM workspaces WHERE id = ?", (findings["workspace_id"],))
            row = await cur.fetchone()
            if row:
                workspace = dict(row)

    # ── LLM でレビュー ──
    if not os.environ.get("OPENAI_API_KEY") and helper_provider == "openai":
        return {"review_id": review_id, "verdict": "skipped",
                "reason": "OPENAI_API_KEY 未設定"}

    dimensions = findings.get("dimensions", REVIEW_DIMENSIONS.get(findings.get("kind"), []))
    system_prompt = (
        "あなたは Build-Factory のレビュアー AI（リン）です。\n"
        "厳しいが建設的に・指摘は理由付きで・改善案を併記してください。\n"
        "壁打ちループで品質を担保するのがあなたの役割です。\n"
        "出力形式（JSON）:\n"
        "{\n"
        '  "verdict": "approve" | "changes_requested" | "failed",\n'
        '  "summary": "<1-2 行の総評>",\n'
        '  "checks": [{"dimension": "<項目名>", "passed": true/false,\n'
        '              "evidence": "<根拠>", "suggestion": "<改善案>"}],\n'
        '  "next_action": "<次にやるべきこと>"\n'
        "}\n"
    )
    user_prompt = (
        f"# レビュー種別: {findings.get('kind')}\n"
        f"# Iteration: {iteration} / 3\n\n"
        f"# Workspace\n{json.dumps(workspace, ensure_ascii=False, default=str) if workspace else 'なし'}\n\n"
        f"# Task\n{json.dumps(task, ensure_ascii=False, default=str) if task else 'なし'}\n\n"
        f"# 対象 Artifacts\n{json.dumps(artifacts_data, ensure_ascii=False, default=str)[:5000]}\n\n"
        f"# 評価次元\n" + "\n".join(f"- {d}" for d in dimensions) + "\n\n"
        "上記を厳格にレビューして JSON で結果を返してください。"
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
            temperature=0.2,
            response_format={"type": "json_object"} if "gpt" in helper_model else None,  # type: ignore
        )
        text = resp.choices[0].message.content or "{}"
    except Exception as e:
        return {"review_id": review_id, "verdict": "failed", "error": str(e)}

    try:
        result = json.loads(text)
    except Exception:
        result = {"verdict": "failed", "summary": "JSON parse 失敗", "raw": text[:500]}

    verdict = result.get("verdict", "failed")

    # 3 ターン改善ルール
    escalate = False
    if verdict == "changes_requested" and iteration >= 3:
        verdict = "needs_human_escalation"
        escalate = True

    findings["iteration"] = iteration + 1
    findings["last_result"] = result
    findings["escalated"] = escalate

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE reviews SET verdict = ?, summary = ?, findings_json = ? "
            "WHERE id = ?",
            (verdict, result.get("summary", "")[:500],
             json.dumps(findings, ensure_ascii=False), review_id),
        )
        await db.commit()

    return {
        "review_id": review_id,
        "verdict": verdict,
        "summary": result.get("summary", ""),
        "checks": result.get("checks", []),
        "next_action": result.get("next_action", ""),
        "iteration": iteration,
        "escalated": escalate,
    }


async def get_review(review_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM reviews WHERE id = ?", (review_id,))
        row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["findings"] = json.loads(d.get("findings_json") or "{}")
    except Exception:
        pass
    return d


async def list_reviews(workspace_id: Optional[int] = None, limit: int = 30) -> list[dict]:
    """workspace_id 指定時は findings_json 内の workspace_id でフィルタ。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if workspace_id is None:
            rows = await db.execute_fetchall(
                "SELECT * FROM reviews ORDER BY created_at DESC LIMIT ?", (limit,),
            )
        else:
            # findings_json に "workspace_id":N が含まれるものを抽出
            rows = await db.execute_fetchall(
                """SELECT * FROM reviews
                   WHERE findings_json LIKE ?
                   ORDER BY created_at DESC LIMIT ?""",
                (f'%"workspace_id":{workspace_id}%', limit),
            )
    return [dict(r) for r in rows]


async def _get_reviewer_id() -> int:
    """reviewer (リン) の employee_id を取得。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id FROM ai_employee_config WHERE employee_name = ? LIMIT 1",
            (REVIEWER_EMPLOYEE_NAME,),
        )
        row = await cur.fetchone()
    return row["id"] if row else 4  # fallback
