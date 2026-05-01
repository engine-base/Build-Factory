"""
slack_block_kit.py — Tool-UI ブロック → Slack Block Kit 変換器

Web画面で動く25種類の Tool-UI ブロックを Slack Block Kit 形式に変換し、
Slack上でも見やすい構造化メッセージとして表示できるようにする。

主な制約:
  - スライダー/複雑フォームは Slack に無いので簡易代替
  - グラフは画像生成 or テキスト棒グラフで代替
  - リアルタイム更新不可（一度投稿したら静的）
"""

import json
import re
from typing import Optional


# ─────────────────────────────────────────────
# メインエントリ
# ─────────────────────────────────────────────

def render_message_for_slack(text: str) -> tuple[str, list[dict]]:
    """
    テキストから tool-ui ブロックを抽出し、Slack 用の (text, blocks) を返す。

    Returns:
        (slack_text, slack_blocks)
        - slack_text: tool-ui部分を除いたプレーンテキスト
        - slack_blocks: Block Kit のブロック配列
    """
    blocks: list[dict] = []
    remaining = text

    # tool-ui コードブロックを抽出
    pattern = re.compile(r'```tool-ui\s*([\s\S]*?)```', re.MULTILINE)
    for match in pattern.finditer(text):
        try:
            data = json.loads(match.group(1).strip())
            converted = convert_tool_ui_to_slack(data)
            if converted:
                blocks.extend(converted)
        except Exception as e:
            print(f"[slack_block_kit] パース失敗: {e}")

    # tool-uiブロックを除いた残テキスト
    remaining = pattern.sub("", text).strip()

    # 残テキストを先頭の section ブロックとして追加
    if remaining and len(remaining) > 0:
        # Slackは1セクション3000字制限
        for chunk in _chunks(remaining, 2900):
            blocks.insert(0, _section(chunk))

    return remaining, blocks


def convert_tool_ui_to_slack(block: dict) -> list[dict]:
    """1個のtool-uiブロックをSlack Block Kit配列に変換する。"""
    btype = block.get("type", "")
    data  = block.get("data", block)
    converter = CONVERTERS.get(btype)
    if not converter:
        return [_section(f"_未対応のtool-ui: {btype}_")]
    try:
        return converter(data)
    except Exception as e:
        return [_section(f"_変換失敗 ({btype}): {e}_")]


# ─────────────────────────────────────────────
# Block Kit ヘルパー
# ─────────────────────────────────────────────

def _section(text: str, fields: Optional[list[dict]] = None, accessory: Optional[dict] = None) -> dict:
    block: dict = {"type": "section", "text": {"type": "mrkdwn", "text": text[:2900]}}
    if fields:
        block["fields"] = fields[:10]
    if accessory:
        block["accessory"] = accessory
    return block


def _header(text: str) -> dict:
    return {"type": "header", "text": {"type": "plain_text", "text": text[:150], "emoji": True}}


def _divider() -> dict:
    return {"type": "divider"}


def _context(items: list[str]) -> dict:
    return {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": s[:150]} for s in items[:10]]
    }


def _actions(buttons: list[dict]) -> dict:
    return {"type": "actions", "elements": buttons[:25]}


def _button(text: str, value: str, action_id: str, style: Optional[str] = None) -> dict:
    btn: dict = {
        "type": "button",
        "text": {"type": "plain_text", "text": text[:75], "emoji": True},
        "value": value[:2000],
        "action_id": action_id,
    }
    if style in ("primary", "danger"):
        btn["style"] = style
    return btn


def _image(url: str, alt: str = "image", title: Optional[str] = None) -> dict:
    block: dict = {"type": "image", "image_url": url, "alt_text": alt[:2000]}
    if title:
        block["title"] = {"type": "plain_text", "text": title[:150], "emoji": True}
    return block


def _chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i:i + size]


# ─────────────────────────────────────────────
# 各 tool-ui タイプの変換器
# ─────────────────────────────────────────────

# ── INPUT ────────────────────────────────────

