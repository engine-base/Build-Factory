"""
estimate_service.py — Phase 5 (見積書) 対話駆動フロー

2 STEP 構成 (シンプル):
  1. 見積項目確認 (前フェーズ自動引き継ぎ + 明細・条件を確定)
  2. 最終出力 (HTML / MD / JSON)

中央タブ 4 つ:
  basic_info  基本情報 (見積番号・宛先・件名・有効期限)
  items       見積項目 (項目 / 数量 / 単価 / 金額)
  summary     金額サマリー (小計・消費税・合計)
  terms       支払・振込・備考
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


ESTIMATE_SKILL_PATH = Path.home() / ".claude" / "skills" / "estimate" / "SKILL.md"

PHASE = "estimate"


STEPS = [
    {
        "step": 1,
        "title": "見積項目確認",
        "description": "前フェーズの推奨見積金額・要件を引き継ぎ、明細と条件を確定",
        "core_sections": [
            {"key": "basic",       "label": "基本情報"},
            {"key": "items",       "label": "見積項目"},
            {"key": "summary",     "label": "金額サマリー"},
            {"key": "payment",     "label": "支払い条件"},
            {"key": "bank",        "label": "振込先"},
            {"key": "notes",       "label": "備考・特記事項"},
        ],
    },
    {
        "step": 2,
        "title": "最終出力",
        "description": "HTML / MD / JSON 一括出力",
        "core_sections": [
            {"key": "summary_final", "label": "出力前最終確認"},
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
    title = f"見積書 STEP {step}: {meta['title']}" if meta else f"見積書 STEP {step}"
    created = await art.create_artifact(
        type="spec",
        title=title,
        data={
            "phase": PHASE, "step": step, "version": 1, "status": "draft",
            "center": initial,
        },
        category_tags=[PHASE, f"step-{step}"],
        created_by="ai:pm",
        actor="ai:pm",
    )
    async with adb.connect(DB_PATH) as db:
        await db.execute("UPDATE artifacts SET workspace_id=? WHERE id=?", (workspace_id, created["id"]))
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
# 前フェーズ自動引き継ぎ (ヒアリング + 要件 + 価格設計 + 提案書)
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
        if ph not in ("hearing", "requirements", "pricing", "proposal"):
            continue
        s = data.get("step")
        if s is None:
            continue
        key = (ph, s)
        if key not in by_phase_step or a.get("updated_at", "") > by_phase_step[key].get("updated_at", ""):
            by_phase_step[key] = a

    summary: dict[str, Any] = {"hearing": {}, "requirements": {}, "pricing": {}, "proposal": {}}
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
# プロンプト
# ──────────────────────────────────────────
def _load_skill_md() -> str:
    if ESTIMATE_SKILL_PATH.exists():
        return ESTIMATE_SKILL_PATH.read_text(encoding="utf-8")
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


async def _get_issuer_context_block(workspace_id: int) -> str:
    """workspace から account_id を引き、account_settings を AI プロンプト用に整形。"""
    try:
        from services import account_settings_service as acc
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
        print(f"[estimate] issuer context fetch failed: {e}")
        return ""


async def _get_references_block(workspace_id: int, keywords: list[str] | None = None) -> str:
    try:
        from services import document_ingest_service as ing
        async with adb.connect(DB_PATH) as db:
            db.row_factory = adb.Row
            rows = await db.execute_fetchall(
                "SELECT account_id FROM workspaces WHERE id=?", (workspace_id,)
            )
        account_id = (dict(rows[0]).get("account_id", 1) if rows else 1)
        block = await ing.build_references_context_block(
            account_id=account_id, doc_type="estimate_reference",
            keywords=keywords, limit=2,
        )
        if not block:
            block = await ing.build_references_context_block(
                account_id=account_id, doc_type=None,
                keywords=keywords, limit=2,
            )
        return block or ""
    except Exception as e:
        print(f"[estimate] references fetch failed: {e}")
        return ""


def _build_system_prompt(step: int, center_state: dict, prev_brief: dict, issuer_block: str = "") -> str:
    meta = get_step_meta(step) or {}
    skill_md = _load_skill_md()
    common_rules = _extract_common_rules(skill_md)
    step_section = _extract_step_section(skill_md, step)
    if not step_section:
        step_section = f"(STEP {step} セクションが見つかりませんでした)"

    prev_summary = ""
    if prev_brief and any(prev_brief.get(k) for k in ("pricing", "proposal", "requirements", "hearing")):
        prev_summary = (
            "# 前フェーズ情報 (ヒアリング + 要件 + 価格設計 + 提案書)\n"
            "価格設計の推奨見積金額を見積項目に反映してください。\n"
            "```json\n"
            + json.dumps(prev_brief, ensure_ascii=False, indent=2)[:5000]
            + "\n```"
        )

    return f"""あなたは「PM AI」です。Build-Factory のクライアント向け見積書を作成する役割を担います。
