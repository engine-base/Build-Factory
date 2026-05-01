"""
secretary_agent.py — 秘書AI（openai-agents Agent SDK ベース）

skill_runner で SKILL.md を読み込み、tools を持たせた Agent として実行する。
Agent loop で自動的にツールを使い分け、必要に応じて社員AIへタスク委任する。
"""

import os
from pathlib import Path
from typing import Optional

# OpenAI Tracing を無効化（OpenAI公式へ送信されないように）
os.environ.setdefault("OPENAI_AGENTS_DISABLE_TRACING", "1")

from agents import Agent, Runner, ModelSettings, set_tracing_disabled
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

set_tracing_disabled(True)

from .tools import (
    search_web, fetch_url,
    search_knowledge, add_knowledge,
    delegate_to_employee, list_pending_tasks, list_employees_and_skills,
    search_past_conversations,
    browser_action,
    create_approval_request,
    knowledge_cleanup_preview, knowledge_cleanup_delete,
    staff_list, staff_orgchart, staff_hire, staff_update, staff_retire,
    staff_transfer_propose, staff_list_members,
    search_knowledge_scoped, add_knowledge_smart,
    list_skills, get_skill, create_skill, update_skill_md,
    add_skill_eval, run_skill_eval, package_skill,
    list_my_artifacts, get_my_artifact, update_my_artifact,
)

SKILL_STORE = Path(__file__).resolve().parents[2] / "data" / "skills"
SKILLS_PATH = Path.home() / ".claude" / "skills"


def _load_secretary_md() -> str:
    """秘書のSKILL.md を読む。"""
    paths = [
        SKILL_STORE / "secretary" / "SKILL.md",
        SKILLS_PATH / "secretary" / "SKILL.md",
    ]
    for p in paths:
        if p.exists():
            return p.read_text(encoding="utf-8")
    return "あなたはENGINE BASEのAI秘書です。"


def _get_llm_client(provider: str) -> AsyncOpenAI:
    """provider に応じて AsyncOpenAI クライアントを返す（既存ヘルパーをラップ）。"""
    from llm.config import get_openai_client, LLMProvider
    try:
        provider_enum = LLMProvider(provider)
    except ValueError:
        provider_enum = LLMProvider.OLLAMA
    return get_openai_client(provider_enum, dict(os.environ))


def build_secretary_agent(
    provider: str = "ollama",
    model: str = "qwen2.5:7b",
) -> Agent:
    """秘書AIエージェントを構築して返す。"""
    instructions = _load_secretary_md() + (
        "\n\n# Agent モード追加指示\n"
        "- 必要に応じて以下のツールを使ってください:\n"
        "  - search_web / fetch_url: 最新情報や外部情報の取得\n"
        "  - search_knowledge: 社内ナレッジ参照（まさとの判断基準など）\n"
        "  - add_knowledge: 重要な情報をナレッジに保存\n"
        "  - search_past_conversations: 過去の会話を検索（「先日言ったあれ」「以前の○○」と聞かれた時に必ず使う）\n"
        "  - list_employees_and_skills: 社員と保有スキルの確認\n"
        "  - delegate_to_employee: 特定スキルでのタスク作成・社員割当\n"
        "  - list_pending_tasks: 現在進行中のタスク確認\n"
        "  - create_approval_request: 外部送信を伴うアウトプットの承認依頼\n"
        "  - knowledge_cleanup_preview / knowledge_cleanup_delete: 使われていないナレッジの整理。削除前に必ずプレビューで件数確認 → まさとに承認を取ってから delete を実行する。\n"
        "  - staff_list / staff_orgchart: AI社員一覧・組織図確認\n"
        "  - staff_hire / staff_update / staff_retire: AI社員の採用・編集・退職。これらの組織変更は基本『人事AI 高橋結衣』(employee_name=hr_05) に依頼する方針。秘書が直接実行するのは例外時のみ。\n"
        "  - staff_transfer_propose: 採用時に親リーダーから引継ナレッジ候補を抽出\n"
        "  - search_knowledge_scoped: 社員スコープ付きナレッジ検索\n"
        "  - add_knowledge_smart: 賢いナレッジ追加（AI分類で保存先提案 → まさと確認 → 保存）\n"
        "\n# 役職呼称ルール（厳守）\n"
        "- secretary = 秘書 / leader = リーダー / member = メンバー（「○○のメンバー」と肩書き付きで呼ぶ）\n"
        "- リーダーは統括役でタスク実行はしない・メンバーが実行担当\n"
        "- ナレッジは 共通 + 部 + 個人 の3層スコープで管理されている\n"
        "\n# 組織変更の振り分けルール\n"
        "- 採用・編集・退職などの組織変更は『人事AI 高橋結衣（hr_05）』が担当。秘書は依頼を受けたら人事AIに振る。\n"
        "- 例外: まさとから直接秘書に頼まれて急ぎの場合のみ秘書が staff_* ツールを実行。\n"
        "- 単純な質問や雑談ではツールを使わず簡潔に返答してください。\n"
        "- 「あれ」「これ」「先日のあの件」など曖昧な指示があったら search_past_conversations で必ず確認してください。"
    )

    client = _get_llm_client(provider)
    llm_model = OpenAIChatCompletionsModel(model=model, openai_client=client)

    tools_list = [
        search_web, fetch_url,
        search_knowledge, add_knowledge,
        search_past_conversations,
        list_employees_and_skills,
        delegate_to_employee,
        list_pending_tasks,
        browser_action,
        create_approval_request,
        knowledge_cleanup_preview, knowledge_cleanup_delete,
        staff_list, staff_orgchart,
        staff_hire, staff_update, staff_retire,
        staff_transfer_propose,
        search_knowledge_scoped, add_knowledge_smart,
    ]
    if not model_supports_tools(provider, model):
        tools_list = []
        instructions = instructions + (
            "\n\n# 重要: 現在のLLM制約\n"
            "ツール非対応モデル動作中。組織変更等は qwen2.5:7b / gpt-4o-mini に切替を促してください。"
        )

    return Agent(
        name="ENGINE BASE 秘書AI",
        instructions=instructions,
        model=llm_model,
        tools=tools_list,
        model_settings=ModelSettings(temperature=0.7),
    )


