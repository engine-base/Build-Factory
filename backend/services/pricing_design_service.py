"""
pricing_design_service.py — Phase 3 (価格設計 — 案件単位の値付け) 対話駆動フロー

目的: ヒアリング・要件定義の出力を起点に、この案件の見積金額を
コスト・市場相場・顧客価値の 3 軸で試算し、推奨レンジ + 採用見積を確定する。

3 STEP 構成:
  1. 原価試算       (機能別工数・人件費・ツール・外注 → コスト下限)
  2. 市場相場・価値試算 (競合相場 + 顧客 ROI → 中央値・上限)
  3. 推奨レンジ・採用案 (3 軸統合 + PM とすり合わせて採用見積を確定)

中央タブ:
  cost_estimate     原価試算
  market_research   市場相場
  value_calc        価値試算
  recommended_range 推奨レンジ・採用案
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


PRICING_SKILL_PATH = Path.home() / ".claude" / "skills" / "pricing-design" / "SKILL.md"

PHASE = "pricing"


STEPS = [
    {
        "step": 1,
        "title": "原価試算",
        "description": "要件定義から各機能の工数を見積もり、人件費・ツール・外注を積み上げて案件のコスト下限を算出",
        "core_sections": [
            {"key": "cost_features",  "label": "機能別工数試算"},
            {"key": "cost_personnel", "label": "人件費試算"},
            {"key": "cost_tools",     "label": "ツール・インフラ費"},
            {"key": "cost_outsource", "label": "外注費"},
            {"key": "cost_total",     "label": "合計コスト (下限)"},
        ],
    },
    {
        "step": 2,
        "title": "市場相場・価値試算",
        "description": "競合相場と顧客 ROI から、中央値および価値ベースの価格上限を算出",
        "core_sections": [
            {"key": "market_competitors", "label": "競合相場 (類似案件)"},
            {"key": "market_position",    "label": "自社ポジション"},
            {"key": "value_roi",          "label": "顧客 ROI 試算"},
            {"key": "value_ceiling",      "label": "価値ベースの価格上限"},
        ],
    },
    {
        "step": 3,
        "title": "推奨レンジ・採用案",
        "description": "3 軸を統合して推奨レンジを算出し、PM とすり合わせて採用見積金額を確定",
        "core_sections": [
            {"key": "range_summary",       "label": "3 軸サマリー (下限・中央・上限)"},
            {"key": "recommended_amount",  "label": "推奨見積金額"},
            {"key": "rationale",           "label": "採用根拠"},
            {"key": "next_steps",          "label": "見積書フェーズへの引き継ぎ事項"},
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
    title = f"価格設計 STEP {step}: {meta['title']}" if meta else f"価格設計 STEP {step}"
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
# 前フェーズ自動引き継ぎ (ヒアリング + 要件定義)
# ──────────────────────────────────────────
async def get_prev_phases_brief(workspace_id: int) -> dict:
    """ヒアリング・要件定義の中央エリアを統合した brief を返す (STEP 1 自動引き継ぎ用)。"""
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
        if ph not in ("hearing", "requirements"):
            continue
        s = data.get("step")
        if s is None:
            continue
        key = (ph, s)
        if key not in by_phase_step or a.get("updated_at", "") > by_phase_step[key].get("updated_at", ""):
            by_phase_step[key] = a

    summary: dict[str, Any] = {"hearing": {}, "requirements": {}}
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
# プロンプト構築
# ──────────────────────────────────────────
def _load_skill_md() -> str:
    if PRICING_SKILL_PATH.exists():
        return PRICING_SKILL_PATH.read_text(encoding="utf-8")
    return ""


def _extract_common_rules(skill_md: str) -> str:
    m = re.search(r"##\s*\U0001F9E0\s*全スキル共通[\s\S]*?(?=\n#\s|\Z)", skill_md)
    if m:
        return m.group(0).strip()
    return skill_md[:5000]


def _extract_step_section(skill_md: str, step: int) -> str:
    _arrow = chr(0x25B6)  # BLACK RIGHT-POINTING TRIANGLE
    pattern = rf"###\s*{_arrow}\s*STEP\s*{step}[：:][\s\S]*?(?=###\s*{_arrow}\s*STEP\s*{step+1}|\n##\s|\Z)"
    m = re.search(pattern, skill_md)
    if m:
        return m.group(0).strip()
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
            account_id=account_id, doc_type="pricing_reference",
            keywords=keywords, limit=2,
        )
        if not block:
            block = await ing.build_references_context_block(
                account_id=account_id, doc_type=None,
                keywords=keywords, limit=2,
            )
        return block or ""
    except Exception as e:
        print(f"[pricing] references fetch failed: {e}")
        return ""


def _build_system_prompt(step: int, center_state: dict, prev_brief: dict) -> str:
    meta = get_step_meta(step) or {}
    skill_md = _load_skill_md()
    common_rules = _extract_common_rules(skill_md)
    step_section = _extract_step_section(skill_md, step)
    if not step_section:
        step_section = f"(STEP {step} セクションが見つかりませんでした。skill md を確認してください)"

    prev_summary = ""
    if prev_brief and (prev_brief.get("hearing") or prev_brief.get("requirements")):
        prev_summary = (
            "# 前フェーズ情報 (ヒアリング + 要件定義)\n"
            "これらを踏まえて価格設計を進めてください。\n```json\n"
            + json.dumps(prev_brief, ensure_ascii=False, indent=2)[:4000]
            + "\n```"
        )

    return f"""あなたは「PM AI / ビジネスストラテジスト」です。Build-Factory のこの案件の見積金額を、コスト・市場相場・顧客価値の 3 軸で試算する役割を担います。
