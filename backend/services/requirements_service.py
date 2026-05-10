"""
requirements_service.py — Phase 2 (要件定義) 対話駆動フロー

7 STEP 構成:
  1. 初期ヒアリング (ヒアリング artifact 引き継ぎ + すり合わせ)
  2. ターゲット・構造設計 (ペルソナ・利用シーン・全体像)
  3. 機能要件詳細 (各機能の入出力・エラー・制約)
  4. 非機能要件・UX・データ構造
  5. 法的考慮・コンプライアンス (ドメイン判定 + ナレッジ + Web 検索)
  6. リスク分析・未確認事項
  7. 最終出力 (HTML / MD / JSON 一括生成)

中央エリアは IDE 風タブで切替表示するため、セクション key を確定:
  overview / users / features / functional / nonfunctional / screens /
  data / integrations / risks / legal / unresolved / history
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


REQ_SKILL_PATH = Path.home() / ".claude" / "skills" / "requirements-definition" / "SKILL.md"
REQ_HTML_TEMPLATE_PATH = Path.home() / ".claude" / "skills" / "requirements-definition" / "assets" / "requirements-template.html"


# ──────────────────────────────────────────
# STEP メタ
# ──────────────────────────────────────────
STEPS = [
    {
        "step": 1,
        "title": "初期ヒアリング・目的明確化",
        "description": "ヒアリングのブリーフをすり合わせ、要件として正式に整理する起点",
        "core_sections": [
            {"key": "overview", "label": "プロジェクト概要"},
            {"key": "challenges", "label": "現状の課題"},
            {"key": "kpi", "label": "成功の定義・KPI"},
            {"key": "constraints_initial", "label": "背景・制約"},
        ],
    },
    {
        "step": 2,
        "title": "ターゲット・構造設計",
        "description": "ペルソナ・利用シーン・システム全体像・主要機能の大分類",
        "core_sections": [
            {"key": "users", "label": "ターゲットユーザー (ペルソナ)"},
            {"key": "scenes", "label": "利用シーン"},
            {"key": "system_overview", "label": "システム全体像"},
            {"key": "features", "label": "主要機能一覧 (大分類)"},
        ],
    },
    {
        "step": 3,
        "title": "機能要件詳細",
        "description": "各機能の入出力・エラーケース・制約を確定",
        "core_sections": [
            {"key": "functional", "label": "機能要件 (詳細)"},
        ],
    },
    {
        "step": 4,
        "title": "非機能要件・UX・データ構造",
        "description": "性能・セキュリティ・可用性・画面・ER 図",
        "core_sections": [
            {"key": "nonfunctional", "label": "非機能要件"},
            {"key": "screens", "label": "画面・UX"},
            {"key": "data", "label": "データ構造"},
            {"key": "integrations", "label": "外部連携"},
        ],
    },
    {
        "step": 5,
        "title": "法的考慮・コンプライアンス",
        "description": "業種・取扱データから適用法令を網羅し、機能要件に反映",
        "core_sections": [
            {"key": "legal_domain", "label": "業種・取扱データ判定"},
            {"key": "legal_regulations", "label": "適用法令・規制 一覧"},
            {"key": "legal_features", "label": "必要な実装要件 (機能要件への追加)"},
            {"key": "legal_nfr", "label": "非機能要件への追加"},
            {"key": "legal_risks", "label": "法的リスク・未確認事項"},
        ],
    },
    {
        "step": 6,
        "title": "リスク分析・未確認事項",
        "description": "リスク表 + 未確認事項 + PM への注意事項",
        "core_sections": [
            {"key": "risks", "label": "リスク一覧"},
            {"key": "unresolved", "label": "未確認事項"},
            {"key": "pm_notes", "label": "PM への注意事項"},
        ],
    },
    {
        "step": 7,
        "title": "最終出力",
        "description": "HTML / Markdown / JSON 一式を生成・確定",
        "core_sections": [
            {"key": "summary", "label": "要件定義書サマリー"},
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

    items = await art.list_artifacts(limit=300)
    for a in items:
        if a.get("workspace_id") != workspace_id:
            continue
        if a.get("type") != "spec":
            continue
        data = a.get("data") or {}
        if data.get("phase") == "requirements" and data.get("step") == step and not data.get("archived_version"):
            return a

    initial = empty_center_state(step)
    meta = get_step_meta(step)
    title = f"要件定義 STEP {step}: {meta['title']}" if meta else f"要件定義 STEP {step}"
    created = await art.create_artifact(
        type="spec",
        title=title,
        data={
            "phase": "requirements",
            "step": step,
            "version": 1,
            "status": "draft",
            "center": initial,
        },
        category_tags=["requirements", f"step-{step}"],
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
    return await art.update_artifact(artifact_id, data=data, actor="ai:pm", note="requirements center update")


async def get_hearing_brief(workspace_id: int) -> dict:
    """ヒアリングフェーズの全 STEP の center を統合した brief を返す。STEP 1 の自動引き継ぎに使う。"""
    from services import artifact_service as art
    items = await art.list_artifacts(limit=300)
    by_step: dict[int, dict] = {}
    for a in items:
        if a.get("workspace_id") != workspace_id:
            continue
        if a.get("type") != "spec":
            continue
        data = a.get("data") or {}
        if data.get("phase") != "hearing":
            continue
        s = data.get("step")
        if s is not None:
            if s not in by_step or a.get("updated_at", "") > by_step[s].get("updated_at", ""):
                by_step[s] = a
    summary = {}
    for s in sorted(by_step.keys()):
        a = by_step[s]
        center = (a.get("data") or {}).get("center", {})
        summary[f"step{s}"] = {
            "title": (a.get("title") or "").split(":")[-1].strip() if ":" in (a.get("title") or "") else a.get("title"),
            "status": (a.get("data") or {}).get("status"),
            "sections": [
                {"key": sec["key"], "label": sec["label"], "items": sec.get("items", [])}
                for sec in (center.get("sections") or []) if sec.get("items")
            ],
        }
    return summary


# ──────────────────────────────────────────
# 法的考慮 (STEP 5) 動的検出
# ──────────────────────────────────────────
# ハードコード辞書は廃止。代わりに以下のフローで動的検出する:
#   [1] プロジェクト全文 (ヒアリング brief + 要件 STEP 1-4 center) を LLM に投入
#   [2] LLM がプロジェクト要旨を構造化抽出
#       - business_summary, industries[], data_types[], business_model
#   [3] ナレッジ DB をベクトル / タグ検索 (既存 embedding 利用、無ければスキップ)
#   [4] Web 検索で該当法令を引く (WebSearch 経由・失敗時はフォールバックとして LLM の事前知識のみ)
#   [5] LLM がすべてのコンテキストを統合し、最終的な法令候補を JSON で返す
#
# Single Source of Truth = ~/.claude/skills/requirements-definition/SKILL.md (system prompt 経由)
def _gather_project_context(hearing_brief: dict, req_centers: list[dict]) -> str:
    """ヒアリング brief + 要件 STEP 1-4 の center を LLM に渡す要約テキストに整形。"""
    parts: list[str] = []
    if hearing_brief:
        parts.append("# ヒアリング結果\n" + json.dumps(hearing_brief, ensure_ascii=False, indent=2)[:3000])
    for i, c in enumerate(req_centers, start=1):
        secs = (c or {}).get("sections", []) or []
        non_empty = [s for s in secs if s.get("items")]
        if non_empty:
            parts.append(f"\n# 要件 STEP {i}\n" + json.dumps(non_empty, ensure_ascii=False, indent=2)[:2000])
    return "\n".join(parts) if parts else "(プロジェクト情報がまだ十分に揃っていません)"


async def _llm_extract_project_profile(project_context: str) -> dict:
    """LLM にプロジェクトの法務的プロファイルを抽出させる (Step 1)。"""
    system = (
        "あなたは日本の IT プロジェクト法務に詳しいビジネスアナリストです。\n"
        "与えられたプロジェクト情報から、法的検討に必要な観点を構造化抽出してください。\n"
        "想像で項目を増やさず、情報がない箇所は空配列・空文字で返してください。\n\n"
        "出力は以下の JSON だけ (コードフェンスなし):\n"
        '{"business_summary": "1-2 文の要旨", '
        '"industries": ["想定される業種・ドメイン (複数可)"], '
        '"data_types": ["扱う可能性が高いデータ種別 (個人情報/決済情報/医療情報/児童情報/位置情報 など)"], '
        '"business_model": "BtoC / BtoB / マーケットプレイス / プラットフォーム など", '
        '"web_search_queries": ["この業種・データで検索すべき具体的な日本語クエリ (3-5 件)"]}'
    )
    return await _call_llm(system, [{"role": "user", "content": project_context[:6000]}])


async def _web_search_legal(queries: list[str], per_query: int = 3) -> list[dict]:
    """Web 検索で法令情報を収集する。

    bf_websearch ヘルパーが利用可能ならそれを使い、失敗時は空リストを返してフォールバック。
    """
    if not queries:
        return []
    results: list[dict] = []
    try:
        from services.web_search_helper import search as bf_search  # type: ignore
    except Exception:
        bf_search = None  # type: ignore

    if bf_search is None:
        return []

    for q in queries[:5]:
        try:
            hits = await bf_search(q, num=per_query)
            for h in (hits or [])[:per_query]:
                results.append({
                    "query": q,
                    "title": h.get("title", "")[:200],
                    "url": h.get("url", ""),
                    "snippet": (h.get("snippet") or h.get("description") or "")[:400],
                })
        except Exception:
            continue
    return results


async def _vector_lookup_legal_knowledge(industries: list[str], data_types: list[str]) -> list[dict]:
    """ナレッジ DB を埋め込み類似度で検索 (利用可能な場合)。

    既存ナレッジサービスに埋め込み検索 API があれば利用、無ければタグ検索にフォールバック。
    """
    queries = list(filter(None, industries + data_types))
    if not queries:
        return []

    # ベクトル検索を試行
    try:
        from services.knowledge_search_service import vector_search  # type: ignore
        out: list[dict] = []
        for q in queries[:3]:
            hits = await vector_search(q, top_k=3, filter_tags=["legal", "法令", "compliance"])
            for h in hits or []:
                out.append({"id": h.get("id"), "title": h.get("title"), "score": h.get("score")})
        if out:
            return out[:8]
    except Exception:
        pass

    # フォールバック: タグ検索
    try:
        from services import artifact_service as art
        items = await art.list_artifacts(limit=200)
    except Exception:
        return []
    found: list[dict] = []
    for a in items or []:
        if a.get("type") not in ("knowledge", "note", "doc"):
            continue
        tags = " ".join(a.get("category_tags") or []).lower()
        if "legal" in tags or "法令" in tags or "compliance" in tags:
            found.append({"id": a.get("id"), "title": a.get("title"), "tags": a.get("category_tags") or []})
    return found[:8]


async def _llm_synthesize_legal(project_context: str, profile: dict, web_hits: list[dict], knowledge_hits: list[dict]) -> dict:
    """全てのコンテキストを統合して、最終的な法令候補を LLM に組み立てさせる (Step 2)。"""
    system = (
        "あなたは日本の IT プロジェクト法務に詳しいビジネスアナリストです。\n"
        "プロジェクト情報・抽出済プロファイル・Web 検索結果・社内ナレッジを統合し、\n"
        "STEP 5 の中央エリアにそのまま反映できる構造で法的考慮事項を整理してください。\n"
        "Web 検索結果に出典 URL がある項目には必ず `source_url` を付けてください。\n"
        "想像で法令を捏造しないこと。確信が低い項目は items の先頭に【要確認】を付けてください。\n\n"
        "出力は以下の JSON だけ (コードフェンスなし):\n"
        '{"legal_domain": [{"item": "業種・取扱データの判定 1 行", "source_url": ""}], '
        '"legal_regulations": [{"item": "[業種] 法令名 (要点)", "source_url": ""}], '
        '"legal_features": [{"item": "実装に必要な要件 (例: 特定商取引法表記ページ)", "source_url": ""}], '
        '"legal_nfr": [{"item": "非機能要件への追加 (例: ログ保管 7 年)", "source_url": ""}], '
        '"legal_risks": [{"item": "法的リスク・要確認事項", "source_url": ""}]}'
    )
    user = (
        f"# プロジェクトコンテキスト\n{project_context[:4000]}\n\n"
        f"# 抽出済プロファイル\n{json.dumps(profile, ensure_ascii=False, indent=2)[:2000]}\n\n"
        f"# Web 検索結果\n{json.dumps(web_hits, ensure_ascii=False, indent=2)[:3000]}\n\n"
        f"# 社内ナレッジ参照\n{json.dumps(knowledge_hits, ensure_ascii=False, indent=2)[:1500]}"
    )
    return await _call_llm(system, [{"role": "user", "content": user}])


async def build_legal_autodetect_payload(workspace_id: int) -> dict:
    """STEP 5 開始時の動的検出ペイロードを構築。

    Returns:
        {
          "profile": {business_summary, industries, data_types, business_model, web_search_queries},
          "web_hits": [{query, title, url, snippet}, ...],
          "knowledge_hits": [{id, title, score?, tags?}, ...],
          "synthesis": {legal_domain, legal_regulations, legal_features, legal_nfr, legal_risks},
          "has_hearing": bool
        }
    """
    hearing_brief = await get_hearing_brief(workspace_id)
    req_centers: list[dict] = []
    for s in (1, 2, 3, 4):
        art = await get_or_create_center_artifact(workspace_id, s)
        c = (art.get("data") or {}).get("center") or {}
        req_centers.append(c)

    project_context = _gather_project_context(hearing_brief, req_centers)
    profile = await _llm_extract_project_profile(project_context)

    queries = profile.get("web_search_queries") or []
    web_hits = await _web_search_legal(queries)
    knowledge_hits = await _vector_lookup_legal_knowledge(
        profile.get("industries") or [],
        profile.get("data_types") or [],
    )
    synthesis = await _llm_synthesize_legal(project_context, profile, web_hits, knowledge_hits)

    return {
        "profile": profile,
        "web_hits": web_hits,
        "knowledge_hits": knowledge_hits,
        "synthesis": synthesis,
        "has_hearing": bool(hearing_brief),
    }


def legal_payload_to_center_patch(payload: dict) -> list[dict]:
    """動的検出結果を center_patch に変換 (STEP 5 用)。

    items は文字列または {item, source_url} を許容。出典 URL があれば末尾に「(出典: URL)」を付ける。
    """
    patch: list[dict] = []
    synthesis = (payload or {}).get("synthesis") or {}

    def _to_lines(entries) -> list[str]:
        out: list[str] = []
        for e in entries or []:
            if isinstance(e, str):
                out.append(e)
            elif isinstance(e, dict):
                txt = e.get("item") or ""
                url = e.get("source_url") or ""
                if not txt:
                    continue
                if url:
                    out.append(f"{txt} (出典: {url})")
                else:
                    out.append(txt)
        return out

    section_map = {
        "legal_domain": "legal_domain",
        "legal_regulations": "legal_regulations",
        "legal_features": "legal_features",
        "legal_nfr": "legal_nfr",
        "legal_risks": "legal_risks",
    }
    any_filled = False
    for src_key, dst_key in section_map.items():
        items = _to_lines(synthesis.get(src_key))
        if items:
            any_filled = True
            patch.append({"section_key": dst_key, "operation": "update", "items": items})

    if not any_filled:
        patch.append({
            "section_key": "legal_domain",
            "operation": "update",
            "items": ["【未検出】プロジェクト情報が不足しています。STEP 1-4 を埋めてから再度この STEP を始めてください。"],
        })
    return patch


# ──────────────────────────────────────────
# プロンプト構築
# ──────────────────────────────────────────
def _load_skill_md() -> str:
    if REQ_SKILL_PATH.exists():
        return REQ_SKILL_PATH.read_text(encoding="utf-8")
    return ""


def _extract_common_rules(skill_md: str) -> str:
    """skill md の冒頭「思考品質基準」セクションを抽出。"""
    m = re.search(r"##\s*\U0001F9E0\s*全スキル共通[\s\S]*?(?=\n#\s*requirements-definition\s*スキル|\Z)", skill_md)
    if m:
        return m.group(0).strip()
    return skill_md[:5000]


def _extract_step_section(skill_md: str, step: int) -> str:
    """指定 STEP セクション抽出 (### [arrow] STEP {n} ... ）。"""
    _arrow = chr(0x25B6)  # BLACK RIGHT-POINTING TRIANGLE (avoid raw emoji char in source)
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
            account_id=account_id, doc_type="requirements_reference",
            keywords=keywords, limit=2,
        )
        if not block:
            block = await ing.build_references_context_block(
                account_id=account_id, doc_type=None,
                keywords=keywords, limit=2,
            )
        return block or ""
    except Exception as e:
        print(f"[requirements] references fetch failed: {e}")
        return ""


