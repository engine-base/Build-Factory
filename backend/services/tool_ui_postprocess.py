"""
tool_ui_postprocess.py — Agent 出力の整形と Tool-UI 自動補完。

- ストリーミング途中の JSON 断片漏れ（{} など）を除去
- 番号付き選択肢を option-list ブロックに自動変換
- tool-ui ブロックの簡易スキーマ検証
"""

from __future__ import annotations

import json
import re


# ──────────────────────────────────────────────────────
# JSON 断片の漏れ除去
# ──────────────────────────────────────────────────────

JSON_LEAK_HEAD = re.compile(r'^\s*(\{\s*\}|\[\s*\]|null|true|false)\s*', re.IGNORECASE)


def strip_json_artifacts(text: str) -> str:
    """先頭にツール戻り値の JSON 断片（{}/[]/null）が漏れていたら除去する。"""
    if not text:
        return text
    cleaned = JSON_LEAK_HEAD.sub("", text)
    return cleaned


# ──────────────────────────────────────────────────────
# ストリーミング用 Tool-UI バッファ
# ──────────────────────────────────────────────────────

class ToolUIStreamBuffer:
    """tool-ui ブロックの途中漏れを防ぐストリーミングバッファ。

    使い方:
        buf = ToolUIStreamBuffer()
        for delta in stream:
            for safe_chunk in buf.feed(delta):
                yield safe_chunk
        for tail in buf.flush():
            yield tail
    """

    OPEN_PATTERNS = [
        re.compile(r"`{1,2}$"),                     # ``  begin
        re.compile(r"```$"),                        # ``` begin
        re.compile(r"```t$"), re.compile(r"```to$"), re.compile(r"```too$"),
        re.compile(r"```tool$"), re.compile(r"```tool-$"),
        re.compile(r"```tool-u$"), re.compile(r"```tool-ui$"),
        re.compile(r"```tool-ui[\s\S]*$"),
    ]

    def __init__(self):
        self._buf = ""
        self._inside_tool_ui = False

    def feed(self, delta: str) -> list[str]:
        """新たな delta を受け取り、安全に flush できる文字列のリストを返す。"""
        out: list[str] = []
        if not delta:
            return out
        self._buf += delta

        while True:
            if self._inside_tool_ui:
                # 閉じる ``` を探す
                end = self._buf.find("```", 4)  # 開始の ```tool-ui の後を探す
                if end == -1:
                    # まだ閉じ無し → 全部保留
                    return out
                # 閉じが見つかった → 完全なブロックを flush
                close_pos = end + 3
                out.append(self._buf[:close_pos])
                self._buf = self._buf[close_pos:]
                self._inside_tool_ui = False
                continue
            else:
                # tool-ui の開始を探す
                start = self._buf.find("```tool-ui")
                if start == -1:
                    # 末尾に「途中まで開いている」可能性チェック
                    # ` / `` / ``` / ```t / ```to ... 形を保留
                    safe_until = self._safe_emit_until(self._buf)
                    if safe_until > 0:
                        out.append(self._buf[:safe_until])
                        self._buf = self._buf[safe_until:]
                    return out
                # 開始の前を flush
                if start > 0:
                    out.append(self._buf[:start])
                    self._buf = self._buf[start:]
                # 残りは tool-ui ブロック開始
                self._inside_tool_ui = True
                # 次ループで閉じを探す

    def _safe_emit_until(self, text: str) -> int:
        """末尾が tool-ui の途中じゃないことを確認し、安全な flush 位置を返す。"""
        # 末尾の ` 連続を保留
        i = len(text)
        # 末尾から ` の連続を数える
        while i > 0 and text[i - 1] == "`":
            i -= 1
        if i == len(text):
            # 末尾に ` がない → 全部 emit OK
            # ただし末尾が "```tool-ui" 形に向かっていないか確認
            # （途中の `tool` 等のキーワード）
            tail = text[-15:]
            for pat_text in ["`", "``", "```", "```t", "```to", "```too",
                             "```tool", "```tool-", "```tool-u", "```tool-ui"]:
                if tail.endswith(pat_text):
                    return len(text) - len(pat_text)
            return len(text)
        return i

    def flush(self) -> list[str]:
        """残りバッファを全部出す（ストリーム終了時）。
        未完の tool-ui ブロックは破棄する（漏れを防ぐ）。"""
        if self._inside_tool_ui:
            # 未完の tool-ui は捨てる
            self._buf = ""
            self._inside_tool_ui = False
            return []
        out = [self._buf] if self._buf else []
        self._buf = ""
        return out