pricing-design スキル (~/.claude/skills/pricing-design/SKILL.md) に従って厳密に動作してください。

# 共通動作ルール
{common_rules}

# 役割 (重要)
このフェーズは **「案件単位の値付け」** です。「自社サービスの料金体系」ではなく、目の前の 1 案件をいくらで請求するかを決めます。
ヒアリング・要件定義の出力をそのまま素材として使い、機能要件を工数換算して原価を積み上げ、競合相場と顧客 ROI を踏まえて推奨レンジを提示してください。
最終決定は PM とのすり合わせを経て行います。AI は **叩き台** を出し、PM の指摘で再計算してください。

# あなたの今の作業: STEP {step}
{step_section}

{prev_summary}

# Build-Factory UI 制約 (重要)
1. 対話駆動: 1 メッセージは 1-3 文 + 質問 1-2 個まで。長文禁止。
2. STEP 1 では要件定義の機能一覧を読んで、自動的に機能別工数 (人日) と人件費を埋めてください。PM が知らない情報があれば質問。
3. STEP 2 では Web 知識から類似案件の競合相場帯を提示し、顧客 ROI の試算根拠を示してください。
4. STEP 3 では「コスト下限・競合中央・価値上限」の 3 軸を統合し、推奨見積金額を 1 つ提案 + 理由を明示。PM が変更したら再計算。
5. 数字には必ず根拠を併記 (例: 「F003 商品検索: 5 人日 (検索 UI + 絞り込み + ページネーションで 1 日ずつ + テスト)」)。
6. 中央エリアにリアルタイム反映: PM の回答から得た情報を center_patch で出力。
7. 絵文字禁止。
8. 【仮説】ラベル: 推測した部分は items 先頭に「【仮説】」を付ける。
9. STEP 完了判定: コア項目が埋まり、PM がレンジ・採用案を承認したら "ready_to_complete": true。

# 中央エリアのセクション構造 (STEP {step})
{json.dumps(meta.get('core_sections', []), ensure_ascii=False, indent=2)}

# 現在の中央エリアの状態 (PM 編集を尊重しつつ、AI による再計算は許可)
```json
{json.dumps(center_state, ensure_ascii=False, indent=2)}
```