async def run_secretary(
    user_message: str,
    history: Optional[list[dict]] = None,
    provider: str = "ollama",
    model: str = "qwen2.5:7b",
) -> dict:
    """
    秘書Agentを1回実行する（Agent loop で必要に応じてツール使用）。

    Args:
        user_message: ユーザーのメッセージ
        history:      会話履歴 [{"role":"user","content":"..."},...]（任意）
        provider:     LLMプロバイダ
        model:        LLMモデル
    Returns:
        {"output": str, "tool_calls": [...], "total_turns": int}
    """
    secretary = build_secretary_agent(provider=provider, model=model)
    input_items = _build_message_list(history, user_message)

    try:
        result = await Runner.run(secretary, input_items, max_turns=8)
        return {
            "output": str(result.final_output) if result.final_output else "",
            "raw_responses": [r.model_dump() if hasattr(r, "model_dump") else str(r) for r in (result.raw_responses or [])][:5],
            "total_turns":  len(result.raw_responses or []),
        }
    except Exception as e:
        return {"output": f"[Agent エラー] {e}", "raw_responses": [], "total_turns": 0}


def _load_persona_block(emp: dict) -> str:
    """社員の persona を system プロンプトとして組み立てる。"""
    if not emp:
        return ""
    role_jp = {"secretary": "秘書", "leader": "リーダー", "member": "メンバー"}.get(
        emp.get("role_level") or "leader", "リーダー"
    )
    parts = []
    if emp.get("persona_name"):
        parts.append(f"あなたの名前: {emp.get('avatar_emoji') or ''} {emp['persona_name']}")
    parts.append(f"役職: {role_jp}（{emp.get('category') or ''}）")
    if emp.get("specialty"):  parts.append(f"特化分野: {emp['specialty']}")
    if emp.get("personality"): parts.append(f"性格: {emp['personality']}")
    if emp.get("tone_style"):  parts.append(f"口調: {emp['tone_style']}")
    if emp.get("catchphrase"): parts.append(f"口癖: {emp['catchphrase']}")
    if emp.get("handles"):     parts.append(f"担当範囲: {emp['handles']}")
    return "\n".join(parts)


# ツール対応モデル判定（Ollama / API）
# False を返したらツール無しで Agent を構築する（Function Calling 非対応モデル）
_TOOL_INCOMPATIBLE_PATTERNS = (
    "gemma",     # gemma2/gemma3 系は tools 非対応
    "gemma2",
    "gemma3",
    "phi",       # phi-3 系も多くが非対応
    "phi3",
)