def _build_system_prompt(step: int, center_state: dict, hearing_brief: dict, legal_payload: dict | None = None) -> str:
    meta = get_step_meta(step) or {}
    skill_md = _load_skill_md()
    common_rules = _extract_common_rules(skill_md)
    step_section = _extract_step_section(skill_md, step)
    if not step_section:
        step_section = f"(STEP {step} セクションが見つかりませんでした)"

    hearing_summary = ""
    if hearing_brief:
        hearing_summary = "# ヒアリング結果 (前フェーズ)\n以下を踏まえて要件定義を進めてください。\n```json\n"
        hearing_summary += json.dumps(hearing_brief, ensure_ascii=False, indent=2)[:3500]
        hearing_summary += "\n```"

    legal_summary = ""
    if step == 5 and legal_payload:
        legal_summary = (
            "# 法的考慮 自動検出結果 (STEP 5 専用コンテキスト)\n"
            "以下は Build-Factory 側のドメインスキャン早見表 + ナレッジ検索で自動抽出した結果です。\n"
            "PM にこの内容を提示しながら、抜け漏れ・該当しない項目・追加すべき業種を確認してください。\n"
            "ナレッジ参照がある場合は legal_risks の【ナレッジ参照】行を残しつつ、PM に内容確認を促してください。\n"
            "```json\n" + json.dumps(legal_payload, ensure_ascii=False, indent=2)[:2500] + "\n```"
        )

    return f"""あなたは「PM AI」です。Build-Factory プロジェクトの要件定義フェーズを担当します。
requirements-definition スキル (~/.claude/skills/requirements-definition/SKILL.md) に従って厳密に動作してください。

# 共通動作ルール (全 STEP 共通・絶対遵守)
{common_rules}

# あなたの今の作業: STEP {step}
{step_section}

{hearing_summary}

{legal_summary}

# Build-Factory UI 制約 (重要)
1. **対話駆動**: チャットで PM (人間) と短いキャッチボール。1 メッセージは 1-3 文 + 質問 1-2 個まで。長文禁止。
2. **質問設計の基準を遵守**: スキルの STEP {step} に書かれた具体的な質問テンプレート (a/b/c のサブ質問など) を使う。汎用質問は禁止。
3. **深掘りチェック**: スキルの「深掘りチェック」表に書かれた観点を毎回確認。
4. **ドメインスキャン**: PM の業界が判明したら、対応する法律・規制・制度を質問の中で必ず触れる。STEP 5 で集中的に深掘り。
5. **ヒアリング引き継ぎ (STEP 1 のみ)**: 既存ヒアリング情報があれば「ヒアリングではこう聞きました。これで合ってますか?」と確認しながら進める。
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
- PM が編集した項目は、AI 側で意図せず削除・改変しないでください。
- ただし「最終更新者勝ち」(last write wins) の方針: AI が更新する妥当な理由 (情報追加・誤りの修正・PM の質問への返答など) があれば上書き OK。
- 上書きする場合は chat_message で必ず「○○を更新しました」と PM に伝える。
- PM の編集は「PM の意思」であり、ユーザーの希望に反する変更は避けること。

# 出力形式 (必ず以下の JSON だけを返す。コードフェンスもなし。)
{{
  "chat_message": "PM への次の発話 (1-3 文 + 質問 1-2 個)",
  "center_patch": [
    {{
      "section_key": "overview",
      "operation": "add" | "update" | "remove",
      "items": ["箇条書き項目"]
    }}
  ],
  "ready_to_complete": false,
  "internal_note": "(任意) デバッグ用 1 行メモ"
}}

JSON 以外の文字列は一切返さない。文字列内の改行は \\n。"""


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
        print(f"[requirements] LLM error: {e}")
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

    history = await get_chat_history(workspace_id, "requirements", step)
    if history:
        return {
            "artifact": art,
            "center": center,
            "history": history,
            "ai_message": history[-1]["content"] if history[-1]["role"] == "ai" else None,
        }

    hearing_brief = await get_hearing_brief(workspace_id) if step == 1 else {}

    # STEP 5: 法的考慮の自動検出を先に走らせ、center にプリフィル + プロンプトに渡す
    legal_payload: dict = {}
    if step == 5:
        legal_payload = await build_legal_autodetect_payload(workspace_id)
        center = apply_center_patch(center, legal_payload_to_center_patch(legal_payload))

    system = _build_system_prompt(step, center, hearing_brief, legal_payload)
    references_block = await _get_references_block(workspace_id)
    if references_block:
        system = system + "\n\n" + references_block
    user_kickoff = f"STEP {step} を始めてください。"
    if step == 1 and hearing_brief:
        user_kickoff += "\nヒアリング結果を踏まえ、要件定義のすり合わせを開始してください。"
    if step == 5 and legal_payload.get("domains"):
        domain_names = ", ".join(d["domain"] for d in legal_payload["domains"])
        user_kickoff += f"\n自動検出されたドメイン: {domain_names}\nこれらの確認と、未検出ドメインがないかの確認から始めてください。"
    llm_out = await _call_llm(system, [{"role": "user", "content": user_kickoff}])

    chat_msg = llm_out.get("chat_message", "STEP を始めます。")
    center = apply_center_patch(center, llm_out.get("center_patch", []))

    await _save_message(workspace_id, "requirements", step, "system", "STEP 開始", {})
    msg_id = await _save_message(workspace_id, "requirements", step, "ai", chat_msg, {"step_started": True})
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
    history = await get_chat_history(workspace_id, "requirements", step)

    await _save_message(workspace_id, "requirements", step, "user", user_message)

    llm_messages = []
    for h in history:
        if h["role"] in ("user", "ai"):
            llm_messages.append({
                "role": "assistant" if h["role"] == "ai" else "user",
                "content": h["content"],
            })
    llm_messages.append({"role": "user", "content": user_message})

    hearing_brief = await get_hearing_brief(workspace_id) if step == 1 else {}
    system = _build_system_prompt(step, center, hearing_brief)
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
        workspace_id, "requirements", step, "ai", chat_msg,
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
        if data.get("phase") != "requirements":
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
        history = await get_chat_history(workspace_id, "requirements", s)
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

    return {"workspace_id": workspace_id, "phase": "requirements", "steps": steps_state}