# 出力形式 (必ず以下の JSON だけを返す。コードフェンスもなし。)
{{
  "chat_message": "PM への次の発話 (1-3 文 + 質問 1-2 個)",
  "center_patch": [
    {{ "section_key": "cost_features", "operation": "add" | "update" | "remove", "items": ["箇条書き項目"] }}
  ],
  "ready_to_complete": false,
  "internal_note": "(任意) デバッグ用メモ"
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
        print(f"[pricing] LLM error: {e}")
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
    system = _build_system_prompt(step, center, prev_brief)
    references_block = await _get_references_block(workspace_id)
    if references_block:
        system = system + "\n\n" + references_block
    user_kickoff = f"STEP {step} を始めてください。"
    if step == 1 and prev_brief:
        user_kickoff += "\nヒアリング・要件定義の情報を踏まえ、価格設計のすり合わせを開始してください。"
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
    system = _build_system_prompt(step, center, prev_brief)
    ref_kw = [w for w in (user_message or "").split() if len(w) >= 2][:8]
    references_block = await _get_references_block(workspace_id, keywords=ref_kw or None)
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
# 集約 (タブ表示用の統合 view)
# ──────────────────────────────────────────
TAB_TO_STEP_SECTIONS: dict[str, list[tuple[int, str]]] = {
    "cost_estimate": [
        (1, "cost_features"), (1, "cost_personnel"),
        (1, "cost_tools"), (1, "cost_outsource"), (1, "cost_total"),
    ],
    "market_research": [
        (2, "market_competitors"), (2, "market_position"),
    ],
    "value_calc": [
        (2, "value_roi"), (2, "value_ceiling"),
    ],
    "recommended_range": [
        (3, "range_summary"), (3, "recommended_amount"),
        (3, "rationale"), (3, "next_steps"),
    ],
}

TAB_LABELS = {
    "all":               "全て",
    "cost_estimate":     "原価試算",
    "market_research":   "市場相場",
    "value_calc":        "価値試算",
    "recommended_range": "推奨レンジ・採用案",
}


async def get_aggregated_view(workspace_id: int) -> dict:
    state = await get_state(workspace_id)
    by_step: dict[int, dict] = {s["step"]: s for s in state["steps"]}

    tab_order = ["cost_estimate", "market_research", "value_calc", "recommended_range"]
    tabs_out: list[dict] = []
    for tab_key in tab_order:
        refs = TAB_TO_STEP_SECTIONS.get(tab_key, [])
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

        tabs_out.append({
            "key": tab_key,
            "label": TAB_LABELS.get(tab_key, tab_key),
            "locked": locked,
            "source_steps": source_steps,
            "sections": sections,
        })

    return {
        "workspace_id": workspace_id,
        "phase": PHASE,
        "tabs": tabs_out,
        "step_status": {s["step"]: s["status"] for s in state["steps"]},
    }


# ──────────────────────────────────────────
# 出力ファイル生成 (HTML / MD / JSON)
# ──────────────────────────────────────────
def _items_to_md(items: list[str]) -> str:
    return "\n".join(f"- {it}" for it in items) if items else "_(まだ記入されていません)_"


def _html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _items_to_html_list(items: list[str]) -> str:
    if not items:
        return '<p style="color:#94A3B8; font-size:13px;">(未記入)</p>'
    lis = "\n".join(f"  <li>{_html_escape(it)}</li>" for it in items)
    return f"<ul>\n{lis}\n</ul>"


async def render_markdown(workspace_id: int, tab: str = "all") -> str:
    view = await get_aggregated_view(workspace_id)
    tabs = {t["key"]: t["sections"] for t in view["tabs"]}

    if tab == "all":
        order = ["cost_estimate", "market_research", "value_calc", "recommended_range"]
        out = ["# 価格設計書\n"]
        for t in order:
            out.append(f"## {TAB_LABELS[t]}\n")
            sections = tabs.get(t, [])
            if not sections:
                out.append("_(未記入)_\n\n")
                continue
            for sec in sections:
                out.append(f"### {sec.get('label')}\n")
                out.append(_items_to_md(sec.get("items", [])))
                out.append("\n\n")
        return "\n".join(out)

    label = TAB_LABELS.get(tab, tab)
    out = [f"# {label}\n"]
    sections = tabs.get(tab, [])
    if not sections:
        out.append("_(未記入)_\n")
        return "\n".join(out)
    for sec in sections:
        out.append(f"## {sec.get('label')}\n")
        out.append(_items_to_md(sec.get("items", [])))
        out.append("\n")
    return "\n".join(out)


async def render_html(workspace_id: int, tab: str = "all") -> str:
    view = await get_aggregated_view(workspace_id)
    tabs = {t["key"]: t["sections"] for t in view["tabs"]}

    if tab == "all":
        order = ["cost_estimate", "market_research", "value_calc", "recommended_range"]
        body = []
        for i, t in enumerate(order, 1):
            label = TAB_LABELS[t]
            sections = tabs.get(t, [])
            inner = []
            for sec in sections:
                inner.append(f'<h3>{_html_escape(sec.get("label", ""))}</h3>')
                inner.append(_items_to_html_list(sec.get("items", [])))
            body.append(f'''
<div class="section-card" id="{t}" data-bf-tab="{t}">
  <div class="section-header"><div class="section-num">{i}</div><div class="section-title">{label}</div></div>
  {"".join(inner) if inner else '<p style="color:#94A3B8;font-size:13px;">(未記入)</p>'}
</div>''')
        body_html = "\n".join(body)
    else:
        label = TAB_LABELS.get(tab, tab)
        sections = tabs.get(tab, [])
        inner = []
        for sec in sections:
            inner.append(f'<h3>{_html_escape(sec.get("label", ""))}</h3>')
            inner.append(_items_to_html_list(sec.get("items", [])))
        body_html = f'''
<div class="section-card" id="{tab}" data-bf-tab="{tab}">
  <div class="section-header"><div class="section-num">1</div><div class="section-title">{label}</div></div>
  {"".join(inner) if inner else '<p style="color:#94A3B8;font-size:13px;">(未記入)</p>'}
</div>'''

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>価格設計書 — {TAB_LABELS.get(tab, tab)}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+JP:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Inter','Noto Sans JP',sans-serif; background: #F5F7FA; color: #0F172A; padding: 32px; line-height: 1.7; }}
  .container {{ max-width: 980px; margin: 0 auto; }}
  h1 {{ font-size: 28px; font-weight: 700; letter-spacing: -0.01em; margin-bottom: 8px; }}
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
  <h1>価格設計書</h1>
  <div class="meta">タブ: {TAB_LABELS.get(tab, tab)} ・ Build-Factory が自動生成</div>
  {body_html}
</div>
</body>
</html>
"""


async def render_json(workspace_id: int, tab: str = "all") -> dict:
    view = await get_aggregated_view(workspace_id)
    tabs = {t["key"]: t for t in view["tabs"]}
    if tab == "all":
        return {
            "workspace_id": workspace_id,
            "phase": PHASE,
            "step_status": view["step_status"],
            "tabs": view["tabs"],
        }
    t = tabs.get(tab) or {}
    return {
        "workspace_id": workspace_id,
        "phase": PHASE,
        "tab": tab,
        "label": TAB_LABELS.get(tab, tab),
        "sections": t.get("sections", []),
    }