def model_supports_tools(provider: str, model: str) -> bool:
    """このモデルが OpenAI 互換の tools パラメータをサポートするか。"""
    if provider in ("openai", "claude", "anthropic"):
        return True
    m = (model or "").lower()
    for pat in _TOOL_INCOMPATIBLE_PATTERNS:
        if pat in m:
            return False
    return True


def _build_identity(emp: dict) -> str:
    """Layer 1: 不変の人格（〜500字）"""
    if not emp:
        return ""
    role_jp = {"secretary": "秘書", "leader": "リーダー", "member": "メンバー"}.get(
        emp.get("role_level") or "leader", "リーダー"
    )
    name = emp.get("persona_name") or emp.get("display_name") or "AI社員"
    avatar = emp.get("avatar_emoji") or ""
    parts = [
        f"あなたは「{name}」{avatar}（{role_jp}・{emp.get('category','')}）。",
    ]
    if emp.get("personality"): parts.append(f"性格: {emp['personality']}。")
    if emp.get("tone_style"):  parts.append(f"口調: {emp['tone_style']}。")
    if emp.get("catchphrase"): parts.append(f"口癖: 「{emp['catchphrase']}」。")
    if emp.get("specialty"):   parts.append(f"特化: {emp['specialty']}。")
    return " ".join(parts)


def _build_common_rules() -> str:
    """Layer 2: 常時適用される最小限ルール + CoT 推論ガイド（V2: 断定許可・部分一致・復唱禁止）

    + Artifact 操作ガイド（V3: 既存 view を更新するときの呼び出し方）
    """
    return (
        "\n\n# Artifact 連携ルール（出力管理レイヤー）\n"
        "- ユーザーが「あのリストに追加」「先ほどのかんばんを更新」「タスク完了にして」など\n"
        "  既存 artifact への操作を求めたら、以下を順に行う:\n"
        "  1. list_my_artifacts で直近の候補を取得（pinned_only や category で絞り込んで良い）\n"
        "  2. 該当しそうな artifact の id を get_my_artifact で詳細確認\n"
        "  3. update_my_artifact(artifact_id, data_patch_json) で部分更新する\n"
        "     - data_patch_json は merge される（既存 data を全部書き直す必要なし）\n"
        "     - 例: {\"items\":[既存全部 + 新項目]} のような JSON 文字列を渡す\n"
        "- 新規に表・かんばん・KPI 等を提示するときは、応答内に明示的なフェンスを書くと\n"
        "  自動で artifact 化される。例:\n"
        "  ```kanban\n  {\"columns\":[{\"id\":\"todo\",\"title\":\"TODO\",\"cards\":[...]}]}\n  ```\n"
        "  ```kpi\n  {\"metrics\":[{\"label\":\"売上\",\"value\":1500000,\"unit\":\"円\"}]}\n  ```\n"
        "- 単純な箇条書き（- xxx）も自動で list 型 artifact 化される。\n"
        "- ユーザーから「ピン留めして」「ライブラリに保存」と言われたら artifact 関連 tool を使うが、\n"
        "  作成自体は通常応答（フェンス）でも可。\n"
        "\n# 基本ルール\n"
        "- 応答は完全に日本語のみ。中国語・英語・韓国語等の混入は1文字でも禁止。\n"
        "- 短い質問には短く・自然に。雑談は気軽に。\n"
        "- 自分の人格・口調を毎ターン保つ。\n"
        "- ユーザー発言の復唱・要約・確認の繰り返しは禁止（「○○ですね」「○○は確定しています」を毎回言わない）。\n"
        "\n# 推論プロセス（応答前に必ず実行・出力には書かない）\n"
        "1. 目的（ゴール）と『どのスロットを埋めようとしているか』を確認\n"
        "2. ユーザー直前発言を分類: 確定 / 否定 / ヒント / メタ指示 / 雑談\n"
        "3. ヒントなら**解釈して漢字1〜2文字**を特定する（原文を引用しない）\n"
        "4. 否定なら直前 AI 提案の何が違うか特定する（後述・部分一致ルール）\n"
        "5. 同じスロットの全ヒントを総合して**1つの候補**を組み立てて断定的に提示する\n"
        "\n# スロット状態の解釈\n"
        "- ✓確定: そのまま使う。再質問・再確認・復唱しない。\n"
        "- ×不採用（再提示禁止）: 全く同じ値を再提案しない。ただし**部分一致は別物**（後述）。\n"
        "- 💡ヒント: 解釈済みの漢字候補。複数あれば全部組み合わせて1案にする。\n"
        "- 各スロットは独立。\n"
        "\n# 部分一致ルール（重要）\n"
        "- 「聖人」が rejected → 「聖」「人」**個別の漢字は依然候補**として使える\n"
        "- 「聖人」と「聖斗」は別物・「聖斗」を提案して良い（rejected には聖人だけが入っている）\n"
        "- ユーザーが『聖は合ってる』と言った場合のみ、聖の単体確定として扱う\n"
        "- 既存の rejected を見て、漢字単位で『2文字とも一致する候補』だけを除外する。1文字でも違えば別候補として提案可。\n"
        "\n# ヒント解釈の例\n"
        "- 「キリストの重要な本」→ 聖書 →「聖」\n"
        "- 「7つの星座」「北斗七星」→「斗」\n"
        "- 「太陽」→「日」「陽」\n"
        "- 複数ヒントは**統合して1つの名前**を組み立てる: 「聖」+「斗」=「聖斗」を提案する（聖人ではなく）\n"
        "\n# 応答スタイル（重要）\n"
        "- 推論できる時は**断定的に1案だけ提示**（『○○ではないでしょうか？』ではなく『○○です』）\n"
        "- 外れたら次の候補を出す。試行錯誤して進める。\n"
        "- 「可能性があります」「かもしれません」を多用しない。\n"
        "- ユーザーが『当てて』と言ったら必ず断定で出す（複数候補の羅列禁止・1ターン1候補）。\n"
        "- 確定情報を毎回前置きで再確認しない（『苗字は高本で確定しています』を繰り返さない）。\n"
        "\n# ヒントが本当に足りない時のみ\n"
        "- 短く1問だけ追加質問する（複数質問・選択肢提示は禁止）。"
    )


