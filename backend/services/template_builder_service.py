"""
template_builder_service.py — Phase 0 (テンプレビルダー) 対話駆動フロー

6 STEP 構成 (template-builder スキルに従う):
  1. 業務情報・読者像
  2. ブランドデザイン
  3. 実績・事例セクション
  4. プラン構成
  5. 任意セクション
  6. プレビュー & 保存

完了時に `account_settings.template_config` に最終 JSON を保存。
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


SKILL_PATH = Path.home() / ".claude" / "skills" / "template-builder" / "SKILL.md"

PHASE = "template_builder"


STEPS = [
    {"step": 1, "title": "業務情報・読者像",
     "description": "業種・読者・目的を確認して推奨セクション構成を提案",
     "core_sections": [
         {"key": "industry", "label": "業種・業務形態"},
         {"key": "audience", "label": "想定読者"},
         {"key": "purpose",  "label": "提案書の目的"},
         {"key": "tone",     "label": "見せ方の方向性"},
     ]},
    {"step": 2, "title": "ブランドデザイン",
     "description": "プライマリ色・フォント・ロゴ・印鑑を確定",
     "core_sections": [
         {"key": "design_color",   "label": "カラーパレット"},
         {"key": "design_font",    "label": "フォント"},
         {"key": "design_logo",    "label": "ロゴ"},
         {"key": "design_stamp",   "label": "印鑑"},
     ]},
    {"step": 3, "title": "実績・事例セクション",
     "description": "実績統計・過去事例の件数とレイアウトを設計",
     "core_sections": [
         {"key": "stats_design",   "label": "実績統計の設計"},
         {"key": "cases_design",   "label": "過去事例の設計"},
     ]},
    {"step": 4, "title": "プラン構成",
     "description": "プラン提示の有無と各プランの価格・機能を決定",
     "core_sections": [
         {"key": "plan_count",     "label": "プラン数 (なし/1/3/5)"},
         {"key": "plan_details",   "label": "各プランの詳細"},
         {"key": "plan_layout",    "label": "プラン表示レイアウト"},
     ]},
    {"step": 5, "title": "任意セクション",
     "description": "会社紹介・FAQ・お客様の声などのオプションセクション",
     "core_sections": [
         {"key": "extra_sections", "label": "追加セクション選択"},
         {"key": "section_order",  "label": "セクション並び順"},
     ]},
    {"step": 6, "title": "プレビュー & 保存",
     "description": "全セクションをプレビュー確認し、template_config に保存",
     "core_sections": [
         {"key": "final_config",   "label": "最終テンプレ構成"},
     ]},
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
# DB ヘルパー (アカウント単位の chat / artifact)
# ──────────────────────────────────────────
async def _save_message(account_id: int, step: int, role: str, content: str, metadata: dict = None) -> int:
    """テンプレビルダーは workspace_id ではなく account_id 単位なので、metadata に格納。"""
    async with adb.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO chat_messages (workspace_id, phase, step, role, content, metadata)
               VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
            (0, PHASE, step, role, content,
             json.dumps({**(metadata or {}), "account_id": account_id}, ensure_ascii=False)),
        )
        row = await cur.fetchone()
        await db.commit()
        return row["id"] if row else 0


async def get_chat_history(account_id: int, step: int) -> list[dict]:
    async with adb.connect(DB_PATH) as db:
        db.row_factory = adb.Row
        rows = await db.execute_fetchall(
            """SELECT id, role, content, metadata, created_at
               FROM chat_messages
               WHERE phase=? AND step=?
               ORDER BY id""",
            (PHASE, step),
        )
    out = []
    for r in rows:
        d = dict(r)
        try:
            md = json.loads(d["metadata"]) if isinstance(d["metadata"], str) else (d["metadata"] or {})
        except Exception:
            md = {}
        if md.get("account_id") == account_id:
            d["metadata"] = md
            out.append(d)
    return out


async def get_or_create_session_state(account_id: int, step: int) -> dict:
    """テンプレビルダーは artifact ではなく account_settings.template_config 内に session を保持。"""
    from services import account_settings_service as acc
    settings = await acc.get_or_create_default(account_id)
    config = settings.get("template_config") or {}

    # template_config["_builder_session"] にステップごとの center を保持
    sess = config.get("_builder_session") or {}
    sess_step = sess.get(f"step{step}") or empty_center_state(step)
    return {
        "settings": settings,
        "config": config,
        "session": sess,
        "current": sess_step,
    }


async def save_session_state(account_id: int, step: int, center: dict, status: str = "draft") -> dict:
    from services import account_settings_service as acc
    settings = await acc.get_or_create_default(account_id)
    config = dict(settings.get("template_config") or {})
    sess = dict(config.get("_builder_session") or {})
    sess[f"step{step}"] = center
    sess[f"step{step}_status"] = status
    config["_builder_session"] = sess

    await acc.upsert_settings(account_id, {"template_config": config})
    return center


# ──────────────────────────────────────────
# プロンプト
# ──────────────────────────────────────────
def _load_skill_md() -> str:
    if SKILL_PATH.exists():
        return SKILL_PATH.read_text(encoding="utf-8")
    return ""


def _extract_common_rules(skill_md: str) -> str:
    m = re.search(r"##\s*🧠\s*全スキル共通[\s\S]*?(?=\n##\s|\Z)", skill_md)
    if m:
        return m.group(0).strip()
    return skill_md[:5000]


def _extract_step_section(skill_md: str, step: int) -> str:
    pattern = rf"###\s*▶\s*STEP\s*{step}[：:][\s\S]*?(?=###\s*▶\s*STEP\s*{step+1}|\n##\s|\Z)"
    m = re.search(pattern, skill_md)
    if m:
        return m.group(0).strip()
    return ""


def _build_system_prompt(step: int, center_state: dict, settings: dict, knowledge_hits: list[dict] | None = None) -> str:
    meta = get_step_meta(step) or {}
    skill_md = _load_skill_md()
    common_rules = _extract_common_rules(skill_md)
    step_section = _extract_step_section(skill_md, step)
    if not step_section:
        step_section = f"(STEP {step} セクションが見つかりません)"

    issuer_summary = ""
    if settings:
        issuer_summary = "# 既存の account_settings (発行者情報)\n```json\n" + \
            json.dumps({
                "company_name": settings.get("company_name"),
                "primary_color": settings.get("primary_color"),
                "achievement_stats": settings.get("achievement_stats"),
                "case_studies_count": len(settings.get("case_studies") or []),
                "logo_url": settings.get("logo_url"),
                "stamp_url": settings.get("stamp_url"),
                "template_config": settings.get("template_config") or {},
            }, ensure_ascii=False, indent=2)[:3000] + "\n```"

    knowledge_summary = ""
    if knowledge_hits:
        knowledge_summary = "# ナレッジ参照 (過去案件の素材)\n" + \
            "\n".join(f"- {k.get('title','(no title)')} (id={k.get('id')})" for k in knowledge_hits[:8])

    return f"""あなたは「ビジネスデザイナー兼テンプレートアーキテクト」です。