# ──────────────────────────────────────────
# 集約 (タブ表示用の統合 view)
# ──────────────────────────────────────────
TAB_TO_STEP_SECTIONS: dict[str, list[tuple[int, str]]] = {
    "overview":      [(1, "overview"), (1, "challenges"), (1, "kpi"), (1, "constraints_initial")],
    "users":         [(2, "users"), (2, "scenes")],
    "features":      [(2, "features"), (2, "system_overview")],
    "functional":    [(3, "functional")],
    "nonfunctional": [(4, "nonfunctional")],
    "screens":       [(4, "screens")],
    "data":          [(4, "data")],
    "integrations":  [(4, "integrations")],
    "legal":         [(5, "legal_domain"), (5, "legal_regulations"), (5, "legal_features"), (5, "legal_nfr"), (5, "legal_risks")],
    "risks":         [(6, "risks")],
    "unresolved":    [(6, "unresolved"), (6, "pm_notes")],
}


async def get_aggregated_view(workspace_id: int) -> dict:
    """全 STEP の center を集約し、IDE タブ単位の配列で返す。

    フロント側が期待する形:
      { workspace_id, phase, tabs: [{key, label, locked, source_steps, sections: [{key,label,items,source_step}]}] }

    locked = 該当 STEP がまだ完了していない (status != confirmed)
    """
    state = await get_state(workspace_id)
    by_step: dict[int, dict] = {s["step"]: s for s in state["steps"]}

    tab_order = [
        "overview", "users", "features", "functional", "nonfunctional",
        "screens", "data", "integrations", "legal", "risks", "unresolved",
    ]

    tabs_out: list[dict] = []
    for tab_key in tab_order:
        refs = TAB_TO_STEP_SECTIONS.get(tab_key, [])
        if not refs:
            continue
        source_steps = sorted({step_num for step_num, _ in refs})

        # locked: 関連 STEP が 1 つでも進行中 (draft 含む) ならアンロック表示
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
        "phase": "requirements",
        "tabs": tabs_out,
        "step_status": {s["step"]: s["status"] for s in state["steps"]},
    }