estimate スキル (~/.claude/skills/estimate/SKILL.md) に従って厳密に動作してください。

# 共通動作ルール
{common_rules}

{issuer_block}

# 役割 (重要)
このフェーズは **「クライアント提出用の見積書作成」** です。
価格設計フェーズの推奨見積金額・要件定義の機能一覧を素材として、4 タブ (基本情報 / 見積項目 / 金額サマリー / 支払・振込・備考) を埋めます。
中央エリアは IDE 風タブ表示。完成形の文章のみ出力してください。

# あなたの今の作業: STEP {step}
{step_section}

{prev_summary}

# Build-Factory UI 制約 (重要)
1. 対話駆動: 1 メッセージ 1-3 文 + 質問 1-2 個。
2. 価格設計の引き継ぎ: 推奨見積金額をそのまま items に反映。
3. 見積項目は最大 10 行。各行「項目名 / 数量 / 単価 / 金額」を 1 文字列で表現 (例: "F001 認証システム / 1式 / 80万円 / 80万円")。
4. 消費税 10%・小計と合計を必ず計算して提示。
5. 絵文字禁止。
6. STEP 完了判定: 全 6 セクションが埋まったら "ready_to_complete": true。

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
    {{ "section_key": "items", "operation": "add" | "update" | "remove", "items": ["箇条書き項目"] }}
  ],
  "ready_to_complete": false,
  "internal_note": ""
}}

