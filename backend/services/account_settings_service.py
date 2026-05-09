"""
account_settings_service.py — アカウントごとの発行者情報・テンプレ設定を管理。

提案書・見積書フェーズで自動的に流し込まれる「発行者情報」を保持する。
JSONB の template_config はテンプレビルダースキルが組み立てる構造を保存。
"""
from __future__ import annotations

import json
from typing import Any, Optional

from db import async_db as adb
from db.queries import DB_PATH


# ──────────────────────────────────────────
# JSONB フィールドのリスト (read 時に dict/list へデコード)
# ──────────────────────────────────────────
_JSON_FIELDS = ("achievement_stats", "case_studies", "default_notes", "template_config")


def _normalize_row(row: dict) -> dict:
    """psycopg は JSONB を既に dict/list にデコードしてくれるが、
    SQLite アダプタ等で str のまま来た場合に備えて変換。"""
    if not row:
        return {}
    out = dict(row)
    for k in _JSON_FIELDS:
        v = out.get(k)
        if isinstance(v, str):
            try:
                out[k] = json.loads(v)
            except Exception:
                out[k] = [] if k != "template_config" else {}
    return out


# ──────────────────────────────────────────
# CRUD
# ──────────────────────────────────────────
async def get_settings(account_id: int) -> dict:
    """account_settings 1 行を取得。なければ空 dict。"""
    async with adb.connect(DB_PATH) as db:
        db.row_factory = adb.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM account_settings WHERE account_id=?",
            (account_id,),
        )
    if not rows:
        return {}
    return _normalize_row(dict(rows[0]))


async def upsert_settings(account_id: int, patch: dict) -> dict:
    """部分更新。既存があれば patch でマージ・無ければ新規作成。"""
    existing = await get_settings(account_id)
    is_new = not existing

    # JSON フィールドは patch 値をそのまま採用 (上書き)
    merged = dict(existing)
    merged.update(patch)
    merged["account_id"] = account_id

    if is_new:
        if not merged.get("company_name"):
            merged["company_name"] = "(未設定)"
        return await _insert(merged)

    return await _update(account_id, patch)


async def _insert(data: dict) -> dict:
    """新規 INSERT。"""
    cols = []
    vals = []
    placeholders = []
    for k, v in data.items():
        cols.append(k)
        if k in _JSON_FIELDS and v is not None and not isinstance(v, str):
            vals.append(json.dumps(v, ensure_ascii=False))
        else:
            vals.append(v)
        placeholders.append("?")

    sql = f"INSERT INTO account_settings ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
    async with adb.connect(DB_PATH) as db:
        await db.execute(sql, tuple(vals))
        await db.commit()
    return await get_settings(data["account_id"])


async def _update(account_id: int, patch: dict) -> dict:
    """UPDATE — patch のキーのみ更新。"""
    if not patch:
        return await get_settings(account_id)

    sets = []
    vals = []
    for k, v in patch.items():
        if k == "account_id":
            continue
        sets.append(f"{k}=?")
        if k in _JSON_FIELDS and v is not None and not isinstance(v, str):
            vals.append(json.dumps(v, ensure_ascii=False))
        else:
            vals.append(v)

    if not sets:
        return await get_settings(account_id)

    # updated_at も更新
    sets.append("updated_at=NOW()")

    sql = f"UPDATE account_settings SET {', '.join(sets)} WHERE account_id=?"
    vals.append(account_id)

    async with adb.connect(DB_PATH) as db:
        await db.execute(sql, tuple(vals))
        await db.commit()
    return await get_settings(account_id)


async def delete_settings(account_id: int) -> None:
    """account_settings 削除 (アカウント削除時のみ呼ぶこと)。"""
    async with adb.connect(DB_PATH) as db:
        await db.execute("DELETE FROM account_settings WHERE account_id=?", (account_id,))
        await db.commit()