def _build_task_rules(skill_loaded: bool) -> str:
    """Layer 3a: タスクモード時に追加するルール（業務時のみ）"""
    if not skill_loaded:
        # スキル発火していないタスク（一般的な業務）
        return (
            "\n\n# 業務応答ルール\n"
            "- 必要なら適切なツールを使用する。\n"
            "- 選択肢を聞く時は tool-ui の option-list、最終承認は approval-card を使う。\n"
            "- 1問1答で進め、ユーザーが指示できる粒度で確認する。"
        )
    # スキル発火時はスキル内のルールに従う（共通ルールはスキル側にある）
    return ""


def _build_skill_block(skill_name: str, skill_md: str) -> str:
    """Layer 3b: 発火したスキルのフル全文（要約しない・Claude 方式）"""
    if not skill_md:
        return ""
    return (
        f"\n\n# 発火スキル: {skill_name}\n"
        "（以下を忠実に守る。途中で別話題に逸れない・英語混じり禁止）\n\n"
        + skill_md
    )


def _build_rag_block(rag_text: str) -> str:
    """Layer 4: RAG コンテキスト（プロファイル/履歴/類似/ナレッジ）"""
    if not rag_text:
        return ""
    return "\n\n" + rag_text


def build_agent_for_employee(
    emp: dict,
    provider: str = "ollama",
    model: str = "qwen2.5:7b",
    mode: str = "chat",                         # "chat" | "task"
    triggered_skill: Optional[str] = None,      # 発火スキル名（None なら未発火）
    rag_text: str = "",                         # RAG コンテキスト整形済み文字列
) -> Agent:
    """階層プロンプトで Agent を構築。

    Layer 1 (Identity)        — 常時
    Layer 2 (Common Rules)    — 常時
    Layer 3a (Task Rules)     — mode=task 時のみ
    Layer 3b (Skill Full MD)  — triggered_skill が None でない時にフル全文ロード
    Layer 4 (RAG Context)     — 毎ターン

    雑談時はトータル ~1KB / スキル発火時は SKILL.md フル全文（5-10KB）。
    """
    from services.skill_detector import load_skill_md

    primary_skill = (emp.get("primary_skill") or "").strip()
    role = emp.get("role_level") or "leader"
    is_hr = (primary_skill == "staff-management")
    name = emp.get("persona_name") or emp.get("display_name") or "AI社員"

    # ── スキル MD ロード（発火時のみ・フル全文） ──────
    skill_md = ""
    if triggered_skill:
        skill_md = load_skill_md(triggered_skill) or ""

    # ── プロンプト組み立て ────────────────────────
    parts = [_build_identity(emp), _build_common_rules()]
    if mode == "task":
        parts.append(_build_task_rules(bool(skill_md)))
    if skill_md and triggered_skill:
        parts.append(_build_skill_block(triggered_skill, skill_md))
    if rag_text:
        parts.append(_build_rag_block(rag_text))

    instructions = "".join(parts)

    # ── ツールセット ──────────────────────────────
    base_tools = [
        search_web, fetch_url,
        search_knowledge, add_knowledge,
        search_past_conversations,
        search_knowledge_scoped, add_knowledge_smart,
        list_pending_tasks,
        create_approval_request,
        # Artifact 管理（既存スキルには影響しない・出力 view の読み書きのみ）
        list_my_artifacts, get_my_artifact, update_my_artifact,
    ]
    secretary_extra = [
        list_employees_and_skills,
        delegate_to_employee,
        staff_list, staff_orgchart,
        knowledge_cleanup_preview, knowledge_cleanup_delete,
        browser_action,
        # skill 管理（skill-creator スキル発火時に使う）
        list_skills, get_skill, create_skill, update_skill_md,
        add_skill_eval, run_skill_eval, package_skill,
    ]
    hr_extra = [
        staff_list, staff_orgchart, staff_list_members,
        staff_hire, staff_update, staff_retire,
        staff_transfer_propose,
    ]
    leader_extra = [staff_list, staff_orgchart]

    # 雑談モードでは ツールを最小化（不要な道具で混乱しない）
    if mode == "chat":
        # 雑談で必要なのは過去会話検索程度
        tools = [search_past_conversations]
    elif role == "secretary":
        tools = base_tools + secretary_extra
    elif is_hr:
        tools = base_tools + hr_extra
    elif role == "leader":
        tools = base_tools + leader_extra
    else:
        tools = base_tools

    # ツール非対応モデル（gemma 系等）の場合はツール無しで構築
    # → 通常会話・回答だけはできるが、staff_hire 等は呼べないので
    #   その旨を instructions の末尾に追記する
    if not model_supports_tools(provider, model):
        tools = []
        instructions = instructions + (
            "\n\n# 重要: 現在のLLM制約\n"
            "あなたは現在ツール非対応のモデルで動作中です。\n"
            "- 採用・退職・組織図確認などのツール実行はできません。\n"
            "- ユーザーから組織変更を依頼されたら『現在のモデルでは実行できないため、\n"
            "  右下の LLMピッカーから qwen2.5:7b や gpt-4o-mini に切り替えてください』と返答してください。\n"
            "- 通常の会話・質問への回答は通常通り行ってください。"
        )

    client = _get_llm_client(provider)
    llm_model = OpenAIChatCompletionsModel(model=model, openai_client=client)

    return Agent(
        name=f"ENGINE BASE {name}",
        instructions=instructions,
        model=llm_model,
        tools=tools,
        model_settings=ModelSettings(temperature=0.5),
    )