ENGINE BASE / Build-Factory のアカウント所有者と対話し、その人専用の User Base Template を組み立てる役割を担います。
template-builder スキル (~/.claude/skills/template-builder/SKILL.md) に従って動作してください。

# 共通動作ルール
{common_rules}

# あなたの今の作業: STEP {step}
{step_section}

{issuer_summary}

{knowledge_summary}

# Build-Factory UI 制約 (重要)
1. 対話駆動: 1 メッセージは 1-3 文 + 質問 1-2 個まで。長文禁止。
2. 既存 account_settings を尊重: ユーザーの会社情報・実績は既に入力されている可能性。上書きするときは理由を明示。
3. STEP ごとに center_patch で session を更新: 結論を items に書く (「業種: IT 受託」「読者: 経営層」のように)
4. 業種に合わせて推奨: IT 受託 / SaaS / コンサル等でセクション構成を変える
5. 絵文字禁止
6. 【仮説】ラベル: 確証のない部分には先頭に「【仮説】」を付ける
7. STEP 完了判定: コア項目が埋まったら "ready_to_complete": true

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
    {{ "section_key": "industry", "operation": "add" | "update" | "remove", "items": ["箇条書き項目"] }}
  ],
  "ready_to_complete": false,
  "internal_note": ""
}}