def conv_option_list(d: dict) -> list[dict]:
    blocks: list[dict] = []
    if d.get("title"):
        blocks.append(_header(f"📋 {d['title']}"))
    options = d.get("options", [])[:25]
    buttons = []
    for o in options:
        oid = str(o.get("id") or o.get("value") or o.get("label", ""))
        buttons.append(_button(o.get("label") or o.get("title", ""), oid, f"option_{oid}"))
    if buttons:
        blocks.append(_actions(buttons))
    return blocks


def conv_parameter_slider(d: dict) -> list[dict]:
    title = d.get("title", "パラメータ")
    params = d.get("params", [{"name": d.get("label"), **d}])
    lines = [f"*🎚 {title}*"]
    for p in params:
        lines.append(f"• {p.get('name','')}: 範囲 {p.get('min',0)}〜{p.get('max',100)}（既定: {p.get('default','-')}{p.get('unit','')}）")
    return [_section("\n".join(lines))]


def conv_preference_panel(d: dict) -> list[dict]:
    title = d.get("title", "設定")
    lines = [f"*⚙️ {title}*"]
    for f in d.get("fields", []):
        default = d.get("defaults", {}).get(f["name"], "")
        lines.append(f"• {f['label']}: `{default}`")
    return [_section("\n".join(lines))]


def conv_question_flow(d: dict) -> list[dict]:
    title = d.get("title", "ヒアリング")
    questions = d.get("questions", [])
    blocks = [_header(f"❓ {title}")]
    for i, q in enumerate(questions[:5], 1):
        text = f"*Q{i}.* {q.get('text','')}"
        if q.get("choices"):
            text += "\n" + "\n".join(f"  • {c}" for c in q["choices"])
        blocks.append(_section(text))
    return blocks


# ── DISPLAY ──────────────────────────────────

def conv_citations(d: dict) -> list[dict]:
    title = d.get("title", "引用元")
    lines = [f"*📚 {title}*"]
    for i, s in enumerate(d.get("sources", []), 1):
        lines.append(f"[{i}] *<{s.get('url','')}|{s.get('title','')}>*")
        if s.get("snippet"):
            lines.append(f"   _{s['snippet'][:200]}_")
    return [_section("\n".join(lines))]


def conv_link_preview(d: dict) -> list[dict]:
    text = f"*<{d.get('url','')}|{d.get('heading') or d.get('title','リンク')}>*"
    if d.get("description"):
        text += f"\n{d['description'][:300]}"
    accessory = None
    if d.get("image"):
        accessory = {"type": "image", "image_url": d["image"], "alt_text": "preview"}
    return [_section(text, accessory=accessory)]


def conv_stats(d: dict) -> list[dict]:
    title = d.get("title", "数値")
    blocks = [_header(f"📊 {title}")]
    fields = []
    for s in d.get("stats", [])[:10]:
        delta_str = f"\n_{s['delta']}_" if s.get("delta") else ""
        fields.append({
            "type": "mrkdwn",
            "text": f"*{s.get('label','')}*\n*{s.get('value','')}*{delta_str}"
        })
    if fields:
        blocks.append(_section(" ", fields=fields))
    return blocks


def conv_terminal(d: dict) -> list[dict]:
    lines = d.get("lines", [])
    code = "\n".join(lines)
    return [_section(f"*🖥 {d.get('title','Terminal')}*\n```{code[:2700]}```")]


def conv_weather(d: dict) -> list[dict]:
    text = (
        f"*🌤 {d.get('location','天気')}*\n"
        f"*{d.get('temp','-')}°* {d.get('condition','')}\n"
        f"_体感 {d.get('feels_like','-')}° / 湿度 {d.get('humidity','-')}%_"
    )
    return [_section(text)]


def conv_map(d: dict) -> list[dict]:
    text = f"*📍 {d.get('title','地図')}*\n{d.get('location','')}"
    if d.get("lat") and d.get("lng"):
        text += f"\n座標: {d['lat']}, {d['lng']}"
    if d.get("places"):
        text += "\n\n*周辺:*\n" + "\n".join(f"• {p['name']} ({p.get('distance','-')})" for p in d["places"])
    return [_section(text)]


