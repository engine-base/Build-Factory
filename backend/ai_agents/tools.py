"""
tools.py — openai-agents で使う共通ツール集

秘書 / 各社員 Agent が使えるツールを @function_tool で定義する。
既存サービス層を呼ぶ薄いラッパー。
"""

import json
from typing import Optional

from agents import function_tool


# ─────────────────────────────────────────────
# Web / 情報取得
# ─────────────────────────────────────────────

@function_tool
async def search_web(query: str, max_results: int = 5) -> str:
    """
    DuckDuckGo で Web を検索する。最新情報・市場動向・競合情報・ニュース等を調べる時に使う。
    Args:
        query:        検索クエリ（日本語可）
        max_results:  返す結果の数
    Returns:
        検索結果（タイトル・URL・スニペット）の JSON 文字列
    """
    from integrations.web_tools import search_web as _search
    results = await _search(query, max_results=max_results)
    return json.dumps(results, ensure_ascii=False, indent=2)


@function_tool
async def fetch_url(url: str) -> str:
    """
    指定URL の本文を取得する。検索結果を深掘りしたい時、ニュース記事を読みたい時に使う。
    Args:
        url: 取得するURL
    Returns:
        ページ本文（最大4000字）
    """
    from integrations.web_tools import fetch_url as _fetch
    return await _fetch(url)


# ─────────────────────────────────────────────
# ナレッジベース
# ─────────────────────────────────────────────

@function_tool
async def search_knowledge(query: str, skill_tag: str = "") -> str:
    """
    社内ナレッジベース（Obsidian + 承認履歴）を意味検索する。
    まさとの価値観・判断基準・過去の正例・社内ルールを引き出したい時に使う。
    Args:
        query:     検索クエリ
        skill_tag: 特定スキル向けに絞るとき（例: "invoice-create"）
    Returns:
        類似度 Top10 のナレッジ
    """
    from services.embedding_service import search_knowledge as _search_kb
    results = await _search_kb(
        query=query,
        skill_tags=[skill_tag] if skill_tag else None,
        top_k=10,
        min_score=0.35,
    )
    return json.dumps([
        {"title": r["title"], "category": r["category"],
         "content": r["content"][:400], "score": r["score"]}
        for r in results
    ], ensure_ascii=False, indent=2)


@function_tool
async def add_knowledge(content: str, masato_memo: str = "") -> str:
    """
    新しいナレッジを保存する。会話の中で「これは覚えておくべき」と判断した時に使う。
    自動的に分類・タグ付けされる。
    Args:
        content:     ナレッジ内容
        masato_memo: 抽出指示があれば（任意）
    Returns:
        保存結果
    """
    from services.knowledge_curator import classify_and_save
    result = await classify_and_save(
        content=content,
        masato_memo=masato_memo or None,
        source="agent_save",
        full_content=not bool(masato_memo),
    )
    return json.dumps({
        "saved":    True,
        "title":    result["title"],
        "category": result["category"],
        "id":       result["knowledge_id"],
    }, ensure_ascii=False)


# ─────────────────────────────────────────────
# 社員 AI / タスク
# ─────────────────────────────────────────────

@function_tool
async def delegate_to_employee(
    employee_name: str,
    skill_name: str,
    task_description: str,
) -> str:
    """
    特定の社員AIにタスクを委任する。タスクは task_executor が並列処理する。

    Args:
        employee_name:    "secretary" | "sales_01" | "finance_02" | "marketing_03" | "cs_04"
        skill_name:       実行するスキル名（例: "invoice-create", "sales-email"）
        task_description: タスクの内容・指示
    Returns:
        作成されたタスクの ID
    """
    from db import async_db as aiosqlite
    from pathlib import Path
    DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

    # 社員ID解決
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT id FROM ai_employee_config WHERE employee_name=?",
            (employee_name,)
        )
        if not rows:
            return json.dumps({"error": f"社員 {employee_name} が見つかりません"}, ensure_ascii=False)
        emp_id = rows[0]["id"]

        cursor = await db.execute(
            """INSERT INTO tasks (title, description, assigned_to, skill_name, status)
               VALUES (?, ?, ?, ?, 'pending') RETURNING id""",
            (task_description[:200], task_description, emp_id, skill_name)
        )
        _row = await cursor.fetchone()
        task_id = _row["id"]
        await db.commit()

    # 即時実行を発火
    try:
        from workers.task_executor import execute_task_now
        import asyncio as _asyncio
        _asyncio.create_task(execute_task_now(task_id))
    except Exception as e:
        print(f"[tools] execute_task_now失敗: {e}")

    return json.dumps({
        "task_id":  task_id,
        "assignee": employee_name,
        "skill":    skill_name,
        "status":   "pending",
        "note":     "task_executor が自動実行します（10秒以内に開始）",
    }, ensure_ascii=False)


