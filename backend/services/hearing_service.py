"""
hearing_service.py — Phase 1 (ヒアリング) 対話駆動フロー

各 STEP は対話ループで進行:
  1. start_step    → AI が STEP 開始メッセージ + 最初の質問を生成
  2. reply         → user 回答を受け、AI 次発話 + 中央エリアの構造化更新
  3. complete_step → 現 STEP の最終 artifact を確定 (中央エリアの内容)

中央エリア (center) は構造化された JSON (sections + items) で管理し、
フロントエンドは Markdown にレンダリングして表示する。
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional
from pathlib import Path

from db import async_db as adb
from db.queries import DB_PATH
from llm.config import LLMProvider, get_openai_client


HEARING_SKILL_PATH = Path.home() / ".claude" / "skills" / "hearing" / "SKILL.md"


# ──────────────────────────────────────────
# STEP メタ
# ──────────────────────────────────────────
STEPS = [
    {
        "step": 1,
        "title": "プロジェクトの全体像と動機",
        "description": "作りたいもの・背景・期限・規模感を整理し、背後のニーズ仮説を立てる",
        "core_sections": [
            {"key": "overview",       "label": "プロジェクト概要"},
            {"key": "hypotheses",     "label": "【仮説】背後のニーズ"},
            {"key": "unresolved",     "label": "確認したいこと (未解決)"},
        ],
    },
    {
        "step": 2,
        "title": "要件・制約・ステークホルダー",
        "description": "機能候補・制約 (期限/予算/技術)・関係者を整理",
        "core_sections": [
            {"key": "requirements",   "label": "言及された機能・要件"},
            {"key": "constraints",    "label": "制約"},
            {"key": "stakeholders",   "label": "ステークホルダー"},
            {"key": "unresolved",     "label": "確認したいこと (未解決)"},
        ],
    },
    {
        "step": 3,
        "title": "優先順位・開発方針",
        "description": "Must/Should/Could/Won't 分類と MVP コンセプトを決める",
        "core_sections": [
            {"key": "must",           "label": "Must (これがないと価値がない)"},
            {"key": "should",         "label": "Should (あると大幅に良くなる)"},
            {"key": "could",          "label": "Could (余裕があれば)"},
            {"key": "wont",           "label": "Won't (今回はやらない)"},
            {"key": "mvp_concept",    "label": "MVP のイメージ"},
            {"key": "risks",          "label": "リスクと懸念事項"},
        ],
    },
    {
        "step": 4,
        "title": "最終出力 (3 形式)",
        "description": "ヒアリングサマリー Markdown + 起点 JSON + 議事録の整理",
        "core_sections": [
            {"key": "summary",        "label": "ヒアリングサマリー"},
            {"key": "next_steps",     "label": "次フェーズへの引き継ぎ"},
        ],
    },
]


def get_step_meta(step_num: int) -> Optional[dict]:
    for s in STEPS:
        if s["step"] == step_num:
            return s
    return None


def empty_center_state(step_num: int) -> dict:
    """新規 STEP の空状態を生成。core_sections を空配列で初期化。"""
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
async def _save_message(workspace_id: int, phase: str, step: int, role: str, content: str, metadata: dict = None) -> int:
    async with adb.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO chat_messages (workspace_id, phase, step, role, content, metadata)
               VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
            (workspace_id, phase, step, role, content, json.dumps(metadata or {}, ensure_ascii=False)),
        )
        row = await cur.fetchone()
        await db.commit()
        return row["id"] if row else 0


async def get_chat_history(workspace_id: int, phase: str, step: int) -> list[dict]:
    async with adb.connect(DB_PATH) as db:
        db.row_factory = adb.Row
        rows = await db.execute_fetchall(
            """SELECT id, role, content, metadata, created_at
               FROM chat_messages
               WHERE workspace_id=? AND phase=? AND step=?
               ORDER BY id""",
            (workspace_id, phase, step),
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
    """STEP の中央エリア用 artifact を取得 or 作成。"""
    from services import artifact_service as art

    # 既存検索
    items = await art.list_artifacts(limit=200)
    for a in items:
        if a.get("workspace_id") != workspace_id:
            continue
        if a.get("type") != "spec":
            continue
        data = a.get("data") or {}
        if data.get("phase") == "hearing" and data.get("step") == step and not data.get("archived_version"):
            return a

    # 無ければ新規作成
    initial = empty_center_state(step)
    meta = get_step_meta(step)
    title = f"ヒアリング STEP {step}: {meta['title']}" if meta else f"ヒアリング STEP {step}"
    created = await art.create_artifact(
        type="spec",
        title=title,
        data={
            "phase": "hearing",
            "step": step,
            "version": 1,
            "status": "draft",
            "center": initial,
        },
        category_tags=["hearing", f"step-{step}"],
        created_by="ai:pm",
        actor="ai:pm",
    )
    # workspace_id を後付け
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
    return await art.update_artifact(artifact_id, data=data, actor="ai:pm", note="hearing center update")


# ──────────────────────────────────────────
# LLM プロンプト構築
# ──────────────────────────────────────────
def _load_skill_md() -> str:
    if HEARING_SKILL_PATH.exists():
        return HEARING_SKILL_PATH.read_text(encoding="utf-8")
    return "# hearing skill (not found, using fallback)"


def _extract_common_rules(skill_md: str) -> str:
    """skill md の冒頭「思考品質基準」～「出力フォーマット厳守」までを抽出。"""
    import re
    # 「## 全スキル共通：思考品質基準」開始 ～ 「# hearing スキル」直前 まで
    m = re.search(r"##\s*\U0001F9E0\s*全スキル共通[\s\S]*?(?=\n#\s*hearing\s*スキル|\Z)", skill_md)
    if m:
        return m.group(0).strip()
    # フォールバック: 最初の 5000 文字
    return skill_md[:5000]


def _extract_step_section(skill_md: str, step: int) -> str:
    """指定 STEP のセクションを抽出 (### [arrow] STEP {n}: ... から次の STEP / 最終出力 まで)。"""
    import re
    _arrow = chr(0x25B6)  # BLACK RIGHT-POINTING TRIANGLE
    pattern = rf"###\s*{_arrow}\s*STEP\s*{step}[\s\S]*?(?=###\s*{_arrow}\s*STEP\s*{step+1}|\n##\s|\Z)"
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
            account_id=account_id, doc_type="hearing_reference",
            keywords=keywords, limit=2,
        )
        if not block:
            block = await ing.build_references_context_block(
                account_id=account_id, doc_type=None,
                keywords=keywords, limit=2,
            )
        return block or ""
    except Exception as e:
        print(f"[hearing] references fetch failed: {e}")
        return ""


