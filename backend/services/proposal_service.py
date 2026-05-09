"""
proposal_service.py — Phase 4 (提案書) 対話駆動フロー

5 STEP 構成:
  1. 起点整理・トーン確認 (前フェーズ自動引き継ぎ)
  2. 課題深掘り・ソリューション設計
  3. スコープ・フェーズ・スケジュール
  4. リスク・前提・体制
  5. 最終ドラフト確定 + 出力

中央エリア = 常に「提案書ドラフト」スクロール 1 本 (8 章を上から下へ)。
中間出力 (構造化メモ・思考ログ) は artifact 裏側に保持し、画面には出さない。

8 章 (TOC アンカー):
  cover               カバー
  executive_summary   エグゼクティブサマリー
  problem             課題の深掘り
  solution            提案ソリューション
  roi                 ROI・効果
  scope               スコープ・フェーズ
  schedule            スケジュール・費用
  risk_team           リスク・前提・体制
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional
from pathlib import Path

from db import async_db as adb
from db.queries import DB_PATH
from llm.config import LLMProvider, get_openai_client


PROPOSAL_SKILL_PATH = Path.home() / ".claude" / "skills" / "proposal" / "SKILL.md"

PHASE = "proposal"


STEPS = [
    {
        "step": 1,
        "title": "起点整理・トーン確認",
        "description": "ヒアリング/要件定義/価格設計を引き継ぎ、トーンと骨格を確定",
        "core_sections": [
            {"key": "cover",             "label": "カバー (案件名・クライアント・サービス種別)"},
            {"key": "executive_summary", "label": "エグゼクティブサマリー"},
            {"key": "tone",              "label": "提案書のトーン・対象読者"},
            {"key": "achievements",      "label": "実績情報 (統計・事例)"},
        ],
    },
    {
        "step": 2,
        "title": "課題深掘り・ソリューション設計",
        "description": "本質課題の深掘り + ソリューション説明 + ROI",
        "core_sections": [
            {"key": "problem",     "label": "課題の深掘り"},
            {"key": "solution",    "label": "提案ソリューション"},
            {"key": "roi",         "label": "ROI・効果"},
            {"key": "tech_stack",  "label": "実装アプローチ・技術スタック"},
        ],
    },
    {
        "step": 3,
        "title": "スコープ・フェーズ・スケジュール",
        "description": "含む/含まない・フェーズ設計・スケジュール・費用",
        "core_sections": [
            {"key": "scope_in",    "label": "スコープ (含むもの)"},
            {"key": "scope_out",   "label": "スコープ (含まないもの・将来対応)"},
            {"key": "phases",      "label": "フェーズ設計"},
            {"key": "schedule",    "label": "スケジュール"},
            {"key": "cost",        "label": "費用概算"},
        ],
    },
    {
        "step": 4,
        "title": "リスク・前提・体制",
        "description": "リスクと対応策 + 提案前提 + 開発体制",
        "core_sections": [
            {"key": "risks",       "label": "リスクと対応策"},
            {"key": "assumptions", "label": "提案前提・クライアント協力事項"},
            {"key": "team",        "label": "開発体制 (AI 社員 + 人間 PM)"},
            {"key": "security",    "label": "セキュリティ・コンプライアンス"},
        ],
    },
    {
        "step": 5,
        "title": "最終ドラフト確定 + 出力",
        "description": "全章の整合性確認 → HTML/MD/JSON 一括出力",
        "core_sections": [
            {"key": "summary",     "label": "提案書サマリー (PM 用最終確認)"},
        ],
    },
]


def get_step_meta(step_num: int) -> Optional[dict]:
    for s in STEPS:
        if s["step"] == step_num:
            return s
    return None


def empty_center_state(step_num: int) -> dict:
    meta = get_step_meta(step_num)
    if not meta:
        return {"step": step_num, "sections": []}
    return {
        "step": step_num,
        "sections": [{"key": s["key"], "label": s["label"], "items": []} for s in meta["core_sections"]],
        "free_sections": [],
        "edited_by_pm": False,
    }


# ──────────────────────────────────────────
# DB ヘルパー
# ──────────────────────────────────────────
async def _save_message(workspace_id: int, step: int, role: str, content: str, metadata: dict = None) -> int:
    async with adb.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO chat_messages (workspace_id, phase, step, role, content, metadata)
               VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
            (workspace_id, PHASE, step, role, content, json.dumps(metadata or {}, ensure_ascii=False)),
        )
        row = await cur.fetchone()
        await db.commit()
        return row["id"] if row else 0


async def get_chat_history(workspace_id: int, step: int) -> list[dict]:
    async with adb.connect(DB_PATH) as db:
        db.row_factory = adb.Row
        rows = await db.execute_fetchall(
            """SELECT id, role, content, metadata, created_at
               FROM chat_messages
               WHERE workspace_id=? AND phase=? AND step=?
               ORDER BY id""",
            (workspace_id, PHASE, step),
        )
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["metadata"] = json.loads(d["metadata"]) if isinstance(d["metadata"], str) else (d["metadata"] or {})
        except Exception:
            d["metadata"] = {}
        out.append(d)
    return out


async def get_or_create_center_artifact(workspace_id: int, step: int) -> dict:
    from services import artifact_service as art

    items = await art.list_artifacts(limit=300)
    for a in items:
        if a.get("workspace_id") != workspace_id:
            continue
        if a.get("type") != "spec":
            continue
        data = a.get("data") or {}
        if data.get("phase") == PHASE and data.get("step") == step and not data.get("archived_version"):
            return a

    initial = empty_center_state(step)
    meta = get_step_meta(step)
    title = f"提案書 STEP {step}: {meta['title']}" if meta else f"提案書 STEP {step}"
    created = await art.create_artifact(
        type="spec",
        title=title,
        data={
            "phase": PHASE,
            "step": step,
            "version": 1,
            "status": "draft",
            "center": initial,
        },
        category_tags=[PHASE, f"step-{step}"],
        created_by="ai:pm",
        actor="ai:pm",
    )
    async with adb.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE artifacts SET workspace_id=? WHERE id=?",
            (workspace_id, created["id"]),
        )
        await db.commit()
    created["workspace_id"] = workspace_id
    return created


async def update_center_artifact(artifact_id: str, center: dict, mark_status: Optional[str] = None) -> dict:
    from services import artifact_service as art
    cur = await art.get_artifact(artifact_id)
    if not cur:
        return {}
    data = dict(cur.get("data") or {})
    data["center"] = center
    if mark_status:
        data["status"] = mark_status
    return await art.update_artifact(artifact_id, data=data, actor="ai:pm", note=f"{PHASE} center update")


# ──────────────────────────────────────────
# 前フェーズ自動引き継ぎ (ヒアリング + 要件定義 + 価格設計)
# ──────────────────────────────────────────
async def get_prev_phases_brief(workspace_id: int) -> dict:
    from services import artifact_service as art
    items = await art.list_artifacts(limit=300)
    by_phase_step: dict[tuple[str, int], dict] = {}
    for a in items:
        if a.get("workspace_id") != workspace_id:
            continue
        if a.get("type") != "spec":
            continue
        data = a.get("data") or {}
        ph = data.get("phase")
        if ph not in ("hearing", "requirements", "pricing"):
            continue
        s = data.get("step")
        if s is None:
            continue
        key = (ph, s)
        if key not in by_phase_step or a.get("updated_at", "") > by_phase_step[key].get("updated_at", ""):
            by_phase_step[key] = a

    summary: dict[str, Any] = {"hearing": {}, "requirements": {}, "pricing": {}}
    for (ph, s), a in sorted(by_phase_step.items()):
        center = (a.get("data") or {}).get("center", {})
        summary[ph][f"step{s}"] = {
            "title": (a.get("title") or ""),
            "status": (a.get("data") or {}).get("status"),
            "sections": [
                {"key": sec["key"], "label": sec["label"], "items": sec.get("items", [])}
                for sec in (center.get("sections") or []) if sec.get("items")
            ],
        }
    return summary


# ──────────────────────────────────────────
# 発行者情報 (account_settings) コンテキスト
# ──────────────────────────────────────────
async def _get_references_block(workspace_id: int, keywords: list[str] | None = None) -> str:
    """同一アカウントの提案書系参考資料を AI コンテキストに注入。"""
    try:
        from services import document_ingest_service as ing
        async with adb.connect(DB_PATH) as db:
            db.row_factory = adb.Row
            rows = await db.execute_fetchall(
                "SELECT account_id FROM workspaces WHERE id=?", (workspace_id,)
            )
        account_id = (dict(rows[0]).get("account_id", 1) if rows else 1)
        # proposal_reference → 該当なければ generic
        block = await ing.build_references_context_block(
            account_id=account_id, doc_type="proposal_reference",
            keywords=keywords, limit=2,
        )
        if not block:
            block = await ing.build_references_context_block(
                account_id=account_id, doc_type=None,
                keywords=keywords, limit=2,
            )
        return block or ""
    except Exception as e:
        print(f"[proposal] references fetch failed: {e}")
        return ""


async def _get_issuer_context_block(workspace_id: int) -> str:
    """workspace から account_id を引き、account_settings を AI プロンプト用に整形。"""
    try:
        from services import artifact_service as art_svc
        from services import account_settings_service as acc

        # workspace から account_id を取得
        async with adb.connect(DB_PATH) as db:
            db.row_factory = adb.Row
            rows = await db.execute_fetchall(
                "SELECT account_id FROM workspaces WHERE id=?",
                (workspace_id,),
            )
        if not rows:
            return ""
        account_id = dict(rows[0]).get("account_id", 1)

        settings = await acc.get_or_create_default(account_id)
        return acc.build_ai_context_block(settings)
    except Exception as e:
        print(f"[proposal] issuer context fetch failed: {e}")
        return ""


# ──────────────────────────────────────────
# プロンプト構築
# ──────────────────────────────────────────
def _load_skill_md() -> str:
    if PROPOSAL_SKILL_PATH.exists():
        return PROPOSAL_SKILL_PATH.read_text(encoding="utf-8")
    return ""


def _extract_common_rules(skill_md: str) -> str:
    m = re.search(r"##\s*🧠\s*全スキル共通[\s\S]*?(?=\n#\s|\n##\s+Build-Factory|\Z)", skill_md)
    if m:
        return m.group(0).strip()
    return skill_md[:5000]


def _extract_step_section(skill_md: str, step: int) -> str:
    pattern = rf"###\s*▶\s*STEP\s*{step}[：:][\s\S]*?(?=###\s*▶\s*STEP\s*{step+1}|\n##\s|\Z)"
    m = re.search(pattern, skill_md)
    if m:
        return m.group(0).strip()
    return ""


def _build_system_prompt(step: int, center_state: dict, prev_brief: dict, issuer_block: str = "") -> str:
    meta = get_step_meta(step) or {}
    skill_md = _load_skill_md()
    common_rules = _extract_common_rules(skill_md)
    step_section = _extract_step_section(skill_md, step)
    if not step_section:
        step_section = f"(STEP {step} セクションが見つかりませんでした。skill md を確認してください)"

    prev_summary = ""
    if prev_brief and any(prev_brief.get(k) for k in ("hearing", "requirements", "pricing")):
        prev_summary = (
            "# 前フェーズ情報 (ヒアリング + 要件定義 + 価格設計)\n"
            "これらを踏まえて提案書を組み立ててください。価格設計の推奨見積金額は費用概算にそのまま反映。\n"
            "```json\n"
            + json.dumps(prev_brief, ensure_ascii=False, indent=2)[:5000]
            + "\n```"
        )

    return f"""あなたは「PM AI」です。Build-Factory のこの案件のクライアント向け提案書を組み立てる役割を担います。