@function_tool
async def list_pending_tasks() -> str:
    """進行中・未完了のタスク一覧を取得する。"""
    from db import async_db as aiosqlite
    from pathlib import Path
    DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT t.id, t.title, t.status, e.display_name as assignee
               FROM tasks t LEFT JOIN ai_employee_config e ON e.id=t.assigned_to
               WHERE t.status IN ('pending','in_progress','review_needed')
               ORDER BY t.created_at DESC LIMIT 20"""
        )
    return json.dumps([dict(r) for r in rows], ensure_ascii=False)


@function_tool
async def list_employees_and_skills() -> str:
    """
    利用可能な全社員AIと、各社員の保有スキル一覧を返す。
    どの社員にタスクを振るか判断する時に呼ぶ。
    """
    from db import async_db as aiosqlite
    from pathlib import Path
    DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        emps = await db.execute_fetchall(
            "SELECT id, employee_name, display_name, category FROM ai_employee_config WHERE is_active=1"
        )
        result = []
        for e in emps:
            skills = await db.execute_fetchall(
                """SELECT s.skill_name, s.description FROM ai_employee_skills aes
                   JOIN skill_definitions s ON s.id=aes.skill_id
                   WHERE aes.employee_id=?""",
                (e["id"],)
            )
            result.append({
                "employee_name": e["employee_name"],
                "display_name":  e["display_name"],
                "category":      e["category"],
                "skills": [
                    {"name": s["skill_name"], "desc": (s["description"] or "")[:80]}
                    for s in skills
                ]
            })
    return json.dumps(result, ensure_ascii=False)


# ─────────────────────────────────────────────
# 承認・通知
# ─────────────────────────────────────────────

@function_tool
async def browser_action(task: str, service: str = "") -> str:
    """
    ブラウザ操作タスクを「キューに追加」する。即時実行はしない。
    実行は後で Claude Desktop が claude-in-chrome MCP 経由で消化する。

    重要: 「今すぐ」「速攻」「すぐに」「至急」などの依頼を受けても、
    必ずキューに積むだけにすること。即時実行のオプションは存在しない。

    例:
      task="Notion で 'プロジェクト案' というページを作成して、'作業中' というメモを入れる"
      service="notion"

    Args:
        task:    自然言語のタスク指示
        service: ログイン要のサービス名（事前に /api/browser/credentials で登録）
    Returns:
        キュー追加結果（task_id とメッセージ）
    """
    from services import browser_queue

    task_id = await browser_queue.add_task(
        task=task, service=service or None, requested_by="secretary",
    )
    return json.dumps({
        "mode": "queued",
        "task_id": task_id,
        "message": f"ブラウザタスク #{task_id} をキューに追加しました。後ほどまとめて実行されます。",
    }, ensure_ascii=False)


@function_tool
async def search_past_conversations(query: str) -> str:
    """
    過去の会話履歴をベクトル検索する。
    「先日言った○○の件」「以前話した△△」など、過去のやり取りを参照したい時に使う。
    全スレッドから関連性の高い発言を Top5 で返す。

    Args:
        query: 検索したい話題・キーワード
    Returns:
        過去の会話メッセージ（時系列・スレッド情報付き）
    """
    from services.conversation_memory import search_related_history
    results = await search_related_history(
        query=query,
        thread_id=None,
        top_k=5,
        min_score=0.4,
        exclude_recent=0,
    )
    if not results:
        return json.dumps({"results": [], "note": "関連する過去の会話は見つかりませんでした"}, ensure_ascii=False)
    return json.dumps({
        "results": [
            {
                "role":       r["role"],
                "message":    r["message"][:400],
                "thread_id":  r["thread_id"],
                "created_at": r["created_at"],
                "similarity": r["score"],
            }
            for r in results
        ]
    }, ensure_ascii=False)


@function_tool
async def create_approval_request(
    title: str,
    content: str,
    action_type: str = "report_save",
) -> str:
    """
    承認待ちキューに項目を追加する。
    ユーザーの承認が必要なアクション（メール送信・請求書発行・契約等）はこれを使う。

    Args:
        title:       承認項目のタイトル
        content:     承認内容（実際の生成物）
        action_type: "email_send" | "invoice_send" | "post" | "report_save" | "db_update"
    """
    from db import async_db as aiosqlite
    import json as _json
    from pathlib import Path
    from datetime import datetime, timedelta
    DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
    expires_at = (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO approval_queue
               (action_type, title, content, source_skill, expires_at)
               VALUES (?, ?, ?, 'agent', ?) RETURNING id""",
            (action_type, title[:80], content, expires_at)
        )
        _row = await cursor.fetchone()
        await db.commit()
    return _json.dumps({"approval_id": _row["id"]}, ensure_ascii=False)