def _build_message_list(history: Optional[list[dict]], user_message: str) -> list[dict]:
    """履歴を OpenAI Agents SDK が解釈できる message list として構築する。
    フラット文字列で渡すとモデルがターン構造を読めず、認識ズレや英語混じりが起きるため
    必ず list[{role, content}] 形式で渡す。"""
    msgs: list[dict] = []
    if history:
        for h in history[-12:]:
            role = h.get("role")
            content = h.get("content") or h.get("message") or ""
            if role in ("user", "assistant") and content:
                msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": user_message})
    return msgs


async def _legacy_prepare(
    employee_id: int,
    user_message: str,
    history: Optional[list[dict]],
    provider: str,
    model: str,
    thread_id: Optional[int],
    helper_provider: Optional[str],
    helper_model: Optional[str],
) -> tuple[dict, str, Optional[str], str]:
    """レガシー直結経路: emp / mode / triggered_skill / rag_text を返す。
    LangGraph が無効・失敗時のフォールバック。"""
    import aiosqlite
    from db.queries import DB_PATH
    from services.mode_detector import detect_mode
    from services.skill_detector import detect_skill
    from services.user_profile import update_from_message
    from services.rag_context import build_context, format_for_prompt
    from services.conversation_summarizer import (
        generate_summary, format_for_prompt as fmt_summary,
    )
    from services import slot_state as ss

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM ai_employee_config WHERE id = ?", (employee_id,),
        )
        row = await cur.fetchone()
    emp = dict(row) if row else {
        "persona_name": "秘書", "role_level": "secretary",
        "primary_skill": "secretary",
    }

    try:
        await update_from_message(user_message)
    except Exception as e:
        print(f"[legacy_prepare] profile {e}")

    mode = await detect_mode(user_message, history or [])
    triggered_skill: Optional[str] = None
    if mode == "task":
        triggered_skill = detect_skill(
            message=user_message,
            history=history or [],
            employee_primary_skill=emp.get("primary_skill"),
        )

    rag_text = ""
    try:
        ctx = await build_context(
            message=user_message, thread_id=thread_id,
            employee_id=employee_id, mode=mode,
        )
        rag_text = format_for_prompt(ctx, mode=mode)
    except Exception as e:
        print(f"[legacy_prepare] rag {e}")

    if thread_id and history and len(history) >= 1:
        try:
            hp = helper_provider if helper_provider else (
                "openai" if os.environ.get("OPENAI_API_KEY") else provider
            )
            hm = helper_model if helper_model else (
                "gpt-4o-mini" if hp == "openai" else model
            )
            await ss.update_slots_from_message(
                thread_id=thread_id,
                user_message=user_message,
                history=history,
                helper_provider=hp,
                helper_model=hm,
            )
        except Exception as e:
            print(f"[legacy_prepare] slot update {e}")

    slot_text = ""
    if thread_id:
        try:
            slots = await ss.get_slots(thread_id)
            slot_text = ss.format_for_prompt(slots)
        except Exception as e:
            print(f"[legacy_prepare] slot get {e}")
    if slot_text:
        rag_text = (rag_text + "\n\n" + slot_text) if rag_text else slot_text

    summary_text = ""
    if history and len(history) >= 2:
        try:
            summary = await generate_summary(
                history=history,
                main_provider=provider, main_model=model,
                helper_provider=helper_provider, helper_model=helper_model,
            )
            summary_text = fmt_summary(summary)
        except Exception as e:
            print(f"[legacy_prepare] summary {e}")
    if summary_text:
        rag_text = (rag_text + "\n\n" + summary_text) if rag_text else summary_text

    return emp, mode, triggered_skill, rag_text