proposal スキル (~/.claude/skills/proposal/SKILL.md) に従って厳密に動作してください。

# 共通動作ルール
{common_rules}

{issuer_block}

# 役割 (重要)
このフェーズは **「クライアント提出用の提案書ドラフト作成」** です。
ヒアリング・要件定義・価格設計の出力をそのまま素材として使い、提案書 8 章を段階的に埋めていきます。
中央エリアは **常に提案書ドラフトのスクロール 1 本** で表示されるため、各 STEP では該当章のみ更新し、他章は触らないでください。
中間出力 (思考メモ・構造化中間データ) は出力に含めず、提案書として完成形の文章のみを items に書いてください。

# あなたの今の作業: STEP {step}
{step_section}

{prev_summary}

# Build-Factory UI 制約 (重要)
1. 対話駆動: 1 メッセージは 1-3 文 + 質問 1-2 個まで。長文禁止。
2. 章単位で更新: 該当 STEP の章のみ center_patch で更新。他章は触らない。
3. 中間出力なし: items に書く文章は完成形 (クライアント提出可能な品質)。「メモ」「叩き台」「思考過程」は禁止。
4. 価格設計の引き継ぎ: STEP 3 の cost セクションは前フェーズの推奨見積金額を必ず反映。
5. 絵文字禁止。
6. 【仮説】ラベル: 確証のない部分は items 先頭に「【仮説】」を付ける。
7. STEP 完了判定: 該当章が完成度 80% 以上に達したら "ready_to_complete": true。