# ──────────────────────────────────────────
# 出力ファイル生成 (HTML / MD / JSON)
# ──────────────────────────────────────────
TAB_LABELS = {
    "all":           "全て",
    "overview":      "プロジェクト概要",
    "users":         "ターゲットユーザー",
    "features":      "主要機能一覧",
    "functional":    "機能要件詳細",
    "nonfunctional": "非機能要件",
    "screens":       "画面・UX",
    "data":          "データ構造",
    "integrations":  "外部連携",
    "legal":         "法的考慮・コンプライアンス",
    "risks":         "リスク・懸念点",
    "unresolved":    "未確認事項",
    "history":       "改訂履歴",
}


def _items_to_md(items: list[str]) -> str:
    return "\n".join(f"- {it}" for it in items) if items else "_(まだ記入されていません)_"


async def render_markdown(workspace_id: int, tab: str = "all") -> str:
    """指定タブの Markdown を生成。tab='all' で全タブ結合。"""
    view = await get_aggregated_view(workspace_id)
    tabs = view["tabs"]

    if tab == "all":
        order = ["overview", "users", "features", "functional", "nonfunctional",
                 "screens", "data", "integrations", "legal", "risks", "unresolved"]
        out = ["# 要件定義書\n"]
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


def _items_to_html_list(items: list[str]) -> str:
    if not items:
        return '<p style="color:#94A3B8; font-size:13px;">(未記入)</p>'
    lis = "\n".join(f"  <li>{_html_escape(it)}</li>" for it in items)
    return f"<ul>\n{lis}\n</ul>"