def conv_carousel(d: dict) -> list[dict]:
    title = d.get("title", "カルーセル")
    blocks = [_header(f"🎠 {title}")]
    for it in d.get("items", [])[:10]:
        text = f"*{it.get('title','')}*"
        if it.get("subtitle"):
            text += f"\n{it['subtitle']}"
        accessory = None
        if it.get("image"):
            accessory = {"type": "image", "image_url": it["image"], "alt_text": it.get("title","")}
        blocks.append(_section(text, accessory=accessory))
    return blocks


# ── ARTIFACTS ────────────────────────────────

def conv_chart(d: dict) -> list[dict]:
    title = d.get("title", "チャート")
    items = d.get("data", [])
    if not items:
        return [_section(f"*📈 {title}*\n_(データなし)_")]
    max_v = max(item.get("value", 0) for item in items) or 1
    lines = [f"*📈 {title}*", "```"]
    for it in items:
        bar_len = int((it.get("value", 0) / max_v) * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        lines.append(f"{str(it.get('label',''))[:14]:<14} {bar} {it.get('value','')}")
    lines.append("```")
    return [_section("\n".join(lines))]


def conv_code_block(d: dict) -> list[dict]:
    title = d.get("title", "コード")
    lang = d.get("lang", "")
    code = d.get("code", "")[:2700]
    return [_section(f"*💻 {title}*\n```{lang}\n{code}\n```")]


def conv_diff(d: dict) -> list[dict]:
    title = d.get("title", "Diff")
    lines = []
    for l in d.get("lines", []):
        prefix = "+" if l.get("type") == "add" else "-" if l.get("type") == "del" else " "
        lines.append(f"{prefix} {l.get('text','')}")
    code = "\n".join(lines)[:2700]
    return [_section(f"*🔀 {title}*\n```diff\n{code}\n```")]


def conv_table(d: dict) -> list[dict]:
    title   = d.get("title", "テーブル")
    columns = d.get("columns", [])
    rows    = d.get("rows", [])
    if not columns or not rows:
        return [_section(f"*📋 {title}*\n_(データなし)_")]
    # markdown表
    out = [f"*📋 {title}*", "```"]
    out.append(" | ".join(str(c) for c in columns))
    out.append("-" * (sum(len(str(c)) for c in columns) + 3 * len(columns)))
    for r in rows[:20]:
        out.append(" | ".join(str(r.get(c, ""))[:30] for c in columns))
    out.append("```")
    return [_section("\n".join(out)[:2900])]


def conv_draft(d: dict) -> list[dict]:
    title = d.get("title", "ドラフト")
    blocks = [_header(f"✉️ {title}")]
    if d.get("subject"):
        blocks.append(_context([f"件名: {d['subject']}"]))
    if d.get("body"):
        blocks.append(_section(d["body"][:2900]))
    return blocks


def conv_social_post(d: dict) -> list[dict]:
    platform = d.get("platform", "投稿")
    body = d.get("body", "")
    blocks = [_header(f"#️⃣ {platform}")]
    blocks.append(_section(body[:2900]))
    if d.get("tags"):
        blocks.append(_context([f"#{t}" for t in d["tags"][:10]]))
    blocks.append(_context([f"{len(body)}文字"]))
    return blocks


# ── CONFIRMATION ────────────────────────────

def conv_approval_card(d: dict) -> list[dict]:
    title = d.get("title", "承認確認")
    blocks = [_header(f"⚠️ {title}")]
    if d.get("description"):
        blocks.append(_section(d["description"][:2900]))
    if d.get("details"):
        fields = [
            {"type": "mrkdwn", "text": f"*{k}*\n{v}"} for k, v in d["details"].items()
        ][:10]
        if fields:
            blocks.append(_section(" ", fields=fields))
    approval_id = d.get("approval_id") or d.get("id", "")
    buttons = [
        _button("✅ 承認", f"approve:{approval_id}", f"approve_{approval_id}", style="primary"),
        _button("❌ 却下", f"reject:{approval_id}", f"reject_{approval_id}", style="danger"),
    ]
    if approval_id:
        blocks.append(_actions(buttons))
        blocks.append(_context([f"または `承認 {approval_id}` / `却下 {approval_id}` で返信"]))
    return blocks


def conv_order_summary(d: dict) -> list[dict]:
    title = d.get("title", "注文内容")
    items = d.get("items", [])
    blocks = [_header(f"🛒 {title}")]
    lines = []
    total = 0
    for it in items:
        qty = it.get("qty", 1)
        price = it.get("price", 0)
        sub = price * qty
        total += sub
        lines.append(f"• {it.get('name','')} × {qty} ……… ¥{sub:,}")
    blocks.append(_section("\n".join(lines)))
    blocks.append(_divider())
    blocks.append(_section(f"*合計: ¥{total:,}*"))
    return blocks


# ── MEDIA ────────────────────────────────────

def conv_image_gallery(d: dict) -> list[dict]:
    title = d.get("title", "ギャラリー")
    blocks = [_header(f"🖼 {title}")]
    for img in d.get("images", [])[:10]:
        blocks.append(_image(img.get("url", ""), img.get("alt", ""), img.get("caption")))
    return blocks


def conv_video(d: dict) -> list[dict]:
    title = d.get("title", "動画")
    url = d.get("url", "")
    blocks = [_header(f"🎬 {title}")]
    if url:
        blocks.append(_section(f"<{url}|▶️ 再生>"))
    if d.get("description"):
        blocks.append(_section(d["description"]))
    return blocks


def conv_audio(d: dict) -> list[dict]:
    title = d.get("title", "音声")
    url = d.get("url", "")
    blocks = [_header(f"🎵 {title}")]
    if url:
        blocks.append(_section(f"<{url}|▶️ 再生>"))
    if d.get("description"):
        blocks.append(_section(d["description"]))
    return blocks


# ── PROGRESS ─────────────────────────────────

def conv_plan(d: dict) -> list[dict]:
    title = d.get("title", "プラン")
    blocks = [_header(f"🎯 {title}")]
    lines = []
    for i, s in enumerate(d.get("steps", []), 1):
        check = "✅" if s.get("done") else f"`{i}.`"
        line = f"{check} *{s.get('title','')}*"
        if s.get("description"):
            line += f"\n   _{s['description'][:200]}_"
        lines.append(line)
    blocks.append(_section("\n".join(lines)))
    return blocks


def conv_progress_tracker(d: dict) -> list[dict]:
    title   = d.get("title", "進捗")
    current = d.get("current", 0)
    total   = d.get("total", 1) or 1
    pct     = round((current / total) * 100)
    bar_len = 20
    filled  = int((pct / 100) * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)

    text = f"*⏱ {title}*\n```{bar} {pct}%```"
    if d.get("tasks"):
        text += "\n" + "\n".join(
            f"{'✅' if t.get('done') else '⬜'} {t.get('name','')}" for t in d["tasks"]
        )
    return [_section(text)]


# ─────────────────────────────────────────────
# レジストリ
# ─────────────────────────────────────────────

CONVERTERS = {
    "option-list":      conv_option_list,
    "parameter-slider": conv_parameter_slider,
    "preference-panel": conv_preference_panel,
    "question-flow":    conv_question_flow,
    "citations":        conv_citations,
    "link-preview":     conv_link_preview,
    "stats":            conv_stats,
    "terminal":         conv_terminal,
    "weather":          conv_weather,
    "map":              conv_map,
    "carousel":         conv_carousel,
    "chart":            conv_chart,
    "code-block":       conv_code_block,
    "diff":             conv_diff,
    "table":            conv_table,
    "draft":            conv_draft,
    "social-post":      conv_social_post,
    "approval-card":    conv_approval_card,
    "order-summary":    conv_order_summary,
    "image-gallery":    conv_image_gallery,
    "video":            conv_video,
    "audio":            conv_audio,
    "plan":             conv_plan,
    "progress-tracker": conv_progress_tracker,
}