JSON 以外の文字列は一切返さない。"""


# ──────────────────────────────────────────
# LLM
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
            max_tokens=2500,
            temperature=0.3,
        )
        text = (resp.choices[0].message.content or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif text.startswith("```"):
            text = text.strip("`").lstrip("\n")
        return json.loads(text)
    except Exception as e:
        print(f"[template-builder] LLM error: {e}")
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
# ナレッジ統合 (過去案件 artifact 参照)
# ──────────────────────────────────────────
async def find_relevant_knowledge(account_id: int, query_keywords: list[str]) -> list[dict]:
    """過去の完了案件 artifact から関連するものを検索。
    type='spec' で phase が proposal/estimate のもので status='confirmed' なものを引く。"""
    from services import artifact_service as art
    items = await art.list_artifacts(limit=300)
    out = []
    keywords_lower = [k.lower() for k in (query_keywords or [])]
    for a in items or []:
        if a.get("type") not in ("spec", "knowledge"):
            continue
        data = a.get("data") or {}
        if a.get("type") == "spec" and data.get("status") != "confirmed":
            continue
        title = (a.get("title") or "").lower()
        tags = " ".join(a.get("category_tags") or []).lower()
        if not keywords_lower or any(kw in title or kw in tags for kw in keywords_lower):
            out.append({
                "id": a.get("id"),
                "title": a.get("title"),
                "type": a.get("type"),
                "phase": data.get("phase"),
                "tags": a.get("category_tags") or [],
            })
    return out[:10]


# ──────────────────────────────────────────
# メインフロー
# ──────────────────────────────────────────
async def start_step(account_id: int, step: int) -> dict:
    if not get_step_meta(step):
        return {"error": f"unknown step: {step}"}

    state = await get_or_create_session_state(account_id, step)
    settings = state["settings"]
    center = state["current"]

    history = await get_chat_history(account_id, step)
    if history:
        return {
            "settings": settings,
            "center": center,
            "history": history,
            "ai_message": history[-1]["content"] if history[-1]["role"] == "ai" else None,
        }

    knowledge_hits = await find_relevant_knowledge(account_id, [])
    system = _build_system_prompt(step, center, settings, knowledge_hits)
    user_kickoff = f"STEP {step} を始めてください。既存の account_settings を踏まえて推奨を提示してください。"
    llm_out = await _call_llm(system, [{"role": "user", "content": user_kickoff}])

    chat_msg = llm_out.get("chat_message", "STEP を始めます。")
    center = apply_center_patch(center, llm_out.get("center_patch", []))

    await _save_message(account_id, step, "system", "STEP 開始", {})
    msg_id = await _save_message(account_id, step, "ai", chat_msg, {"step_started": True})
    await save_session_state(account_id, step, center)

    return {
        "settings": settings,
        "center": center,
        "ai_message": chat_msg,
        "ai_message_id": msg_id,
        "ready_to_complete": llm_out.get("ready_to_complete", False),
    }


async def reply(account_id: int, step: int, user_message: str) -> dict:
    state = await get_or_create_session_state(account_id, step)
    settings = state["settings"]
    center = state["current"]
    history = await get_chat_history(account_id, step)

    await _save_message(account_id, step, "user", user_message)

    llm_messages = []
    for h in history:
        if h["role"] in ("user", "ai"):
            llm_messages.append({
                "role": "assistant" if h["role"] == "ai" else "user",
                "content": h["content"],
            })
    llm_messages.append({"role": "user", "content": user_message})

    knowledge_hits = await find_relevant_knowledge(account_id, [])
    system = _build_system_prompt(step, center, settings, knowledge_hits)
    llm_out = await _call_llm(system, llm_messages)

    chat_msg = llm_out.get("chat_message", "(応答なし)")
    patch = llm_out.get("center_patch", [])
    new_center = apply_center_patch(center, patch)
    ready = bool(llm_out.get("ready_to_complete", False))

    msg_id = await _save_message(account_id, step, "ai", chat_msg, {"ready": ready})
    await save_session_state(account_id, step, new_center)

    return {
        "settings": settings,
        "center": new_center,
        "ai_message": chat_msg,
        "ai_message_id": msg_id,
        "patch": patch,
        "ready_to_complete": ready,
    }


async def complete_step(account_id: int, step: int) -> dict:
    state = await get_or_create_session_state(account_id, step)
    center = state["current"]
    await save_session_state(account_id, step, center, status="confirmed")

    next_step = step + 1
    if not get_step_meta(next_step):
        # 全 STEP 完了 → template_config に最終構造を構築
        final_config = await _build_final_config(account_id)
        from services import account_settings_service as acc
        await acc.upsert_settings(account_id, {"template_config": final_config})
        return {"finished": True, "template_config": final_config, "next_step": None}

    return {"finished": False, "next_step": next_step}


async def _build_final_config(account_id: int) -> dict:
    """全 STEP の session を統合して最終 template_config を生成。"""
    from services import account_settings_service as acc
    settings = await acc.get_or_create_default(account_id)
    config = settings.get("template_config") or {}
    sess = config.get("_builder_session") or {}

    # 簡易統合 (詳細は STEP 6 で AI が組み立てる想定)
    final = {
        "design": {
            "primary_color":   settings.get("primary_color", "#004CD9"),
            "secondary_color": settings.get("secondary_color"),
            "font_family":     settings.get("font_family", "Noto Sans JP"),
            "logo_url":        settings.get("logo_url"),
            "stamp_url":       settings.get("stamp_url"),
        },
        "sections": _default_sections_from_session(sess),
        "plans": _extract_plans_from_session(sess),
        "extra_pages": [],
        "_builder_session": sess,  # session も残す (再編集可)
    }
    return final


def _default_sections_from_session(sess: dict) -> list[dict]:
    """STEP 1 / 5 のセッションからセクション一覧を組み立てる。簡易版。"""
    return [
        {"key": "cover", "enabled": True},
        {"key": "executive_summary", "enabled": True},
        {"key": "company_intro", "enabled": False},
        {"key": "achievements", "enabled": True, "config": {"layout": "grid", "stat_count": 6}},
        {"key": "case_studies", "enabled": True, "config": {"count": 3, "layout": "card"}},
        {"key": "problem", "enabled": True},
        {"key": "solution", "enabled": True},
        {"key": "plans", "enabled": False},
        {"key": "roi", "enabled": True},
        {"key": "scope", "enabled": True},
        {"key": "schedule", "enabled": True},
        {"key": "cost", "enabled": True},
        {"key": "risk_team", "enabled": True},
        {"key": "testimonials", "enabled": False},
        {"key": "faq", "enabled": False},
        {"key": "closing_cta", "enabled": True},
    ]


def _extract_plans_from_session(sess: dict) -> list[dict]:
    """STEP 4 のセッションから plans 配列を抽出。詳細未実装のため空返し。"""
    return []


async def get_state(account_id: int) -> dict:
    state = await get_or_create_session_state(account_id, 1)
    settings = state["settings"]
    sess = (settings.get("template_config") or {}).get("_builder_session") or {}

    steps_state = []
    for meta in STEPS:
        s = meta["step"]
        history = await get_chat_history(account_id, s)
        center = sess.get(f"step{s}") or empty_center_state(s)
        status = sess.get(f"step{s}_status") or ("draft" if history else "not_started")
        steps_state.append({
            "step": s, "title": meta["title"], "description": meta["description"],
            "status": status, "center": center, "history": history,
        })

    return {
        "account_id": account_id,
        "phase": PHASE,
        "steps": steps_state,
        "template_config": settings.get("template_config") or {},
    }