# ──────────────────────────────────────────
# 提案書・見積書フェーズから利用するヘルパー
# ──────────────────────────────────────────
async def get_or_create_default(account_id: int) -> dict:
    """設定が無ければデフォルト値で作成して返す。"""
    s = await get_settings(account_id)
    if s:
        return s
    return await upsert_settings(account_id, {
        "company_name": "(未設定 — 設定画面から会社情報を入力してください)",
        "primary_color": "#004CD9",
        "estimate_prefix": "EST",
        "proposal_prefix": "PROP",
        "warranty_days": 90,
        "estimate_validity_days": 30,
        "tax_rate": 0.10,
        "achievement_stats": [],
        "case_studies": [],
        "default_notes": [],
        "template_config": {},
    })


async def render_issuer_block(account_id: int) -> dict:
    """発行者情報のサブセットを返す (HTML テンプレ置換用)。"""
    s = await get_or_create_default(account_id)
    return {
        "company_name":         s.get("company_name", ""),
        "company_name_kana":    s.get("company_name_kana", ""),
        "representative":       f"{s.get('representative_title','')} {s.get('representative_name','')}".strip(),
        "address":              f"〒{s.get('postal_code','')} {s.get('address','')}".strip(),
        "phone":                s.get("phone", ""),
        "email":                s.get("email", ""),
        "website":              s.get("website", ""),
        "bank":                 {
            "name":           s.get("bank_name", ""),
            "branch":         s.get("bank_branch", ""),
            "account_type":   s.get("bank_account_type", ""),
            "account_number": s.get("bank_account_number", ""),
            "account_holder": s.get("bank_account_holder", ""),
        },
        "logo_url":     s.get("logo_url", ""),
        "stamp_url":    s.get("stamp_url", ""),
        "stamp_text":   s.get("stamp_text", ""),
        "primary_color": s.get("primary_color", "#004CD9"),
    }


def build_ai_context_block(settings: dict) -> str:
    """AI system prompt に挿入する「発行者情報」コンテキスト。
    クライアント情報と取り違えないよう、明確にラベル付け。"""
    if not settings:
        return ""
    issuer_lines = []
    if settings.get("company_name"):
        issuer_lines.append(f"発行者会社名: {settings['company_name']}")
    if settings.get("representative_name"):
        rep_title = settings.get("representative_title", "")
        issuer_lines.append(f"代表者: {rep_title} {settings['representative_name']}".strip())
    if settings.get("address"):
        issuer_lines.append(f"住所: 〒{settings.get('postal_code','')} {settings['address']}")
    if settings.get("phone") or settings.get("email"):
        issuer_lines.append(f"連絡: {settings.get('phone','')} / {settings.get('email','')}")
    if settings.get("bank_name"):
        issuer_lines.append(
            f"振込先: {settings['bank_name']} {settings.get('bank_branch','')} "
            f"({settings.get('bank_account_type','')}) {settings.get('bank_account_number','')} "
            f"{settings.get('bank_account_holder','')}"
        )

    achievements = settings.get("achievement_stats") or []
    if achievements:
        ach_str = " / ".join(f"{a.get('value','?')} {a.get('label','')}" for a in achievements)
        issuer_lines.append(f"実績: {ach_str}")

    defaults = []
    if settings.get("payment_terms_default"):
        defaults.append(f"支払条件 {settings['payment_terms_default']}")
    if settings.get("warranty_days"):
        defaults.append(f"保証 {settings['warranty_days']}日")
    if settings.get("monthly_maintenance_yen"):
        defaults.append(f"月額保守 {settings['monthly_maintenance_yen']:,}円")
    if settings.get("estimate_validity_days"):
        defaults.append(f"見積有効期限 {settings['estimate_validity_days']}日")
    if defaults:
        issuer_lines.append("デフォルト条件: " + " / ".join(defaults))

    body = "\n".join(f"- {line}" for line in issuer_lines)
    return f"""# 発行者情報 (重要・クライアント情報と混同しないこと)
これはあなた (PM AI) が所属する会社の情報です。提案書・見積書の「発行者欄」「振込先欄」「実績欄」にそのまま流し込んでください。
クライアント (案件依頼元) の情報とは別物です。

{body}
"""