# ──────────────────────────────────────────────────────
# 数字付き選択肢の検出 (1. xxx / 2. yyy)
# ──────────────────────────────────────────────────────
NUMBERED_LINE = re.compile(r"^\s*(\d+)[\.\)）]\s*\*{0,2}([^\n*]+?)\*{0,2}\s*$", re.MULTILINE)


def _detect_numbered_choices(text: str) -> list[dict] | None:
    """
    本文末尾近くに『1. リーダー / 2. メンバー』パターンがあれば抽出。
    2〜5個の連続した番号付き短い項目（30字以下）を検出。
    """
    matches = list(NUMBERED_LINE.finditer(text))
    if len(matches) < 2 or len(matches) > 5:
        return None

    # 連続した番号で 1, 2, 3, ... と並んでいるか
    nums = [int(m.group(1)) for m in matches]
    if nums != list(range(1, len(nums) + 1)):
        return None

    # 各項目が短い（=本格的な見出しではない）
    options = []
    for m in matches:
        label = m.group(2).strip()
        if len(label) > 60 or "\n" in label:
            return None
        # 「:」「：」で説明分割
        desc = ""
        if ":" in label or "：" in label:
            sep = ":" if ":" in label else "："
            parts = label.split(sep, 1)
            label = parts[0].strip()
            desc = parts[1].strip() if len(parts) > 1 else ""
        options.append({"label": label, **({"description": desc} if desc else {})})

    return options


def _detect_approval_intent(text: str) -> bool:
    """承認確認文を求めている雰囲気を検知。"""
    keywords = [
        "よろしいでしょうか", "よろしいですか", "進めてよろしい", "実行してよろしい",
        "承認をお願い", "確認をお願い", "OK と返答", "OKと返答",
        "問題なければ", "進めますがよろしい",
    ]
    tail = text[-400:]
    return any(k in tail for k in keywords)


def _has_existing_tool_ui(text: str) -> bool:
    return "```tool-ui" in text


def auto_inject_tool_ui(text: str) -> str:
    """
    Agent 出力に Tool-UI が含まれていなければ、パターン検知で自動補完する。
    """
    if not text:
        return text

    # 先頭の JSON 漏れを除去
    text = strip_json_artifacts(text)

    if _has_existing_tool_ui(text):
        text = validate_tool_ui_blocks(text)
        return text

    options = _detect_numbered_choices(text)
    if not options:
        return text

    block = {
        "type": "option-list",
        "data": {"title": "選択肢", "options": options},
    }
    suffix = "\n\n```tool-ui\n" + json.dumps(block, ensure_ascii=False) + "\n```"
    return text.rstrip() + suffix


# ──────────────────────────────────────────────────────
# Tool-UI ブロックの簡易スキーマ検証
# ──────────────────────────────────────────────────────

VALID_TOOL_UI_TYPES = {
    "option-list", "parameter-slider", "preference-panel", "question-flow",
    "citations", "link-preview", "stats", "terminal", "weather", "map", "carousel",
    "chart", "code-block", "diff", "table", "draft", "social-post",
    "approval-card", "order-summary",
    "image-gallery", "video", "audio",
    "plan", "progress-tracker",
}


def validate_tool_ui_blocks(text: str) -> str:
    """tool-ui ブロックを正規化する。
    - JSON が壊れていれば削除
    - type が未知なら削除
    - data フィールドが無ければ {}/{}を補完
    """
    pattern = re.compile(r"```tool-ui\s*([\s\S]*?)```")
    def fix(m: re.Match) -> str:
        raw = m.group(1).strip()
        try:
            obj = json.loads(raw)
        except Exception:
            # 壊れた JSON はブロックごと削除
            return ""
        if not isinstance(obj, dict):
            return ""
        ui_type = obj.get("type")
        if ui_type not in VALID_TOOL_UI_TYPES:
            return ""
        if "data" not in obj or not isinstance(obj.get("data"), dict):
            obj["data"] = {k: v for k, v in obj.items() if k != "type"}
            obj = {"type": ui_type, "data": obj["data"]}
        return "```tool-ui\n" + json.dumps(obj, ensure_ascii=False) + "\n```"
    return pattern.sub(fix, text)