def _build_system_prompt(step: int, center_state: dict) -> str:
    meta = get_step_meta(step) or {}
    skill_md = _load_skill_md()
    common_rules = _extract_common_rules(skill_md)
    step_section = _extract_step_section(skill_md, step)
    if not step_section:
        step_section = f"(STEP {step} セクションが見つかりませんでした)"

    return f"""あなたは「PM AI」です。Build-Factory プロジェクトのヒアリングを担当します。
hearing スキル (~/.claude/skills/hearing/SKILL.md) に従って厳密に動作してください。

# 共通動作ルール (全 STEP 共通・絶対遵守)
{common_rules}

# あなたの今の作業: STEP {step}
{step_section}

# Build-Factory UI 制約 (重要)
1. **対話駆動**: チャットで PM (人間) と短いキャッチボール。1 メッセージは 1-3 文 + 質問 1-2 個まで。長文禁止。
2. **質問設計の基準を遵守**: スキルの STEP {step} に書かれた具体的な質問テンプレート (a/b/c のサブ質問など) を使う。汎用質問 (「どんなプロジェクトですか?」等) は禁止。
3. **深掘りチェック**: スキルの「深掘りチェック」表に書かれた観点を毎回確認。曖昧な回答は具体例・選択肢で深掘り。
4. **ドメインスキャン**: PM の業界が判明したら、対応する法律・規制・制度を質問の中で必ず触れる。
5. **複数解釈処理**: 曖昧な発言には複数解釈を提示して確認する。
6. **中央エリアにリアルタイム反映**: PM の回答から得た情報を即座に center_patch で出力。
7. **絵文字禁止**: UI に表示されるため、絵文字を一切使わない。日本語のみ。
8. **【仮説】ラベル**: 聞けていない部分を推測した場合は、items 内で先頭に「【仮説】」を付ける。
9. **STEP 完了判定**: STEP のコア項目が十分埋まり、未解決の確認事項が大筋解消したら "ready_to_complete": true。

# 中央エリアのセクション構造 (STEP {step})
{json.dumps(meta.get('core_sections', []), ensure_ascii=False, indent=2)}

# 現在の中央エリアの状態 (PM が手動編集している場合はそれが最新)
```json
{json.dumps(center_state, ensure_ascii=False, indent=2)}
```

# PM 手動編集の取り扱い (重要)
- center_state の各セクションには PM の最新編集が反映されています。
- 「最終更新者勝ち」(last write wins) — AI が更新する妥当な理由があれば上書き OK。
- 上書きする場合は chat_message で必ず「○○を更新しました」と PM に伝える。
- PM の意図に反する不要な書き換えは避けること。

# 出力形式 (必ず以下の JSON だけを返す。コードフェンスもなし。)
{{
  "chat_message": "PM への次の発話 (1-3 文 + 質問 1-2 個。スキルの質問テンプレートに沿った具体的なもの)",
  "center_patch": [
    {{
      "section_key": "overview",
      "operation": "add" | "update" | "remove",
      "items": ["箇条書き項目。【仮説】ラベルは仮説のみ"]
    }}
  ],
  "ready_to_complete": false,
  "internal_note": "(任意) 何を判断したかの 1 行メモ。デバッグ用。空でも可"
}}

JSON 以外の文字列 (説明・挨拶・コードフェンス) は一切返さない。文字列内の改行は \\n。"""