def _html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def render_html(workspace_id: int, tab: str = "all") -> str:
    """指定タブの HTML を生成 (テンプレに沿った Calm Industrial スタイル)。"""
    view = await get_aggregated_view(workspace_id)
    tabs = view["tabs"]

    if tab == "all":
        order = ["overview", "users", "features", "functional", "nonfunctional",
                 "screens", "data", "integrations", "legal", "risks", "unresolved"]
        body = []
        for i, t in enumerate(order, 1):
            label = TAB_LABELS[t]
            sections = tabs.get(t, [])
            inner = []
            for sec in sections:
                inner.append(f'<h3 style="font-size:15px;font-weight:700;color:#0F172A;margin:16px 0 8px;">{_html_escape(sec.get("label", ""))}</h3>')
                inner.append(_items_to_html_list(sec.get("items", [])))
            body.append(f'''
<div class="section-card" id="{t}" data-bf-tab="{t}">
  <div class="section-header"><div class="section-num">{i}</div><div class="section-title">{label}</div></div>
  {"".join(inner) if inner else '<p style="color:#94A3B8; font-size:13px;">(未記入)</p>'}
</div>''')
        body_html = "\n".join(body)
    else:
        label = TAB_LABELS.get(tab, tab)
        sections = tabs.get(tab, [])
        inner = []
        for sec in sections:
            inner.append(f'<h3 style="font-size:15px;font-weight:700;color:#0F172A;margin:16px 0 8px;">{_html_escape(sec.get("label", ""))}</h3>')
            inner.append(_items_to_html_list(sec.get("items", [])))
        body_html = f'''
<div class="section-card" id="{tab}" data-bf-tab="{tab}">
  <div class="section-header"><div class="section-num">1</div><div class="section-title">{label}</div></div>
  {"".join(inner) if inner else '<p style="color:#94A3B8; font-size:13px;">(未記入)</p>'}
</div>'''

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>要件定義書 — {TAB_LABELS.get(tab, tab)}</title>
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
  <h1>要件定義書</h1>
  <div class="meta">タブ: {TAB_LABELS.get(tab, tab)} ・ Build-Factory が自動生成</div>
  {body_html}
</div>
</body>
</html>
"""


async def render_json(workspace_id: int, tab: str = "all") -> dict:
    """指定タブの JSON を生成。実装側に渡せる構造化データ。"""
    view = await get_aggregated_view(workspace_id)
    tabs = view["tabs"]
    if tab == "all":
        return {
            "workspace_id": workspace_id,
            "phase": "requirements",
            "step_status": view["step_status"],
            "tabs": tabs,
        }
    return {
        "workspace_id": workspace_id,
        "phase": "requirements",
        "tab": tab,
        "label": TAB_LABELS.get(tab, tab),
        "sections": tabs.get(tab, []),
    }