JSON 以外の文字列は一切返さない。"""


# ──────────────────────────────────────────
# LLM (共通パターン)
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

    if _is_real(openai_key): return LLMProvider.OPENAI, "gpt-4o"
    if _is_real(anth): return LLMProvider.CLAUDE, "claude-sonnet-4-6"
    return LLMProvider.OLLAMA, "qwen2.5:7b"


async def _call_llm(system: str, messages: list[dict]) -> dict:
    provider, model = _autodetect_provider()
    try:
        client = get_openai_client(provider, dict(os.environ))
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, *messages],
            max_tokens=2500, temperature=0.2,
        )
        text = (resp.choices[0].message.content or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif text.startswith("```"):
            text = text.strip("`").lstrip("\n")
        return json.loads(text)
    except Exception as e:
        print(f"[estimate] LLM error: {e}")
        return {"chat_message": "(AI 応答失敗)", "center_patch": [], "ready_to_complete": False, "error": str(e)}


def apply_center_patch(center: dict, patch: list[dict]) -> dict:
    new_center = json.loads(json.dumps(center))
    sections = {s["key"]: s for s in new_center.get("sections", [])}
    free = {s["key"]: s for s in new_center.get("free_sections", [])}
    for op in patch or []:
        key = op.get("section_key")
        operation = op.get("operation", "add")
        items = op.get("items", [])
        if not key: continue
        if key in sections: sec = sections[key]
        elif key in free: sec = free[key]
        else:
            sec = {"key": key, "label": op.get("label", key), "items": []}
            new_center.setdefault("free_sections", []).append(sec)
            free[key] = sec
        existing = sec.setdefault("items", [])
        if operation == "remove": sec["items"] = [it for it in existing if it not in items]
        elif operation == "update": sec["items"] = items
        else:
            for it in items:
                if it not in existing: existing.append(it)
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
            "artifact": art, "center": center, "history": history,
            "ai_message": history[-1]["content"] if history[-1]["role"] == "ai" else None,
        }
    prev_brief = await get_prev_phases_brief(workspace_id)
    issuer_block = await _get_issuer_context_block(workspace_id)
    references_block = await _get_references_block(workspace_id)
    system = _build_system_prompt(step, center, prev_brief, issuer_block)
    if references_block:
        system = system + "\n\n" + references_block
    user_kickoff = f"STEP {step} を始めてください。価格設計の推奨見積金額を反映して見積項目を埋めてください。"
    llm_out = await _call_llm(system, [{"role": "user", "content": user_kickoff}])
    chat_msg = llm_out.get("chat_message", "STEP を始めます。")
    center = apply_center_patch(center, llm_out.get("center_patch", []))
    await _save_message(workspace_id, step, "system", "STEP 開始", {})
    msg_id = await _save_message(workspace_id, step, "ai", chat_msg, {"step_started": True})
    art = await update_center_artifact(art["id"], center)
    return {
        "artifact": art, "center": center,
        "ai_message": chat_msg, "ai_message_id": msg_id,
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
        "artifact": art, "center": new_center,
        "ai_message": chat_msg, "ai_message_id": msg_id,
        "patch": patch, "ready_to_complete": ready,
    }


async def complete_step(workspace_id: int, step: int) -> dict:
    art = await get_or_create_center_artifact(workspace_id, step)
    center = (art.get("data") or {}).get("center") or empty_center_state(step)
    if "sections" in center:
        center["sections"] = [s for s in center["sections"] if s.get("items")] + \
                             [s for s in center["sections"] if not s.get("items")]
    art = await update_center_artifact(art["id"], center, mark_status="confirmed")
    next_step = step + 1
    next_art = None
    if get_step_meta(next_step):
        next_art = await get_or_create_center_artifact(workspace_id, next_step)
    return {"artifact": art, "center": center, "next_step": next_step if next_art else None, "next_artifact": next_art}


async def get_state(workspace_id: int) -> dict:
    from services import artifact_service as art_svc
    arts = await art_svc.list_artifacts(limit=300)
    by_step: dict[int, dict] = {}
    for a in arts:
        if a.get("workspace_id") != workspace_id: continue
        if a.get("type") != "spec": continue
        data = a.get("data") or {}
        if data.get("phase") != PHASE: continue
        s = data.get("step")
        if s is None: continue
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
            "step": s, "title": meta["title"], "description": meta["description"],
            "status": status, "artifact_id": a.get("id") if a else None,
            "center": center, "history": history,
        })
    return {"workspace_id": workspace_id, "phase": PHASE, "steps": steps_state}


# ──────────────────────────────────────────
# 集約 (4 タブ)
# ──────────────────────────────────────────
TAB_TO_STEP_SECTIONS: dict[str, list[tuple[int, str]]] = {
    "basic_info": [(1, "basic")],
    "items":      [(1, "items")],
    "summary":    [(1, "summary")],
    "terms":      [(1, "payment"), (1, "bank"), (1, "notes")],
}

TAB_LABELS = {
    "all":        "全て",
    "basic_info": "基本情報",
    "items":      "見積項目",
    "summary":    "金額サマリー",
    "terms":      "支払・振込・備考",
}


async def get_aggregated_view(workspace_id: int) -> dict:
    state = await get_state(workspace_id)
    by_step: dict[int, dict] = {s["step"]: s for s in state["steps"]}
    tab_order = ["basic_info", "items", "summary", "terms"]
    tabs_out: list[dict] = []
    for tab_key in tab_order:
        refs = TAB_TO_STEP_SECTIONS.get(tab_key, [])
        if not refs: continue
        source_steps = sorted({step_num for step_num, _ in refs})
        locked = all((by_step.get(s, {}).get("status") == "not_started") for s in source_steps)
        sections: list[dict] = []
        for step_num, section_key in refs:
            step_state = by_step.get(step_num)
            if not step_state: continue
            for sec in (step_state["center"].get("sections", []) or []):
                if sec.get("key") == section_key:
                    sections.append({
                        "key": sec["key"], "label": sec.get("label", section_key),
                        "items": sec.get("items", []) or [], "source_step": step_num,
                    })
                    break
        tabs_out.append({
            "key": tab_key, "label": TAB_LABELS.get(tab_key, tab_key),
            "locked": locked, "source_steps": source_steps, "sections": sections,
        })
    return {
        "workspace_id": workspace_id, "phase": PHASE,
        "tabs": tabs_out,
        "step_status": {s["step"]: s["status"] for s in state["steps"]},
    }


# ──────────────────────────────────────────
# 出力
# ──────────────────────────────────────────
def _items_to_md(items: list[str]) -> str:
    return "\n".join(f"- {it}" for it in items) if items else "_(まだ記入されていません)_"


def _html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _items_to_html_list(items: list[str]) -> str:
    if not items: return '<p style="color:#94A3B8;font-size:13px;">(未記入)</p>'
    return "<ul>\n" + "\n".join(f"  <li>{_html_escape(it)}</li>" for it in items) + "\n</ul>"


async def render_markdown(workspace_id: int, tab: str = "all") -> str:
    view = await get_aggregated_view(workspace_id)
    tabs = {t["key"]: t["sections"] for t in view["tabs"]}
    if tab == "all":
        order = ["basic_info", "items", "summary", "terms"]
        out = ["# 見積書\n"]
        for t in order:
            out.append(f"## {TAB_LABELS[t]}\n")
            sections = tabs.get(t, [])
            if not sections:
                out.append("_(未記入)_\n\n"); continue
            for sec in sections:
                if len(sections) > 1: out.append(f"### {sec.get('label')}\n")
                out.append(_items_to_md(sec.get("items", []))); out.append("\n\n")
        return "\n".join(out)
    label = TAB_LABELS.get(tab, tab)
    out = [f"# {label}\n"]
    sections = tabs.get(tab, [])
    if not sections: out.append("_(未記入)_\n"); return "\n".join(out)
    for sec in sections:
        out.append(f"## {sec.get('label')}\n")
        out.append(_items_to_md(sec.get("items", []))); out.append("\n")
    return "\n".join(out)


async def render_html(workspace_id: int, tab: str = "all") -> str:
    # Phase 5: tab="all" の時は template_render_service 経由で A4 見積書
    if tab == "all":
        try:
            from services import template_render_service as tr
            from services import account_settings_service as acc
            view = await get_aggregated_view(workspace_id)
            async with adb.connect(DB_PATH) as db:
                db.row_factory = adb.Row
                rows = await db.execute_fetchall(
                    "SELECT account_id FROM workspaces WHERE id=?", (workspace_id,))
            account_id = (dict(rows[0]).get("account_id", 1) if rows else 1)
            settings = await acc.get_or_create_default(account_id)
            estimate_data = _flatten_estimate_for_render(view.get("tabs", []), settings)
            return tr.render_estimate_html(settings=settings, estimate_data=estimate_data)
        except Exception as e:
            print(f"[estimate] template render failed, fallback: {e}")
    return await _render_html_fallback(workspace_id, tab)


def _flatten_estimate_for_render(tabs: list[dict], settings: dict) -> dict:
    """estimate aggregated tabs から render_estimate_html 用 dict に変換。"""
    by_tab = {t.get("key"): t for t in tabs or []}
    today = __import__("datetime").date.today()
    return {
        "estimate_number": f"{settings.get('estimate_prefix','EST')}-{today.strftime('%Y%m%d')}-001",
        "issue_date":      today.isoformat(),
        "expiry_date":     (today + __import__("datetime").timedelta(days=settings.get("estimate_validity_days", 30) or 30)).isoformat(),
        "client_name":     "(クライアント名)",
        "client_contact":  "",
        "project_title":   "御見積書",
        "items": [],
        "subtotal": 0, "tax": 0, "total": 0,
        "payment_terms": settings.get("payment_terms_default", "30/30/40"),
        "notes": settings.get("default_notes") or [],
    }


async def _render_html_fallback(workspace_id: int, tab: str = "all") -> str:
    view = await get_aggregated_view(workspace_id)
    tabs = {t["key"]: t["sections"] for t in view["tabs"]}
    targets = ["basic_info", "items", "summary", "terms"] if tab == "all" else [tab]
    body_parts = []
    for i, t in enumerate(targets, 1):
        if t not in TAB_LABELS: continue
        label = TAB_LABELS[t]
        sections = tabs.get(t, [])
        inner = []
        for sec in sections:
            if len(sections) > 1:
                inner.append(f'<h3>{_html_escape(sec.get("label", ""))}</h3>')
            inner.append(_items_to_html_list(sec.get("items", [])))
        body_parts.append(f'''
<div class="section-card" id="{t}" data-bf-tab="{t}">
  <div class="section-header"><div class="section-num">{i}</div><div class="section-title">{label}</div></div>
  {"".join(inner) if inner else '<p style="color:#94A3B8;font-size:13px;">(未記入)</p>'}
</div>''')
    body_html = "\n".join(body_parts)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>見積書 — {TAB_LABELS.get(tab, tab)}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+JP:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Inter','Noto Sans JP',sans-serif; background: #F5F7FA; color: #0F172A; padding: 32px; line-height: 1.7; }}
  .container {{ max-width: 980px; margin: 0 auto; }}
  h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
  .meta {{ font-size: 13px; color: #64748B; margin-bottom: 32px; }}
  .section-card {{ background: #fff; border: 1px solid #E4E8EE; border-radius: 8px; padding: 24px 28px; margin-bottom: 16px; }}
  .section-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }}
  .section-num {{ width: 32px; height: 32px; background: #004CD9; color: #fff; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-weight: 700; }}
  .section-title {{ font-size: 18px; font-weight: 700; }}
  ul {{ list-style: disc; padding-left: 24px; }}
  li {{ font-size: 14px; line-height: 1.7; color: #334155; margin-bottom: 4px; }}
  h3 {{ font-size: 15px; font-weight: 700; color: #0F172A; margin: 16px 0 8px; }}
</style>
</head>
<body>
<div class="container">
  <h1>見積書</h1>
  <div class="meta">タブ: {TAB_LABELS.get(tab, tab)} ・ Build-Factory 自動生成</div>
  {body_html}
</div>
</body>
</html>
"""


async def render_json(workspace_id: int, tab: str = "all") -> dict:
    view = await get_aggregated_view(workspace_id)
    if tab == "all":
        return {
            "workspace_id": workspace_id, "phase": PHASE,
            "step_status": view["step_status"], "tabs": view["tabs"],
        }
    tabs = {t["key"]: t for t in view["tabs"]}
    t = tabs.get(tab) or {}
    return {
        "workspace_id": workspace_id, "phase": PHASE,
        "tab": tab, "label": TAB_LABELS.get(tab, tab),
        "sections": t.get("sections", []),
    }