# ─────────────────────────────────────────────
# AI社員管理（採用・編集・退職・組織図）
# ─────────────────────────────────────────────

@function_tool
async def staff_list(include_retired: bool = False) -> str:
    """
    現在のAI社員一覧を返す。秘書・リーダー・メンバーすべて。

    Args:
        include_retired: True なら退職済みも含める
    """
    import aiohttp
    async with aiohttp.ClientSession() as s:
        async with s.get(
            "http://localhost:8000/api/staff",
            params={"include_retired": str(include_retired).lower()},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            return json.dumps(await r.json(), ensure_ascii=False)


@function_tool
async def staff_orgchart() -> str:
    """
    組織図を返す（秘書・リーダー・メンバーの階層 + ナレッジ件数 + キャパ警告）。
    まさとに「組織図見せて」「うちの体制」と聞かれた時に使う。
    """
    import aiohttp
    async with aiohttp.ClientSession() as s:
        async with s.get("http://localhost:8000/api/staff/orgchart",
                         timeout=aiohttp.ClientTimeout(total=10)) as r:
            return json.dumps(await r.json(), ensure_ascii=False)


@function_tool
async def staff_hire(
    persona_name: str,
    role_level: str,                # 'leader' | 'member'
    category: str,
    parent_id: int = 0,             # member のとき必須・leader は 0
    specialty: str = "",
    handles: str = "",
    personality: str = "",
    tone_style: str = "",
    catchphrase: str = "",
    avatar_emoji: str = "👤",
) -> str:
    """
    新しいAI社員を採用する。staff-managementスキルのHIREフロー実行版。
    必ずまさとから最終承認を得てから呼ぶこと。

    Args:
        persona_name: 表示名（例: 田中ジュニア）
        role_level:   'leader'（部の長）か 'member'（実行担当）
        category:     大分類（例: 01_営業）
        parent_id:    member の場合、親リーダーのID
        specialty:    特化分野（例: 新規開拓）member のみ
        handles:      担当範囲（自然文・1〜2文）
        personality:  性格
        tone_style:   口調
        catchphrase:  口癖
        avatar_emoji: アバター絵文字
    """
    import aiohttp
    body = {
        "persona_name": persona_name,
        "role_level": role_level,
        "category": category,
        "parent_id": parent_id if parent_id > 0 else None,
        "specialty": specialty or None,
        "handles": handles,
        "personality": personality,
        "tone_style": tone_style,
        "catchphrase": catchphrase,
        "avatar_emoji": avatar_emoji,
        "triggered_by": "secretary",
    }
    async with aiohttp.ClientSession() as s:
        async with s.post("http://localhost:8000/api/staff/hire", json=body,
                          timeout=aiohttp.ClientTimeout(total=30)) as r:
            return json.dumps(await r.json(), ensure_ascii=False)


@function_tool
async def staff_update(
    employee_id: int,
    persona_name: str = "",
    personality: str = "",
    tone_style: str = "",
    catchphrase: str = "",
    avatar_emoji: str = "",
    specialty: str = "",
    handles: str = "",
    category: str = "",
) -> str:
    """
    既存社員の個性・担当を編集する。空文字の項目はスキップ。
    必ずまさとに変更前/後を見せて承認を得てから呼ぶ。

    Args:
        employee_id:  編集対象のID
        persona_name: 名前（変更する場合のみ・空ならスキップ）
        personality:  性格
        tone_style:   口調
        catchphrase:  口癖
        avatar_emoji: アバター絵文字
        specialty:    特化分野（メンバーのみ）
        handles:      担当範囲
        category:     部署
    """
    import aiohttp
    updates = {}
    if persona_name: updates["persona_name"] = persona_name
    if personality:  updates["personality"]  = personality
    if tone_style:   updates["tone_style"]   = tone_style
    if catchphrase:  updates["catchphrase"]  = catchphrase
    if avatar_emoji: updates["avatar_emoji"] = avatar_emoji
    if specialty:    updates["specialty"]    = specialty
    if handles:      updates["handles"]      = handles
    if category:     updates["category"]     = category
    if not updates:
        return json.dumps({"error": "更新フィールドが空"}, ensure_ascii=False)

    async with aiohttp.ClientSession() as s:
        async with s.patch(
            f"http://localhost:8000/api/staff/{employee_id}",
            json={"updates": updates},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            return json.dumps(await r.json(), ensure_ascii=False)


@function_tool
async def staff_retire(
    employee_id: int,
    inheritance_to: int = 0,
    promote_to_common: bool = False,
    reason: str = "",
    member_reassign_to: int = 0,
    retire_members_too: bool = False,
) -> str:
    """
    AI社員を退職処理する。ナレッジは inheritance_to (>0) または共通へ自動移管。
    リーダーが配下メンバーを抱える場合は member_reassign_to か retire_members_too 必須。

    Args:
        employee_id:        退職対象ID
        inheritance_to:     ナレッジ引継先ID（0 なら共通へ昇格）
        promote_to_common:  True なら共通ナレッジへ昇格
        reason:             退職理由
        member_reassign_to: 配下メンバーを移す先のリーダーID（0=指定なし）
        retire_members_too: True なら配下メンバーも一緒に退職
    """
    import aiohttp
    body = {
        "inheritance_to": inheritance_to if inheritance_to > 0 else None,
        "promote_to_common": promote_to_common,
        "reason": reason,
        "triggered_by": "secretary",
        "member_reassign_to": member_reassign_to if member_reassign_to > 0 else None,
        "retire_members_too": retire_members_too,
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(
            f"http://localhost:8000/api/staff/{employee_id}/retire",
            json=body,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as r:
            return json.dumps(await r.json(), ensure_ascii=False)


@function_tool
async def staff_list_members(leader_id: int) -> str:
    """
    指定リーダー配下の在籍メンバー一覧を返す。退職前の事前確認用。

    Args:
        leader_id: リーダーID
    """
    import aiohttp
    async with aiohttp.ClientSession() as s:
        async with s.get(
            f"http://localhost:8000/api/staff/{leader_id}/members",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as r:
            return json.dumps(await r.json(), ensure_ascii=False)


@function_tool
async def staff_transfer_propose(
    from_employee_id: int,
    query_text: str,
    top_k: int = 30,
) -> str:
    """
    親リーダーから新メンバーへ引継ぐナレッジ候補を抽出する（採用時の事前確認）。
    特化分野（query_text）のベクトル類似度で関連ナレッジ候補を返す。

    Args:
        from_employee_id: 親リーダーID
        query_text:       特化分野・担当領域の自然文
        top_k:            候補上限
    """
    import aiohttp
    async with aiohttp.ClientSession() as s:
        async with s.post(
            "http://localhost:8000/api/staff/transfer/propose",
            json={"from_employee_id": from_employee_id, "query_text": query_text, "top_k": top_k},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            return json.dumps(await r.json(), ensure_ascii=False)


# ─────────────────────────────────────────────
# スコープ付きナレッジ操作
# ─────────────────────────────────────────────

@function_tool
async def search_knowledge_scoped(
    query: str,
    employee_id: int = 0,
    top_k: int = 10,
) -> str:
    """
    スコープ付きでナレッジを検索する。
    employee_id を指定するとその社員が見えるナレッジ（共通+部+個人）だけから検索する。

    Args:
        query:       検索クエリ
        employee_id: 0 なら共通ナレッジのみ。それ以外なら指定社員のスコープ
        top_k:       返す件数
    """
    import aiohttp
    async with aiohttp.ClientSession() as s:
        async with s.post(
            "http://localhost:8000/api/staff/knowledge/search",
            json={"employee_id": employee_id if employee_id > 0 else None,
                  "query": query, "top_k": top_k},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            return json.dumps(await r.json(), ensure_ascii=False)


@function_tool
async def add_knowledge_smart(
    title: str,
    content: str,
    current_employee_id: int = 0,
    confirmed_target_employee_id: int = -1,    # -1=未確認 / 0=共通 / N=指定
    confirmed_target_folder: str = "",
) -> str:
    """
    ナレッジを賢く追加する。保存先は AI が分類して提案、まさとが確認後に保存。

    使い方:
    1) 初回呼出: title, content, current_employee_id だけ渡す
       → 保存先提案が返ってくる
    2) まさとに確認 → 承認後に再呼出（confirmed_target_employee_id, confirmed_target_folder 指定）
       → 実保存

    Args:
        title:                       ナレッジタイトル
        content:                     本文
        current_employee_id:         現在の会話相手の社員ID
        confirmed_target_employee_id: -1=提案モード / 0=共通 / N=指定社員ID
        confirmed_target_folder:      確認後の保存先フォルダ
    """
    import aiohttp

    if confirmed_target_employee_id < 0:
        # 提案フェーズ
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "http://localhost:8000/api/staff/knowledge/propose-target",
                json={"content": content,
                      "current_employee_id": current_employee_id if current_employee_id > 0 else None},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                proposal = await r.json()
        return json.dumps({
            "phase": "proposal",
            "title": title,
            "proposal": proposal,
            "note": "この提案でよければ confirmed_target_employee_id と confirmed_target_folder を指定して再呼出してください",
        }, ensure_ascii=False)

    # 保存フェーズ
    async with aiohttp.ClientSession() as s:
        async with s.post(
            "http://localhost:8000/api/staff/knowledge/save",
            json={
                "title": title,
                "content": content,
                "target_employee_id": confirmed_target_employee_id if confirmed_target_employee_id > 0 else None,
                "target_folder": confirmed_target_folder or "02_共通ナレッジ",
                "source": "secretary",
                "triggered_by": "masato",
            },
            timeout=aiohttp.ClientTimeout(total=20),
        ) as r:
            return json.dumps(await r.json(), ensure_ascii=False)


# ─────────────────────────────────────────────
# ナレッジ クリーンアップ
# ─────────────────────────────────────────────

@function_tool
async def knowledge_cleanup_preview(
    use_count_lte: int = 0,
    not_used_for_days: int = 30,
    older_than_days: int = 0,
    source: str = "",
    confirmed_by_user: int = -1,    # -1=指定なし / 0=未確認のみ / 1=確認済のみ
    exclude_obsidian: bool = True,
    limit: int = 200,
) -> str:
    """
    削除候補のナレッジを抽出する（実際は削除しない）。
    まさとが「使ってないナレッジ整理して」と言ったら、まずこれで件数とリストを確認し、
    knowledge_cleanup_delete に渡して実行する。

    Args:
        use_count_lte:     利用回数が この値以下 のナレッジを対象（既定: 0=一度も使われていない）
        not_used_for_days: 最終更新が N日以上前 のナレッジを対象（既定: 30日）
        older_than_days:   作成から N日以上経過 のナレッジを対象（0なら無制限）
        source:            ソースで絞り込み（manual/approval/task_curate/slack_manual/slack_feedback/document）
        confirmed_by_user: -1=すべて / 0=未確認のみ / 1=確認済のみ
        exclude_obsidian:  Obsidian Vault由来（手動で書いたもの）を除外（推奨: True）
        limit:             最大件数

    Returns:
        件数 + 候補リスト（id, title, source, use_count, last_updated 等）
    """
    import aiohttp
    params = {
        "use_count_lte": use_count_lte,
        "not_used_for_days": not_used_for_days,
        "exclude_obsidian": str(exclude_obsidian).lower(),
        "limit": limit,
    }
    if older_than_days > 0:
        params["older_than_days"] = older_than_days
    if source:
        params["source"] = source
    if confirmed_by_user >= 0:
        params["confirmed_by_user"] = confirmed_by_user

    async with aiohttp.ClientSession() as s:
        async with s.get("http://localhost:8000/api/knowledge/cleanup/preview",
                         params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()

    items = data.get("items", [])[:30]
    return json.dumps({
        "count": data.get("count", 0),
        "filters": data.get("filters"),
        "preview_items": [
            {
                "id": i["id"],
                "title": i["title"],
                "source": i.get("source"),
                "use_count": i.get("use_count", 0),
                "last_updated": i.get("last_updated"),
            }
            for i in items
        ],
        "note": "knowledge_cleanup_delete を呼ぶ前に、まさとに件数と内容を確認してから実行すること。",
    }, ensure_ascii=False)


@function_tool
async def knowledge_cleanup_delete(
    ids: Optional[list[int]] = None,
    use_count_lte: int = 0,
    not_used_for_days: int = 30,
    older_than_days: int = 0,
    source: str = "",
    confirmed_by_user: int = -1,
    exclude_obsidian: bool = True,
    dry_run: bool = False,
) -> str:
    """
    ナレッジを一括削除する。必ず先に knowledge_cleanup_preview で件数を確認すること。
    まさとから明示的な確認（「OK」「削除して」等）を取ってから実行すること。

    Args:
        ids:               個別指定（推奨。プレビューの結果から渡す）
        その他:            ids が空のときに使うフィルタ条件（preview と同じ）
        dry_run:           True なら削除対象数だけ返して実際は削除しない

    Returns:
        削除件数
    """
    import aiohttp
    body: dict = {"dry_run": dry_run}
    if ids:
        body["ids"] = ids
    else:
        body["filter"] = {
            "use_count_lte": use_count_lte,
            "not_used_for_days": not_used_for_days,
            "older_than_days": older_than_days if older_than_days > 0 else None,
            "source": source or None,
            "confirmed_by_user": confirmed_by_user if confirmed_by_user >= 0 else None,
            "exclude_obsidian": exclude_obsidian,
        }

    async with aiohttp.ClientSession() as s:
        async with s.post("http://localhost:8000/api/knowledge/cleanup/bulk-delete",
                          json=body, timeout=aiohttp.ClientTimeout(total=30)) as r:
            data = await r.json()
    return json.dumps(data, ensure_ascii=False)


# ─────────────────────────────────────────────
# Skill 管理（skill-creator スキルが利用）
# ─────────────────────────────────────────────

@function_tool
async def list_skills() -> str:
    """
    インストール済みのスキル一覧を返す。
    ユーザーが「どんなスキルがある？」「○○スキルある？」と聞いた時に使う。
    """
    from services import skill_manager as sm
    skills = await sm.list_skills()
    return json.dumps(skills, ensure_ascii=False, indent=2)


@function_tool
async def get_skill(name: str) -> str:
    """
    指定スキルの SKILL.md とファイル一覧を返す。
    skill-creator で既存スキルを改善する前に必ず呼んで現状把握する。

    Args:
        name: スキル名（ディレクトリ名）
    """
    from services import skill_manager as sm
    s = await sm.get_skill(name)
    if not s:
        return json.dumps({"error": f"skill '{name}' not found"}, ensure_ascii=False)
    return json.dumps(s, ensure_ascii=False, indent=2)


@function_tool
async def create_skill(name: str, description: str, body: str, overwrite: bool = False) -> str:
    """
    新規スキルを作成する。SKILL.md を primary + Claude desktop ミラーの両方に書く。
    ユーザーから「○○のスキルを作って」と頼まれた時に skill-creator スキルの手順に従って使う。

    Args:
        name:        スキル名（英数字+ハイフン）
        description: いつ発火するか・何をするかを 1-2 文で
        body:        SKILL.md 本文（Markdown）
        overwrite:   既存を上書きするか
    """
    from services import skill_manager as sm
    try:
        result = await sm.create_skill(name=name, description=description, body=body, overwrite=overwrite)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, indent=2)


@function_tool
async def update_skill_md(name: str, skill_md: str) -> str:
    """
    既存スキルの SKILL.md 全体を上書き更新する。改善ループで使う。

    Args:
        name:     スキル名
        skill_md: 新しい SKILL.md 全文（YAML frontmatter 含む）
    """
    from services import skill_manager as sm
    try:
        result = await sm.update_skill_md(name, skill_md)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, indent=2)


@function_tool
async def add_skill_eval(name: str, prompt: str, expected_output: str = "") -> str:
    """
    スキルにテストケース（eval）を追加する。
    skill-creator のテストケース作成ステップで使う。

    Args:
        name:            スキル名
        prompt:          実際のユーザーが書きそうな自然なテストプロンプト
        expected_output: 期待される結果の説明
    """
    from services import skill_manager as sm
    try:
        result = await sm.add_eval(name, prompt, expected_output)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False)


@function_tool
async def run_skill_eval(name: str, eval_id: int,
                          provider: str = "openai", model: str = "gpt-4o-mini") -> str:
    """
    指定スキルのテストケース 1 件を LLM で実行して出力をワークスペースに保存する。
    skill-creator の評価ステップで使う。

    Args:
        name:     スキル名
        eval_id:  evals.json の id
        provider: openai / ollama / claude
        model:    使うモデル名
    """
    from services import skill_manager as sm
    try:
        result = await sm.run_eval_inline(name, eval_id, provider=provider, model=model)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, indent=2)


@function_tool
async def package_skill(name: str) -> str:
    """
    スキルディレクトリを .skill ファイル（zip）にパッケージする。
    完成したスキルをユーザーに渡したり、Claude desktop に持ち込む時に使う。

    Args:
        name: スキル名
    """
    from services import skill_manager as sm
    try:
        result = await sm.package_skill(name)
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# Artifact 管理（出力 view を読み書き）
# 既存スキルは触らない・秘書/オーケストレータが使う
# ─────────────────────────────────────────────

@function_tool
async def list_my_artifacts(
    category: Optional[str] = None,
    type: Optional[str] = None,
    pinned_only: bool = False,
    limit: int = 20,
) -> str:
    """
    user の artifact 一覧を取得する。
    「タスク一覧見せて」「ピンしてるもの全部」と聞かれた時に使う。

    Args:
        category:    "task" / "number" / "document" / "catalog" / "design" / "flow" / "time"
        type:        "list" / "kanban" / "table" / "kpi-card" / "markdown" / 他 10 種
        pinned_only: True ならピン留めだけ返す
        limit:       最大件数
    """
    from services import artifact_service as art
    items = await art.list_artifacts(
        category=category, type=type, pinned_only=pinned_only, limit=limit,
    )
    summary = [
        {
            "id": a["id"][:8],
            "type": a["type"],
            "title": a["title"],
            "tags": a.get("category_tags", []),
            "pinned": "masato" in (a.get("pinned_by") or []),
        }
        for a in items
    ]
    return json.dumps(summary, ensure_ascii=False, indent=2)


@function_tool
async def get_my_artifact(artifact_id: str) -> str:
    """
    artifact の中身を取得する（更新前に現状把握する時に使う）。
    """
    from services import artifact_service as art
    a = await art.get_artifact(artifact_id)
    if not a:
        return json.dumps({"error": "not found"}, ensure_ascii=False)
    return json.dumps(a, ensure_ascii=False, indent=2)


@function_tool
async def update_my_artifact(artifact_id: str, data_patch_json: str, note: str = "") -> str:
    """
    artifact を部分更新する。data_patch は merge される。
    例: タスクのステータスを変更・KPI 数値を更新・カードを追加など。

    Args:
        artifact_id:     対象 artifact の id
        data_patch_json: マージしたい JSON 文字列（既存 data に上書きマージされる）
        note:            変更理由の短いメモ
    """
    from services import artifact_service as art
    try:
        patch = json.loads(data_patch_json) if data_patch_json else {}
    except Exception:
        return json.dumps({"error": "data_patch_json は JSON で渡す"}, ensure_ascii=False)
    try:
        result = await art.update_artifact(
            artifact_id, data_patch=patch, actor="ai:secretary", note=note,
        )
    except FileNotFoundError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    return json.dumps({"id": result["id"], "title": result["title"], "updated": True},
                      ensure_ascii=False)
