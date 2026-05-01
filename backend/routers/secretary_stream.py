"""
secretary_stream.py — 秘書チャット SSE ストリーミング・添付・音声対応

POST /api/secretary/stream  — SSE で逐次返答
POST /api/secretary/upload  — 画像/動画/PDF/音声ファイルアップロード
POST /api/secretary/transcribe — 音声→テキスト変換
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from db import async_db as aiosqlite
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

DB_PATH      = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
UPLOAD_DIR   = Path(__file__).resolve().parents[2] / "data" / "uploads" / "secretary"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/api/secretary", tags=["secretary-chat"])


# ── ファイルアップロード ─────────────────────────────────────────────────

@router.post("/upload")
async def upload_attachment(file: UploadFile = File(...)):
    """画像・動画・PDF・音声などのファイルをアップロード。"""
    ext = Path(file.filename).suffix.lower()
    file_id = uuid.uuid4().hex
    saved_name = f"{file_id}{ext}"
    saved_path = UPLOAD_DIR / saved_name

    content = await file.read()
    saved_path.write_bytes(content)

    # MIMEタイプから種別判定
    content_type = file.content_type or ""
    kind = "file"
    if content_type.startswith("image/"):    kind = "image"
    elif content_type.startswith("video/"):  kind = "video"
    elif content_type.startswith("audio/"):  kind = "audio"
    elif "pdf" in content_type:              kind = "pdf"

    return {
        "id":       file_id,
        "filename": file.filename,
        "size":     len(content),
        "kind":     kind,
        "content_type": content_type,
        "url":      f"/api/secretary/files/{saved_name}",
    }


@router.get("/files/{filename}")
async def get_file(filename: str):
    """アップロードされたファイルを配信する。"""
    from fastapi.responses import FileResponse
    path = UPLOAD_DIR / filename
    if not path.exists():
        raise HTTPException(404, "file not found")
    return FileResponse(path)


# ── 音声→テキスト変換 ──────────────────────────────────────────────────

@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    音声ファイルをテキスト変換する。
    OpenAI Whisper API があればそれを使う。なければエラー。
    （ブラウザ側のWeb Speech APIで変換済みのテキストを送るパスもアリ）
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key.startswith("sk-") or len(api_key) < 50:
        raise HTTPException(
            503,
            "OPENAI_API_KEY が未設定です。ブラウザのWeb Speech APIをお使いください。"
        )

    try:
        # 一時保存
        ext = Path(file.filename or "audio.webm").suffix.lower() or ".webm"
        tmp_path = UPLOAD_DIR / f"tmp-{uuid.uuid4().hex}{ext}"
        content = await file.read()
        tmp_path.write_bytes(content)

        # OpenAI Whisper API 呼び出し
        import aiohttp
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field("file", open(tmp_path, "rb"),
                          filename=tmp_path.name,
                          content_type=file.content_type or "audio/webm")
            data.add_field("model", "whisper-1")
            data.add_field("language", "ja")
            async with session.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data=data,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                tmp_path.unlink(missing_ok=True)
                if resp.status != 200:
                    err = await resp.text()
                    raise HTTPException(resp.status, f"Whisper API エラー: {err[:200]}")
                result = await resp.json()
                return {"text": result.get("text", "")}
    except Exception as e:
        raise HTTPException(500, f"transcribe エラー: {e}")


# ── SSE チャットストリーミング ─────────────────────────────────────────

class StreamChatBody(BaseModel):
    message:     str
    attachments: Optional[list[dict]] = None
    provider:    Optional[str] = "ollama"
    model:       Optional[str] = "qwen2.5:7b"
    thread_id:   Optional[int] = None
    employee_id: Optional[int] = None  # 指定すると社員直接対話モード
    force_new_thread: bool = False     # True なら必ず新スレッドを作る（採用フロー等）
    # 補助LLM（会話サマリ等の裏方処理用・None=メインと同じ）
    helper_provider: Optional[str] = None
    helper_model:    Optional[str] = None


@router.post("/stream")
async def secretary_stream_chat(body: StreamChatBody):
    """
    秘書 or 各社員とのチャットを Server-Sent Events で逐次配信する。
    employee_id が指定されれば社員直接対話モード、なければ秘書モード。
    thread_id でスレッド分離。
    """
    user_message = body.message
    attachments = body.attachments or []
    employee_id = body.employee_id or 1  # 1 = 秘書
    is_secretary = employee_id == 1
    channel = "secretary" if is_secretary else "employee"

    # スレッド解決（指定なし → 直近 or 新規 / force_new=True なら必ず新規）
    from routers.threads import get_or_create_thread
    thread_id = await get_or_create_thread(
        channel, employee_id, body.thread_id, force_new=body.force_new_thread
    )

    # ユーザーメッセージを保存（添付情報も含めて）
    enriched_message = user_message
    if attachments:
        att_lines = []
        for a in attachments:
            att_lines.append(f"[{a.get('kind','file')}] {a.get('filename')}")
        enriched_message = f"{user_message}\n\n添付:\n" + "\n".join(att_lines)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO conversation_log
               (channel, with_employee, role, message, thread_id)
               VALUES (?, ?, 'user', ?, ?) RETURNING id""",
            (f"web_{channel}", employee_id, enriched_message[:5000], thread_id)
        )
        _row = await cursor.fetchone()
        user_msg_id = _row["id"]
        await db.execute(
            "UPDATE threads SET last_active_at=datetime('now','localtime') WHERE id=?",
            (thread_id,)
        )
        await db.commit()

    # ユーザーメッセージを Embedding 化（非同期発火）
    import asyncio as _asyncio
    from services.conversation_memory import embed_message
    _asyncio.create_task(embed_message(user_msg_id))

    # 秘書モード前処理: 明示的なキーワードを検出して強制処理
    if is_secretary:
        from services.intent_preprocessor import detect_explicit_intent
        intent = detect_explicit_intent(user_message)
        if intent and intent.get("type") == "remember":
            # 「覚えて○○」 → 即 add_knowledge 実行
            async def remember_generator():
                try:
                    yield f"data: {json.dumps({'type':'start','thread_id':thread_id}, ensure_ascii=False)}\n\n"
                    from services.knowledge_curator import classify_and_save
                    result = await classify_and_save(
                        content=intent["content"],
                        masato_memo=None,
                        source="explicit_remember",
                        full_content=True,
                    )
                    msg = (
                        f"承知しました。以下の内容をナレッジに保存しました。\n\n"
                        f"**{result['title']}**\n"
                        f"カテゴリ: {result['category']} / 知識タイプ: {result['knowledge_type']} / 重要度: {result['importance']}\n"
                        f"保存先: {result.get('md_path','DB')}"
                    )
                    yield f"data: {json.dumps({'type':'text','delta':msg}, ensure_ascii=False)}\n\n"
                    # 会話履歴へ保存
                    async with aiosqlite.connect(DB_PATH) as db:
                        cur = await db.execute(
                            """INSERT INTO conversation_log (channel, with_employee, role, message, thread_id)
                               VALUES (?, ?, 'assistant', ?, ?)""",
                            (f"web_{channel}", employee_id, msg, thread_id)
                        )
                        await db.execute(
                            "UPDATE threads SET last_active_at=datetime('now','localtime') WHERE id=?",
                            (thread_id,)
                        )
                        await db.commit()
                    yield f"data: {json.dumps({'type':'done'}, ensure_ascii=False)}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'type':'error','error':str(e)}, ensure_ascii=False)}\n\n"
            return StreamingResponse(remember_generator(), media_type="text/event-stream")

    # 秘書 / リーダー / メンバー すべて openai-agents の Agent ベースで実行
    # （persona + 全ツール + スコープ前提・認識ズレ防止）
    if True:
        async def event_generator_agent():
            try:
                yield f"data: {json.dumps({'type':'start','thread_id':thread_id}, ensure_ascii=False)}\n\n"

                # 履歴 + 関連過去会話を取得（ハイブリッド context）
                from services.conversation_memory import build_context_for_agent
                ctx = await build_context_for_agent(
                    user_message=user_message,
                    thread_id=thread_id,
                    model=body.model or "qwen2.5:7b",
                    recent_n=10,
                    related_k=5,
                )
                history = [
                    {"role": h["role"], "content": h["message"]}
                    for h in ctx["recent_history"]
                ]

                # 関連過去会話があれば、user メッセージの前にコンテキストとして埋める
                related_block = ""
                if ctx["related_history"]:
                    related_block = "\n\n# 関連する過去のやり取り（参考）\n"
                    for r in ctx["related_history"]:
                        related_block += f"- [{r['role']}] {r['message'][:200]}（{r['created_at']}）\n"

                final_input = enriched_message
                if related_block:
                    final_input = related_block + "\n\n# 現在の依頼\n" + enriched_message

                # Agent 実行（ストリーミング）— 社員別 persona で
                from ai_agents.secretary_agent import stream_as_employee
                from services.tool_ui_postprocess import auto_inject_tool_ui, ToolUIStreamBuffer
                full_text = ""
                ui_buf = ToolUIStreamBuffer()

                def emit_safe(delta: str):
                    """tool-ui バッファを通して安全な部分だけ yield 用に返す。"""
                    out = ui_buf.feed(delta)
                    return out

                async for evt in stream_as_employee(
                    employee_id=employee_id,
                    user_message=final_input,
                    history=history[:-1] if len(history) > 0 else [],
                    provider=body.provider or "ollama",
                    model=body.model or "qwen2.5:7b",
                    thread_id=thread_id,
                    helper_provider=body.helper_provider,
                    helper_model=body.helper_model,
                ):
                    if evt["type"] == "text":
                        delta = evt.get("delta", "")
                        full_text += delta
                        for chunk in ui_buf.feed(delta):
                            yield f"data: {json.dumps({'type':'text','delta':chunk}, ensure_ascii=False)}\n\n"
                    elif evt["type"] == "tool":
                        yield f"data: {json.dumps({'type':'tool','name':evt.get('name','?')}, ensure_ascii=False)}\n\n"
                    elif evt["type"] == "done":
                        if evt.get("output") and not full_text:
                            full_text = evt["output"]
                            for chunk in ui_buf.feed(full_text):
                                yield f"data: {json.dumps({'type':'text','delta':chunk}, ensure_ascii=False)}\n\n"
                        # 残りバッファを flush（未完 tool-ui は破棄）
                        for chunk in ui_buf.flush():
                            yield f"data: {json.dumps({'type':'text','delta':chunk}, ensure_ascii=False)}\n\n"
                        # 自動補完（番号付き選択肢 → option-list）
                        injected = auto_inject_tool_ui(full_text)
                        if injected != full_text:
                            tail = injected[len(full_text):]
                            yield f"data: {json.dumps({'type':'text','delta':tail}, ensure_ascii=False)}\n\n"
                            full_text = injected
                    elif evt["type"] == "error":
                        yield f"data: {json.dumps({'type':'error','error':evt['error']}, ensure_ascii=False)}\n\n"

                # 返答を保存
                async with aiosqlite.connect(DB_PATH) as db:
                    cursor = await db.execute(
                        """INSERT INTO conversation_log
                           (channel, with_employee, role, message, thread_id)
                           VALUES (?, ?, 'assistant', ?, ?) RETURNING id""",
                        (f"web_{channel}", employee_id, full_text[:5000], thread_id)
                    )
                    _row = await cursor.fetchone()
                    asst_msg_id = _row["id"]
                    await db.execute(
                        "UPDATE threads SET last_active_at=datetime('now','localtime') WHERE id=?",
                        (thread_id,)
                    )
                    await db.execute(
                        """UPDATE threads SET title=?
                           WHERE id=? AND (title='新しいチャット' OR title IS NULL)""",
                        (user_message[:30], thread_id)
                    )
                    await db.commit()
                # アシスタント返答も Embedding 化
                import asyncio as _aio
                from services.conversation_memory import embed_message as _embed_msg
                _aio.create_task(_embed_msg(asst_msg_id))

                # AI 応答から提案候補を抽出して slot history に記録
                try:
                    from services.slot_state import record_ai_proposals
                    _aio.create_task(record_ai_proposals(thread_id, full_text))
                except Exception as e:
                    print(f"[secretary_stream] proposal記録失敗: {e}")

                # 出力プロセッサ: AI 応答を解析して artifact を生成/更新
                # スキル / AI 社員には影響しない外側介入
                try:
                    from services.output_processor import (
                        process_ai_response, find_active_artifact_for_thread,
                    )

                    async def _gen_artifact():
                        try:
                            existing = await find_active_artifact_for_thread(thread_id)
                            update_id = None
                            if existing:
                                # 直近 30 分以内かつ同じスレッドなら更新候補とする
                                from datetime import datetime, timedelta
                                try:
                                    upd = datetime.fromisoformat(
                                        (existing.get("updated_at") or "").replace(" ", "T")
                                    )
                                    if datetime.now() - upd < timedelta(minutes=30):
                                        update_id = existing["id"]
                                except Exception:
                                    pass
                            artifact = await process_ai_response(
                                text=full_text,
                                thread_id=thread_id,
                                employee_id=employee_id,
                                update_existing_id=update_id,
                            )
                            if artifact:
                                print(f"[output_processor] artifact "
                                      f"{'updated' if update_id else 'created'}: "
                                      f"{artifact['type']} / {artifact['title'][:40]}")
                        except Exception as e:
                            print(f"[output_processor] {e}")

                    _aio.create_task(_gen_artifact())
                except Exception as e:
                    print(f"[secretary_stream] artifact生成エラー: {e}")

                # Phase 4: Mem0 へ会話を蓄積（USE_MEM0=1 のとき・失敗無視）
                if os.environ.get("USE_MEM0") == "1":
                    try:
                        from services.long_term_memory import add_conversation
                        _aio.create_task(add_conversation(
                            user_id="masato",
                            messages=[
                                {"role": "user", "content": user_message},
                                {"role": "assistant", "content": full_text[:5000]},
                            ],
                            metadata={"thread_id": thread_id, "employee_id": employee_id},
                        ))
                    except Exception as e:
                        print(f"[secretary_stream] mem0 蓄積失敗: {e}")

                yield f"data: {json.dumps({'type':'done'}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type':'error','error':str(e)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            event_generator_agent(),
            media_type="text/event-stream",
            headers={"Cache-Control":"no-cache", "Connection":"keep-alive", "X-Accel-Buffering":"no"}
        )

    async def event_generator():
        try:
            # 1. 開始イベント
            yield f"data: {json.dumps({'type':'start','thread_id':thread_id}, ensure_ascii=False)}\n\n"

            # 2. ストリーミング応答を生成
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                # 社員直接対話モード or 秘書モードでシステムプロンプトを切り替え
                if is_secretary:
                    from services.secretary_chat import SECRETARY_CHAT_SYSTEM
                    emps = await db.execute_fetchall(
                        """SELECT employee_name, display_name, category
                           FROM ai_employee_config WHERE is_active=1"""
                    )
                    employees_str = "\n".join(
                        f"- {e['employee_name']} ({e['display_name']}): {e['category']}" for e in emps
                    )
                    system_prompt = SECRETARY_CHAT_SYSTEM.format(employees_str=employees_str)
                else:
                    # 社員直接対話: その社員のSKILL.mdとスキル一覧を入れる
                    emp_rows = await db.execute_fetchall(
                        "SELECT * FROM ai_employee_config WHERE id=?", (employee_id,)
                    )
                    emp = dict(emp_rows[0]) if emp_rows else {}
                    skill_rows = await db.execute_fetchall(
                        """SELECT s.skill_name, s.description FROM ai_employee_skills aes
                           JOIN skill_definitions s ON s.id=aes.skill_id
                           WHERE aes.employee_id=?""",
                        (employee_id,)
                    )
                    skill_list = "\n".join(
                        f"- {s['skill_name']}: {(s['description'] or '')[:80]}"
                        for s in skill_rows
                    )
                    primary_skill = emp.get("primary_skill") or "secretary"
                    # SKILL.md を読む
                    from integrations.skill_runner import _resolve_skill_path
                    try:
                        skill_md = _resolve_skill_path(primary_skill).read_text(encoding="utf-8")
                    except Exception:
                        skill_md = ""
                    system_prompt = (
                        skill_md
                        + f"\n\n## あなた\nあなたは「{emp.get('display_name','社員')}」です。\n"
                        + f"\n## 持ちスキル\n{skill_list}\n"
                        + "\n依頼に応じて持ちスキルを活用して応答してください。"
                    )

                history = await db.execute_fetchall(
                    "SELECT role, message FROM conversation_log WHERE thread_id=? ORDER BY created_at DESC LIMIT 10",
                    (thread_id,)
                )

            messages = [{"role": "system", "content": system_prompt}]
            for h in reversed(list(history)):
                if h["role"] in ("user", "assistant"):
                    messages.append({"role": h["role"], "content": h["message"]})
            messages.append({"role": "user", "content": enriched_message})

            # LLM を呼び出してストリーム
            from llm.config import get_openai_client, LLMProvider
            try:
                provider_enum = LLMProvider(body.provider or "ollama")
            except ValueError:
                provider_enum = LLMProvider.OLLAMA
            client = get_openai_client(provider_enum, dict(os.environ))

            full_text = ""
            try:
                stream = await client.chat.completions.create(
                    model=body.model or "qwen2.5:7b",
                    messages=messages,
                    stream=True,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        full_text += delta
                        yield f"data: {json.dumps({'type':'text','delta':delta}, ensure_ascii=False)}\n\n"
            except Exception as stream_err:
                # ストリーム非対応なら一括取得
                response = await client.chat.completions.create(
                    model=body.model or "qwen2.5:7b",
                    messages=messages,
                )
                full_text = response.choices[0].message.content or ""
                yield f"data: {json.dumps({'type':'text','delta':full_text}, ensure_ascii=False)}\n\n"

            # 3. アクション抽出（タスク自動分解）
            import re
            actions = []
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', full_text, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(1))
                    if parsed.get("action") == "execute_tasks":
                        from services.secretary_chat import _create_and_dispatch
                        actions = await _create_and_dispatch(user_message, parsed.get("tasks", []))
                        if actions:
                            yield f"data: {json.dumps({'type':'tasks','tasks':actions}, ensure_ascii=False)}\n\n"
                except Exception as e:
                    print(f"[stream] アクション解析失敗: {e}")

            # 4. 返答を保存
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    """INSERT INTO conversation_log
                       (channel, with_employee, role, message, thread_id)
                       VALUES (?, ?, 'assistant', ?, ?)""",
                    (f"web_{channel}", employee_id, full_text[:5000], thread_id)
                )
                # スレッド最終アクティブ更新
                await db.execute(
                    "UPDATE threads SET last_active_at=datetime('now','localtime') WHERE id=?",
                    (thread_id,)
                )
                # スレッドのタイトルがデフォルトのままなら最初の発言から自動命名
                await db.execute(
                    """UPDATE threads SET title=?
                       WHERE id=? AND (title='新しいチャット' OR title IS NULL)""",
                    (user_message[:30], thread_id)
                )
                await db.commit()

            # 5. 完了イベント
            yield f"data: {json.dumps({'type':'done','full_text':full_text[:200]}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type':'error','error':str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":  "no-cache",
            "Connection":     "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