async def stream_as_employee(
    employee_id: int,
    user_message: str,
    history: Optional[list[dict]] = None,
    provider: str = "ollama",
    model: str = "qwen2.5:7b",
    thread_id: Optional[int] = None,
    helper_provider: Optional[str] = None,   # サマリ用LLM（None=メインと同じ）
    helper_model: Optional[str] = None,
):
    """指定社員の persona でエージェント実行をストリーミング配信する。

    階層プロンプト + RAG 自動注入 + 会話サマリ + スキル発火検知。
    雑談時は 軽量プロンプト（~1KB）・業務時は フル装備。

    USE_LANGGRAPH=1 のとき LangGraph で前処理を実行（推奨）。
    それ以外は従来通り直接呼び出し（互換動作）。
    """
    # ── 前処理: LangGraph 経路 / レガシー経路 ─────
    use_lg = os.environ.get("USE_LANGGRAPH", "1") == "1"
    emp: dict = {}
    mode = "chat"
    triggered_skill: Optional[str] = None
    rag_text = ""

    if use_lg:
        try:
            from services.orchestrator_graph import prepare_state
            prep = await prepare_state(
                thread_id=thread_id,
                employee_id=employee_id,
                user_message=user_message,
                history=history,
                provider=provider, model=model,
                helper_provider=helper_provider, helper_model=helper_model,
            )
            emp = prep["employee"]
            mode = prep["mode"]
            triggered_skill = prep["triggered_skill"]
            rag_text = prep["rag_text"]
        except Exception as e:
            print(f"[stream_as_employee] LangGraph 失敗・旧経路へ: {e}")
            use_lg = False

    if not use_lg:
        emp, mode, triggered_skill, rag_text = await _legacy_prepare(
            employee_id, user_message, history, provider, model,
            thread_id, helper_provider, helper_model,
        )

    # ── Agent 構築（階層プロンプト） ──────────
    agent = build_agent_for_employee(
        emp,
        provider=provider, model=model,
        mode=mode,
        triggered_skill=triggered_skill,
        rag_text=rag_text,
    )

    print(f"[stream_as_employee] mode={mode} skill={triggered_skill} "
          f"prompt_len={len(agent.instructions or '')}")

    input_items = _build_message_list(history, user_message)

    try:
        result = Runner.run_streamed(agent, input_items, max_turns=8)
        async for event in result.stream_events():
            etype = type(event).__name__
            if etype == "RawResponsesStreamEvent":
                data = getattr(event, "data", None)
                if data and hasattr(data, "type"):
                    # output_text のみ転送（function_call_arguments のような JSON 断片を弾く）
                    dtype = str(getattr(data, "type", ""))
                    if "output_text.delta" in dtype:
                        delta = getattr(data, "delta", None)
                        if delta:
                            yield {"type": "text", "delta": str(delta)}
            elif etype == "RunItemStreamEvent":
                item = getattr(event, "item", None)
                if item and hasattr(item, "raw_item"):
                    item_type = type(item.raw_item).__name__
                    if "ToolCall" in item_type or "FunctionCall" in item_type:
                        name = getattr(item.raw_item, "name", "?")
                        yield {"type": "tool", "name": name}

        yield {"type": "done", "output": str(result.final_output or "")}
    except Exception as e:
        yield {"type": "error", "error": str(e)}