# ──────────────────────────────────────────
# メインフロー
# ──────────────────────────────────────────
def _autodetect_provider() -> tuple[LLMProvider, str]:
    """利用可能な LLM を自動検出。優先順位: env 明示 > OpenAI 実キー > Anthropic 実キー > Ollama"""
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
        return bool(k) and not k.startswith("sk-ant-xxxx") and not k.startswith("sk-proj-xxxx") and "xxxxx" not in k.lower()

    if _is_real(openai_key):
        return LLMProvider.OPENAI, "gpt-4o"
    if _is_real(anth):
        return LLMProvider.CLAUDE, "claude-sonnet-4-6"
    return LLMProvider.OLLAMA, "qwen2.5:7b"


async def _call_llm(system: str, messages: list[dict]) -> dict:
    """LLM を呼んで JSON 出力を取得。失敗時は最低限の reply で fallback。"""
    provider, model = _autodetect_provider()

    try:
        client = get_openai_client(provider, dict(os.environ))
        # Anthropic OpenAI 互換 (https://docs.anthropic.com/en/api/openai-sdk) を期待
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, *messages],
            max_tokens=2000,
            temperature=0.3,
        )
        text = (resp.choices[0].message.content or "").strip()
        # JSON 抽出 (```json ... ``` を許容)
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif text.startswith("```"):
            text = text.strip("`").lstrip("\n")
        return json.loads(text)
    except Exception as e:
        print(f"[hearing] LLM error: {e}")
        return {
            "chat_message": "(AI 応答の取得に失敗しました。もう一度送信してください)",
            "center_patch": [],
            "ready_to_complete": False,
            "error": str(e),
        }


def apply_center_patch(center: dict, patch: list[dict]) -> dict:
    """center_patch を center 状態に適用。in-place ではなく新しい dict を返す。"""
    new_center = json.loads(json.dumps(center))  # deep copy
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
            # 自由セクションとして新規追加
            label = op.get("label", key)
            sec = {"key": key, "label": label, "items": []}
            new_center.setdefault("free_sections", []).append(sec)
            free[key] = sec

        existing = sec.setdefault("items", [])
        if operation == "remove":
            sec["items"] = [it for it in existing if it not in items]
        elif operation == "update":
            sec["items"] = items
        else:  # add (重複は除外)
            for it in items:
                if it not in existing:
                    existing.append(it)

    return new_center