# 中央エリアのセクション構造 (STEP {step})
{json.dumps(meta.get('core_sections', []), ensure_ascii=False, indent=2)}

# 現在の中央エリアの状態
```json
{json.dumps(center_state, ensure_ascii=False, indent=2)}
```

# 出力形式 (必ず以下の JSON だけを返す。コードフェンスもなし。)
{{
  "chat_message": "PM への次の発話 (1-3 文 + 質問 1-2 個)",
  "center_patch": [
    {{ "section_key": "cover", "operation": "add" | "update" | "remove", "items": ["完成形の文章"] }}
  ],
  "ready_to_complete": false,
  "internal_note": "(任意) 裏側メモ。画面には出さない"
}}

JSON 以外の文字列は一切返さない。"""


# ──────────────────────────────────────────
# LLM 呼出
# ──────────────────────────────────────────
def _autodetect_provider() -> tuple[LLMProvider, str]:
    explicit = os.environ.get("MAIN_LLM_PROVIDER", "").strip().lower()
    explicit_model = os.environ.get("MAIN_LLM_MODEL", "").strip()
    if explicit:
        try:
            p = LLMProvider(explicit)
            return p, explicit_model or {
                LLMProvider.CLAUDE: "claude-sonnet-4-6",
                LLMProvider.OPENAI: "gpt-4o",
                LLMProvider.OLLAMA: "qwen2.5:7b",
                LLMProvider.LMSTUDIO: "local-model",
                LLMProvider.LITELLM: "claude-sonnet-4-6",
            }[p]
        except ValueError:
            pass
    anth = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()

    def _is_real(k: str) -> bool:
        return bool(k) and "xxxxx" not in k.lower()

    if _is_real(openai_key):
        return LLMProvider.OPENAI, "gpt-4o"
    if _is_real(anth):
        return LLMProvider.CLAUDE, "claude-sonnet-4-6"
    return LLMProvider.OLLAMA, "qwen2.5:7b"


async def _call_llm(system: str, messages: list[dict]) -> dict:
    provider, model = _autodetect_provider()
    try:
        client = get_openai_client(provider, dict(os.environ))
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, *messages],
            max_tokens=3000,
            temperature=0.4,
        )
        text = (resp.choices[0].message.content or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif text.startswith("```"):
            text = text.strip("`").lstrip("\n")
        return json.loads(text)
    except Exception as e:
        print(f"[proposal] LLM error: {e}")
        return {
            "chat_message": "(AI 応答の取得に失敗しました。もう一度送信してください)",
            "center_patch": [],
            "ready_to_complete": False,
            "error": str(e),
        }


def apply_center_patch(center: dict, patch: list[dict]) -> dict:
    new_center = json.loads(json.dumps(center))
    sections = {s["key"]: s for s in new_center.get("sections", [])}
    free = {s["key"]: s for s in new_center.get("free_sections", [])}

    for op in patch or []:
        key = op.get("section_key")
        operation = op.get("operation", "add")
        items = op.get("items", [])
        if not key:
            continue

        if key in sections:
            sec = sections[key]
        elif key in free:
            sec = free[key]
        else:
            label = op.get("label", key)
            sec = {"key": key, "label": label, "items": []}
            new_center.setdefault("free_sections", []).append(sec)
            free[key] = sec

        existing = sec.setdefault("items", [])
        if operation == "remove":
            sec["items"] = [it for it in existing if it not in items]
        elif operation == "update":
            sec["items"] = items
        else:
            for it in items:
                if it not in existing:
                    existing.append(it)

    return new_center


# ──────────────────────────────────────────
# メインフロー
# ──────────────────────────────────────────
async def start_step(workspace_id: int, step: int) -> dict:
    if not get_step_meta(step):
        return {"error": f"unknown step: {step}"}

    art = await get_or_create_center_artifact(workspace_id, step)
    center = (art.get("data") or {}).get("center") or empty_center_state(step)

    history = await get_chat_history(workspace_id, step)
    if history:
        return {
            "artifact": art,
            "center": center,
            "history": history,
            "ai_message": history[-1]["content"] if history[-1]["role"] == "ai" else None,
        }

    prev_brief = await get_prev_phases_brief(workspace_id)
    issuer_block = await _get_issuer_context_block(workspace_id)
    references_block = await _get_references_block(workspace_id)
    system = _build_system_prompt(step, center, prev_brief, issuer_block)
    if references_block:
        system = system + "\n\n" + references_block
    user_kickoff = f"STEP {step} を始めてください。前フェーズの情報を踏まえて該当章を埋めていきましょう。"
    llm_out = await _call_llm(system, [{"role": "user", "content": user_kickoff}])

    chat_msg = llm_out.get("chat_message", "STEP を始めます。")
    center = apply_center_patch(center, llm_out.get("center_patch", []))

    await _save_message(workspace_id, step, "system", "STEP 開始", {})
    msg_id = await _save_message(workspace_id, step, "ai", chat_msg, {"step_started": True})
    art = await update_center_artifact(art["id"], center)

    return {
        "artifact": art,
        "center": center,
        "ai_message": chat_msg,
        "ai_message_id": msg_id,
        "ready_to_complete": llm_out.get("ready_to_complete", False),
    }


async def reply(workspace_id: int, step: int, user_message: str) -> dict:
    art = await get_or_create_center_artifact(workspace_id, step)
    center = (art.get("data") or {}).get("center") or empty_center_state(step)
    history = await get_chat_history(workspace_id, step)

    await _save_message(workspace_id, step, "user", user_message)

    llm_messages = []
    for h in history:
        if h["role"] in ("user", "ai"):
            llm_messages.append({
                "role": "assistant" if h["role"] == "ai" else "user",
                "content": h["content"],
            })
    llm_messages.append({"role": "user", "content": user_message})

    prev_brief = await get_prev_phases_brief(workspace_id)
    issuer_block = await _get_issuer_context_block(workspace_id)
    # ユーザー発話をキーワードに参考資料を検索
    ref_kw = [w for w in (user_message or "").split() if len(w) >= 2][:8]
    references_block = await _get_references_block(workspace_id, keywords=ref_kw or None)
    system = _build_system_prompt(step, center, prev_brief, issuer_block)
    if references_block:
        system = system + "\n\n" + references_block
    llm_out = await _call_llm(system, llm_messages)

    chat_msg = llm_out.get("chat_message", "(応答なし)")
    patch = llm_out.get("center_patch", [])
    new_center = apply_center_patch(center, patch)
    ready = bool(llm_out.get("ready_to_complete", False))

    msg_id = await _save_message(workspace_id, step, "ai", chat_msg, {"ready": ready})
    art = await update_center_artifact(art["id"], new_center)

    return {
        "artifact": art,
        "center": new_center,
        "ai_message": chat_msg,
        "ai_message_id": msg_id,
        "patch": patch,
        "ready_to_complete": ready,
    }


async def complete_step(workspace_id: int, step: int) -> dict:
    art = await get_or_create_center_artifact(workspace_id, step)
    center = (art.get("data") or {}).get("center") or empty_center_state(step)

    if "sections" in center:
        center["sections"] = [s for s in center["sections"] if s.get("items")] + \
                             [s for s in center["sections"] if not s.get("items")]

    art = await update_center_artifact(art["id"], center, mark_status="confirmed")

    # Phase 4: 完了したら knowledge 化 (将来の提案書 AI が参照する素材になる)
    try:
        if step == 5:  # 最終 STEP の確定時のみ
            await _archive_as_knowledge(workspace_id)
    except Exception as e:
        print(f"[proposal] knowledge archive failed: {e}")

    next_step = step + 1
    next_art = None
    if get_step_meta(next_step):
        next_art = await get_or_create_center_artifact(workspace_id, next_step)

    return {
        "artifact": art,
        "center": center,
        "next_step": next_step if next_art else None,
        "next_artifact": next_art,
    }


async def get_state(workspace_id: int) -> dict:
    from services import artifact_service as art_svc
    arts = await art_svc.list_artifacts(limit=300)
    by_step: dict[int, dict] = {}
    for a in arts:
        if a.get("workspace_id") != workspace_id:
            continue
        if a.get("type") != "spec":
            continue
        data = a.get("data") or {}
        if data.get("phase") != PHASE:
            continue
        s = data.get("step")
        if s is None:
            continue
        if s not in by_step or a.get("updated_at", "") > by_step[s].get("updated_at", ""):
            by_step[s] = a

    steps_state = []
    for meta in STEPS:
        s = meta["step"]
        a = by_step.get(s)
        history = await get_chat_history(workspace_id, s)
        center = (a.get("data") or {}).get("center") if a else empty_center_state(s)
        status = (a.get("data") or {}).get("status") if a else "not_started"
        steps_state.append({
            "step": s,
            "title": meta["title"],
            "description": meta["description"],
            "status": status,
            "artifact_id": a.get("id") if a else None,
            "center": center,
            "history": history,
        })

    return {"workspace_id": workspace_id, "phase": PHASE, "steps": steps_state}


# ──────────────────────────────────────────
# 章 (TOC) 構造 — 8 章を 1 本のスクロールで表示
# ──────────────────────────────────────────
CHAPTER_TO_STEP_SECTIONS: dict[str, list[tuple[int, str]]] = {
    "cover":             [(1, "cover")],
    "executive_summary": [(1, "executive_summary"), (1, "tone"), (1, "achievements")],
    "problem":           [(2, "problem")],
    "solution":          [(2, "solution"), (2, "tech_stack")],
    "roi":               [(2, "roi")],
    "scope":             [(3, "scope_in"), (3, "scope_out"), (3, "phases")],
    "schedule":          [(3, "schedule"), (3, "cost")],
    "risk_team":         [(4, "risks"), (4, "assumptions"), (4, "team"), (4, "security")],
}

CHAPTER_LABELS = {
    "cover":             "カバー",
    "executive_summary": "エグゼクティブサマリー",
    "problem":           "課題の深掘り",
    "solution":          "提案ソリューション",
    "roi":               "ROI・効果",
    "scope":             "スコープ・フェーズ",
    "schedule":          "スケジュール・費用",
    "risk_team":         "リスク・前提・体制",
}

CHAPTER_ORDER = ["cover", "executive_summary", "problem", "solution", "roi", "scope", "schedule", "risk_team"]


async def get_aggregated_view(workspace_id: int) -> dict:
    """章単位の集約ビューを返す (8 章をスクロールで一気に表示する用)。"""
    state = await get_state(workspace_id)
    by_step: dict[int, dict] = {s["step"]: s for s in state["steps"]}

    chapters_out: list[dict] = []
    for ch_key in CHAPTER_ORDER:
        refs = CHAPTER_TO_STEP_SECTIONS.get(ch_key, [])
        if not refs:
            continue
        source_steps = sorted({step_num for step_num, _ in refs})

        locked = all(
            (by_step.get(s, {}).get("status") == "not_started") for s in source_steps
        )

        sections: list[dict] = []
        for step_num, section_key in refs:
            step_state = by_step.get(step_num)
            if not step_state:
                continue
            for sec in (step_state["center"].get("sections", []) or []):
                if sec.get("key") == section_key:
                    sections.append({
                        "key": sec["key"],
                        "label": sec.get("label", section_key),
                        "items": sec.get("items", []) or [],
                        "source_step": step_num,
                    })
                    break

        chapters_out.append({
            "key": ch_key,
            "label": CHAPTER_LABELS.get(ch_key, ch_key),
            "locked": locked,
            "source_steps": source_steps,
            "sections": sections,
        })

    return {
        "workspace_id": workspace_id,
        "phase": PHASE,
        "chapters": chapters_out,
        "step_status": {s["step"]: s["status"] for s in state["steps"]},
    }


# ──────────────────────────────────────────
# 出力 (HTML / MD / JSON)
# ──────────────────────────────────────────
def _items_to_md(items: list[str]) -> str:
    return "\n".join(f"- {it}" for it in items) if items else "_(まだ記入されていません)_"


def _html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _items_to_html_paragraphs(items: list[str]) -> str:
    if not items:
        return '<p style="color:#94A3B8; font-size:13px;">(未記入)</p>'
    return "\n".join(f'<p>{_html_escape(it)}</p>' for it in items)


async def render_markdown(workspace_id: int, chapter: str = "all") -> str:
    view = await get_aggregated_view(workspace_id)
    chapters = {c["key"]: c["sections"] for c in view["chapters"]}

    if chapter == "all":
        out = ["# 提案書\n"]
        for ch_key in CHAPTER_ORDER:
            label = CHAPTER_LABELS[ch_key]
            out.append(f"## {label}\n")
            sections = chapters.get(ch_key, [])
            if not sections:
                out.append("_(未記入)_\n\n")
                continue
            for sec in sections:
                if len(sections) > 1:
                    out.append(f"### {sec.get('label')}\n")
                out.append(_items_to_md(sec.get("items", [])))
                out.append("\n\n")
        return "\n".join(out)

    label = CHAPTER_LABELS.get(chapter, chapter)
    out = [f"# {label}\n"]
    sections = chapters.get(chapter, [])
    if not sections:
        out.append("_(未記入)_\n")
        return "\n".join(out)
    for sec in sections:
        out.append(f"## {sec.get('label')}\n")
        out.append(_items_to_md(sec.get("items", [])))
        out.append("\n")
    return "\n".join(out)


async def _gather_project_meta(workspace_id: int) -> dict:
    """proposal/estimate レンダラに渡す案件メタ情報を組み立てる。
    ヒアリング・要件定義・価格設計から抜粋。"""
    prev = await get_prev_phases_brief(workspace_id)
    out: dict = {}

    # ヒアリング step1 から project_name / client を抽出 (簡易)
    for ph in ("hearing", "requirements", "pricing"):
        for sk, body in (prev.get(ph) or {}).items():
            for sec in body.get("sections", []) or []:
                items = sec.get("items", []) or []
                if not items:
                    continue
                if sec.get("key") in ("overview", "project_overview", "summary") and not out.get("project_name"):
                    out["project_name"] = items[0][:80]
                if sec.get("key") in ("client", "stakeholders") and not out.get("client_name"):
                    out["client_name"] = items[0][:80]
                if sec.get("key") in ("recommended_amount",) and not out.get("pricing_amount"):
                    # 「推奨採用案: 320 万円」から数字抽出
                    import re as _re
                    m = _re.search(r"([0-9,]+)\s*万", items[0])
                    if m:
                        try: out["pricing_amount"] = int(m.group(1).replace(",", "")) * 10000
                        except Exception: pass

    # workspace name もフォールバック
    if not out.get("project_name"):
        async with adb.connect(DB_PATH) as db:
            db.row_factory = adb.Row
            rows = await db.execute_fetchall("SELECT name FROM workspaces WHERE id=?", (workspace_id,))
        if rows:
            out["project_name"] = dict(rows[0]).get("name") or "(案件名未設定)"

    out["proposal_date"] = __import__("datetime").date.today().isoformat()
    return out


async def _archive_as_knowledge(workspace_id: int) -> None:
    """完了した提案書を knowledge artifact として保存。次回の AI が参照可能に。"""
    from services import artifact_service as art
    view = await get_aggregated_view(workspace_id)
    summary = {
        "workspace_id": workspace_id,
        "phase": PHASE,
        "chapters": view.get("chapters", []),
        "completed_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
    await art.create_artifact(
        type="knowledge",
        title=f"提案書ナレッジ (workspace #{workspace_id})",
        data=summary,
        category_tags=["knowledge", "proposal", "completed", PHASE],
        created_by="ai:pm",
        actor="ai:pm",
    )


async def render_html(workspace_id: int, chapter: str = "all") -> str:
    # Phase 5: chapter="all" の時は template_render_service 経由でフルテンプレ HTML
    if chapter == "all":
        try:
            from services import template_render_service as tr
            from services import account_settings_service as acc
            view = await get_aggregated_view(workspace_id)
            # workspace の account_id 取得
            async with adb.connect(DB_PATH) as db:
                db.row_factory = adb.Row
                rows = await db.execute_fetchall(
                    "SELECT account_id FROM workspaces WHERE id=?", (workspace_id,))
            account_id = (dict(rows[0]).get("account_id", 1) if rows else 1)
            settings = await acc.get_or_create_default(account_id)

            # 案件サマリ
            project = await _gather_project_meta(workspace_id)
            return tr.render_proposal_html(
                settings=settings,
                project=project,
                proposal_chapters=view.get("chapters", []),
                pricing_amount=project.get("pricing_amount"),
            )
        except Exception as e:
            print(f"[proposal] template render failed, fallback: {e}")

    # 章単位またはフォールバック: 既存のシンプル HTML
    view = await get_aggregated_view(workspace_id)
    chapters = {c["key"]: c["sections"] for c in view["chapters"]}

    targets = CHAPTER_ORDER if chapter == "all" else [chapter]
    body_parts = []
    for ch_key in targets:
        if ch_key not in CHAPTER_LABELS:
            continue
        label = CHAPTER_LABELS[ch_key]
        sections = chapters.get(ch_key, [])
        inner = []
        for sec in sections:
            if len(sections) > 1:
                inner.append(f'<h3>{_html_escape(sec.get("label", ""))}</h3>')
            inner.append(_items_to_html_paragraphs(sec.get("items", [])))
        body_parts.append(f'''
<section class="chapter" id="{ch_key}" data-bf-chapter="{ch_key}">
  <h2>{label}</h2>
  {"".join(inner) if inner else '<p style="color:#94A3B8;font-size:13px;">(未記入)</p>'}
</section>''')

    body_html = "\n".join(body_parts)

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>提案書 — {CHAPTER_LABELS.get(chapter, chapter)}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+JP:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Inter','Noto Sans JP',sans-serif; background: #F5F7FA; color: #0F172A; padding: 32px 24px; line-height: 1.75; }}
  .container {{ max-width: 880px; margin: 0 auto; }}
  h1 {{ font-size: 32px; font-weight: 800; letter-spacing: -0.01em; margin-bottom: 6px; }}
  .meta {{ font-size: 13px; color: #64748B; margin-bottom: 40px; }}
  .chapter {{ background: #fff; border: 1px solid #E4E8EE; border-radius: 12px; padding: 32px 36px; margin-bottom: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }}
  .chapter h2 {{ font-size: 22px; font-weight: 800; color: #004CD9; margin-bottom: 18px; padding-bottom: 12px; border-bottom: 2px solid #E8EFFF; }}
  .chapter h3 {{ font-size: 14px; font-weight: 700; color: #334155; margin: 20px 0 10px; }}
  .chapter p {{ font-size: 14px; line-height: 1.8; color: #334155; margin-bottom: 8px; }}
</style>
</head>
<body>
<div class="container">
  <h1>提案書</h1>
  <div class="meta">章: {CHAPTER_LABELS.get(chapter, chapter)} ・ Build-Factory 自動生成</div>
  {body_html}
</div>
</body>
</html>
"""


async def render_json(workspace_id: int, chapter: str = "all") -> dict:
    view = await get_aggregated_view(workspace_id)
    if chapter == "all":
        return {
            "workspace_id": workspace_id,
            "phase": PHASE,
            "step_status": view["step_status"],
            "chapters": view["chapters"],
        }
    chapters = {c["key"]: c for c in view["chapters"]}
    c = chapters.get(chapter) or {}
    return {
        "workspace_id": workspace_id,
        "phase": PHASE,
        "chapter": chapter,
        "label": CHAPTER_LABELS.get(chapter, chapter),
        "sections": c.get("sections", []),
    }