async def run_as_employee_unified(
    employee_id: int,
    user_message: str,
    history: Optional[list[dict]] = None,
    provider: str = "ollama",
    model: str = "qwen2.5:7b",
    thread_id: Optional[int] = None,
    helper_provider: Optional[str] = None,
    helper_model: Optional[str] = None,
) -> dict:
    """非ストリーミング統一エントリポイント（Slack 等で使う）。

    内部で stream_as_employee と同じ前処理（LangGraph + slot + RAG + skill）を経由し、
    最終出力を1回で返す。Web の SSE 経路と「全く同じ仕様」を保証する。

    Returns: {"output": str, "tool_calls": list[str], "thread_id": int|None}
    """
    full_text = ""
    tool_calls: list[str] = []
    async for evt in stream_as_employee(
        employee_id=employee_id,
        user_message=user_message,
        history=history,
        provider=provider, model=model,
        thread_id=thread_id,
        helper_provider=helper_provider, helper_model=helper_model,
    ):
        if evt.get("type") == "text":
            full_text += evt.get("delta") or ""
        elif evt.get("type") == "tool":
            tool_calls.append(evt.get("name") or "?")
        elif evt.get("type") == "done":
            if not full_text and evt.get("output"):
                full_text = evt["output"]

    # AI 提案を slot history に記録（次ターンの reject に備える）
    if thread_id and full_text:
        try:
            from services import slot_state as ss
            await ss.record_ai_proposals(thread_id, full_text)
        except Exception as e:
            print(f"[run_as_employee_unified] proposal記録失敗: {e}")

    return {"output": full_text, "tool_calls": tool_calls, "thread_id": thread_id}


async def stream_secretary(
    user_message: str,
    history: Optional[list[dict]] = None,
    provider: str = "ollama",
    model: str = "qwen2.5:7b",
):
    """
    秘書Agentをストリーミング実行する（イベント逐次配信）。
    yield: {"type": "text"|"tool"|"done", ...}
    """
    secretary = build_secretary_agent(provider=provider, model=model)
    input_items = _build_message_list(history, user_message)

    try:
        result = Runner.run_streamed(secretary, input_items, max_turns=8)
        async for event in result.stream_events():
            etype = type(event).__name__
            # raw_response_event: 個々のLLMレスポンス
            if etype == "RawResponsesStreamEvent":
                data = getattr(event, "data", None)
                if data and hasattr(data, "type"):
                    # text delta
                    if "output_text" in str(data.type) or hasattr(data, "delta"):
                        delta = getattr(data, "delta", None)
                        if delta:
                            yield {"type": "text", "delta": str(delta)}
            # ツール呼び出し
            elif etype == "RunItemStreamEvent":
                item = getattr(event, "item", None)
                if item and hasattr(item, "raw_item"):
                    item_type = type(item.raw_item).__name__
                    if "ToolCall" in item_type or "FunctionCall" in item_type:
                        name = getattr(item.raw_item, "name", "?")
                        yield {"type": "tool", "name": name}

        yield {"type": "done", "output": str(result.final_output or "")}

    except Exception as e:
        yield {"type": "error", "error": str(e)}