async def start_step(workspace_id: int, step: int) -> dict:
    """STEP 開始。AI が起動メッセージ + 最初の質問を生成して返す。"""
    if not get_step_meta(step):
        return {"error": f"unknown step: {step}"}

    art = await get_or_create_center_artifact(workspace_id, step)
    center = (art.get("data") or {}).get("center") or empty_center_state(step)

    history = await get_chat_history(workspace_id, "hearing", step)
    if history:
        # 既に開始済 → そのまま既存状態を返す
        return {
            "artifact": art,
            "center": center,
            "history": history,
            "ai_message": history[-1]["content"] if history[-1]["role"] == "ai" else None,
        }

    # 新規開始
    system = _build_system_prompt(step, center)
    references_block = await _get_references_block(workspace_id)
    if references_block:
        system = system + "\n\n" + references_block
    user_kickoff = f"STEP {step} を始めてください。最初の質問をお願いします。"
    llm_out = await _call_llm(system, [{"role": "user", "content": user_kickoff}])

    chat_msg = llm_out.get("chat_message", "STEP を始めます。よろしくお願いします。")
    center = apply_center_patch(center, llm_out.get("center_patch", []))

    # DB 反映
    await _save_message(workspace_id, "hearing", step, "system", "STEP 開始", {})
    msg_id = await _save_message(workspace_id, "hearing", step, "ai", chat_msg, {"step_started": True})
    art = await update_center_artifact(art["id"], center)

    return {
        "artifact": art,
        "center": center,
        "ai_message": chat_msg,
        "ai_message_id": msg_id,
        "ready_to_complete": llm_out.get("ready_to_complete", False),
    }


async def reply(workspace_id: int, step: int, user_message: str) -> dict:
    """ユーザー回答を受けて、AI 次発話 + center 更新を返す。"""
    art = await get_or_create_center_artifact(workspace_id, step)
    center = (art.get("data") or {}).get("center") or empty_center_state(step)
    history = await get_chat_history(workspace_id, "hearing", step)

    # ユーザー発話保存
    await _save_message(workspace_id, "hearing", step, "user", user_message)

    # LLM 用履歴 (system は別)
    llm_messages = []
    for h in history:
        if h["role"] in ("user", "ai"):
            llm_messages.append({
                "role": "assistant" if h["role"] == "ai" else "user",
                "content": h["content"],
            })
    llm_messages.append({"role": "user", "content": user_message})

    system = _build_system_prompt(step, center)
    ref_kw = [w for w in (user_message or "").split() if len(w) >= 2][:8]
    references_block = await _get_references_block(workspace_id, keywords=ref_kw or None)
    if references_block:
        system = system + "\n\n" + references_block
    llm_out = await _call_llm(system, llm_messages)

    chat_msg = llm_out.get("chat_message", "(応答なし)")
    patch = llm_out.get("center_patch", [])
    new_center = apply_center_patch(center, patch)
    ready = bool(llm_out.get("ready_to_complete", False))

    msg_id = await _save_message(
        workspace_id, "hearing", step, "ai", chat_msg,
        {"patch_applied": patch, "ready_to_complete": ready},
    )
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
    """STEP 完了。artifact の status を confirmed に更新し、次フェーズの可否を判定。"""
    art = await get_or_create_center_artifact(workspace_id, step)
    center = (art.get("data") or {}).get("center") or empty_center_state(step)

    # 軽い整形 (空セクションを除いて並べ替え)
    if "sections" in center:
        center["sections"] = [s for s in center["sections"] if s.get("items")] + \
                             [s for s in center["sections"] if not s.get("items")]

    art = await update_center_artifact(art["id"], center, mark_status="confirmed")

    # 次 STEP があれば自動で空 artifact を用意 (UI で見えるように)
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
    """ワークスペースのヒアリング全体状態を取得。各 STEP の center + history + status。"""
    from services import artifact_service as art_svc

    arts = await art_svc.list_artifacts(limit=200)
    by_step: dict[int, dict] = {}
    for a in arts:
        if a.get("workspace_id") != workspace_id:
            continue
        if a.get("type") != "spec":
            continue
        data = a.get("data") or {}
        if data.get("phase") != "hearing":
            continue
        s = data.get("step")
        if s is None:
            continue
        # 同じ step に複数あれば最新を採用 (updated_at)
        if s not in by_step or a.get("updated_at", "") > by_step[s].get("updated_at", ""):
            by_step[s] = a

    steps_state = []
    for meta in STEPS:
        s = meta["step"]
        a = by_step.get(s)
        history = await get_chat_history(workspace_id, "hearing", s)
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

    return {"workspace_id": workspace_id, "phase": "hearing", "steps": steps_state}
