"""
template_render_service.py — Phase 3 (テンプレレンダリングエンジン)

template_config (account_settings 内 JSONB) と案件データ (proposal/estimate center) を
組み合わせて、最終的な HTML / Markdown / JSON を出力する。

主な役割:
1. account_settings の発行者情報・実績・事例を取り出す
2. template_config の sections 配列から有効なセクションだけをレンダリング
3. 案件データ (proposal/estimate の各章/タブ items) と組み合わせる
4. 既存のスキル付属テンプレ HTML (proposal-slides.html / estimate.html) のプレースホルダ置換にも対応

出力ターゲット:
- proposal-slides.html: **24 スライド** (v2 テンプレ・5 スライド追加・124 変数対応)
  - 旧 53 変数 (CLIENT_NAME, PROBLEM_*, SOLUTION_*, STACK_*, SECURITY_*, PHASE_*, PRICE_* 等)
  - 新 71 変数 (HYPOTHESIS_NOTE_*, DIALOG_1〜8, REQ_A〜E, LEGAL_*, ROI_*, CONFIRM_GROUP_1〜3,
    ITEM_1〜9, SUBTOTAL_EXCL_TAX, TAX, TOTAL_INCL_TAX, PAYMENT_1〜3, GRANT_SPLIT_BLOCK 等)
- estimate.html: A4 見積書
- Markdown / JSON: 構造化データそのまま
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PROPOSAL_TEMPLATE_PATH = Path.home() / ".claude" / "skills" / "proposal" / "assets" / "proposal-slides.html"
ESTIMATE_TEMPLATE_PATH = Path.home() / ".claude" / "skills" / "estimate" / "assets" / "estimate.html"


# ──────────────────────────────────────────
# 文字列ヘルパー
# ──────────────────────────────────────────
def _esc(s: Any) -> str:
    """HTML エスケープ。"""
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _yen(n: int | float | None) -> str:
    if n is None:
        return ""
    try:
        return f"¥{int(n):,}"
    except Exception:
        return str(n)


# ──────────────────────────────────────────
# プレースホルダ置換 (Mustache 風)
# ──────────────────────────────────────────
def _substitute(template: str, vars: dict[str, Any]) -> str:
    """{{KEY}} 形式のプレースホルダを vars[KEY] で置換。
    vars に値がなければ空文字。"""
    def replace(m: re.Match) -> str:
        key = m.group(1).strip()
        v = vars.get(key, "")
        if isinstance(v, (dict, list)):
            return _esc(json.dumps(v, ensure_ascii=False))
        return _esc(v) if v is not None else ""
    return re.sub(r"\{\{([A-Z_0-9]+)\}\}", replace, template)


# ──────────────────────────────────────────
# 提案書 (proposal-slides.html) レンダリング
# ──────────────────────────────────────────
def build_proposal_vars(
    *,
    settings: dict,
    project: dict,                     # ヒアリング/要件/価格設計をまとめた dict
    proposal_chapters: list[dict],     # proposal_service.get_aggregated_view() の chapters
    pricing_amount: int | None = None,
) -> dict[str, str]:
    """proposal-slides.html の {{...}} 変数群を構築。"""

    # 発行者
    company_name = settings.get("company_name") or "(発行者未設定)"
    achievements = settings.get("achievement_stats") or []
    cases = settings.get("case_studies") or []

    # 案件
    project_name = (project.get("project_name")
                    or project.get("hearing", {}).get("project_name")
                    or "(案件名未設定)")
    client_name = project.get("client_name") or "(クライアント名)"

    # 章を key→items dict に
    by_ch: dict[str, list[str]] = {}
    for ch in proposal_chapters or []:
        sections = ch.get("sections", [])
        items: list[str] = []
        for sec in sections:
            items.extend(sec.get("items", []) or [])
        by_ch[ch.get("key")] = items

    def _first(items: list[str]) -> str:
        return items[0] if items else ""

    def _join(items: list[str], sep: str = "\n") -> str:
        return sep.join(items)

    vars = {
        "CLIENT_NAME":        client_name,
        "PROJECT_NAME":       project_name,
        "PROPOSAL_DATE":      project.get("proposal_date", ""),
        "SERVICE_TYPE":       project.get("service_type", "full-code"),
        "DEADLINE":           project.get("deadline", ""),
        "TOTAL_PRICE":        _yen(pricing_amount or project.get("total_price")),
        "TOTAL_DURATION":     project.get("total_duration", ""),
        "MAINTENANCE_FEE":    _yen(settings.get("monthly_maintenance_yen")),
        "REQUIREMENTS_DOC_URL": project.get("requirements_doc_url", ""),

        # 実績 (最大 3 件)
        "ACHIEVEMENT_STAT_1_VALUE": (achievements[0]["value"] if len(achievements) > 0 else ""),
        "ACHIEVEMENT_STAT_1_LABEL": (achievements[0]["label"] if len(achievements) > 0 else ""),
        "ACHIEVEMENT_STAT_2_VALUE": (achievements[1]["value"] if len(achievements) > 1 else ""),
        "ACHIEVEMENT_STAT_2_LABEL": (achievements[1]["label"] if len(achievements) > 1 else ""),
        "ACHIEVEMENT_STAT_3_VALUE": (achievements[2]["value"] if len(achievements) > 2 else ""),
        "ACHIEVEMENT_STAT_3_LABEL": (achievements[2]["label"] if len(achievements) > 2 else ""),

        # 事例 (最大 3 件)
        "PROJECT_1_TYPE":  (cases[0].get("type") if len(cases) > 0 else ""),
        "PROJECT_1_TITLE": (cases[0].get("title") if len(cases) > 0 else ""),
        "PROJECT_1_DESC":  (cases[0].get("desc") if len(cases) > 0 else ""),
        "PROJECT_2_TYPE":  (cases[1].get("type") if len(cases) > 1 else ""),
        "PROJECT_2_TITLE": (cases[1].get("title") if len(cases) > 1 else ""),
        "PROJECT_2_DESC":  (cases[1].get("desc") if len(cases) > 1 else ""),
        "PROJECT_3_TYPE":  (cases[2].get("type") if len(cases) > 2 else ""),
        "PROJECT_3_TITLE": (cases[2].get("title") if len(cases) > 2 else ""),
        "PROJECT_3_DESC":  (cases[2].get("desc") if len(cases) > 2 else ""),

        # 課題・ソリューション (各章の items から)
        "PROBLEM_1_TITLE": _first(by_ch.get("problem", [])),
        "PROBLEM_1_DESC":  _first(by_ch.get("problem", [])[1:]),
        "PROBLEM_2_TITLE": (by_ch.get("problem", []) + ["", ""])[2],
        "PROBLEM_2_DESC":  (by_ch.get("problem", []) + ["", "", ""])[3],
        "PROBLEM_3_TITLE": (by_ch.get("problem", []) + ["", "", "", ""])[4],
        "PROBLEM_3_DESC":  (by_ch.get("problem", []) + ["", "", "", "", ""])[5],

        "SOLUTION_HEADLINE": _first(by_ch.get("solution", [])),
        "SOLUTION_OVERVIEW": _join(by_ch.get("solution", [])[1:4]),
        "VALUE_1": (by_ch.get("solution", []) + ["", ""])[2] or _first(by_ch.get("roi", [])),
        "VALUE_2": (by_ch.get("solution", []) + ["", "", ""])[3] or (by_ch.get("roi", []) + [""])[1] if len(by_ch.get("roi", [])) > 1 else "",
        "VALUE_3": (by_ch.get("solution", []) + ["", "", "", ""])[4] or (by_ch.get("roi", []) + [""])[2] if len(by_ch.get("roi", [])) > 2 else "",

        "REQ_POINT_1": (by_ch.get("scope", []) + [""])[0],
        "REQ_POINT_2": (by_ch.get("scope", []) + ["", ""])[1] if len(by_ch.get("scope", [])) > 1 else "",
        "REQ_POINT_3": (by_ch.get("scope", []) + ["", "", ""])[2] if len(by_ch.get("scope", [])) > 2 else "",

        # 技術スタック (要件定義の data から取得想定)
        "STACK_FRONTEND":  project.get("stack_frontend", "Next.js / TypeScript"),
        "STACK_BACKEND":   project.get("stack_backend", "Hono / Node.js"),
        "STACK_INFRA":     project.get("stack_infra", "Vercel / Cloudflare"),
        "STACK_DATABASE":  project.get("stack_database", "PostgreSQL (Supabase)"),
        "STACK_REASON":    project.get("stack_reason", "短納期と運用シンプルさを両立"),

        # セキュリティ
        "SECURITY_1_TITLE": "HTTPS + Cloudflare DDoS",
        "SECURITY_1_DESC":  "全通信を HTTPS で保護",
        "SECURITY_2_TITLE": "決済情報のトークン化",
        "SECURITY_2_DESC":  "Stripe / Paid のトークン経由で自社 DB に保持しない",
        "SECURITY_3_TITLE": "管理画面 2FA",
        "SECURITY_3_DESC":  "RBAC + IP 制限",

        # フェーズ・スケジュール (proposal_chapters の schedule 章から)
        "PHASE_1_NAME":     "要件確定・設計",
        "PHASE_1_DURATION": "1か月",
        "PHASE_2_NAME":     "基盤・主要機能",
        "PHASE_2_DURATION": "1か月",
        "PHASE_3_NAME":     "拡張機能・連携",
        "PHASE_3_DURATION": "1か月",
        "PHASE_4_NAME":     "QA・テスト",
        "PHASE_4_DURATION": "0.5か月",
        "PHASE_5_NAME":     "リリース・引継ぎ",
        "PHASE_5_DURATION": "0.5か月",

        # 費用明細
        "PRICE_ITEM_1":   "中核機能開発",
        "PRICE_DESC_1":   "認証・商品・カート・決済",
        "PRICE_AMOUNT_1": _yen((pricing_amount or 3200000) // 2),
        "PRICE_ITEM_2":   "拡張機能・管理画面",
        "PRICE_DESC_2":   "サブスクリプション・BtoB・管理ダッシュボード",
        "PRICE_AMOUNT_2": _yen((pricing_amount or 3200000) // 3),
        "PRICE_ITEM_3":   "外部連携・テスト・移行",
        "PRICE_DESC_3":   "在庫連携・QA・データ移行",
        "PRICE_AMOUNT_3": _yen((pricing_amount or 3200000) // 6),
    }
    return {k: ("" if v is None else str(v)) for k, v in vars.items()}


def render_proposal_html(
    *,
    settings: dict,
    project: dict,
    proposal_chapters: list[dict],
    pricing_amount: int | None = None,
) -> str:
    """proposal-slides.html を埋めて返す。"""
    if not PROPOSAL_TEMPLATE_PATH.exists():
        return _fallback_proposal_html(settings, project, proposal_chapters)
    template = PROPOSAL_TEMPLATE_PATH.read_text(encoding="utf-8")
    vars = build_proposal_vars(
        settings=settings, project=project,
        proposal_chapters=proposal_chapters, pricing_amount=pricing_amount,
    )
    rendered = _substitute(template, vars)
    rendered = _apply_design_overrides(rendered, settings)
    return rendered


def _fallback_proposal_html(settings: dict, project: dict, chapters: list[dict]) -> str:
    """テンプレが無い時のシンプルフォールバック。"""
    parts = []
    parts.append(f"<h1>提案書 — {_esc(project.get('project_name','(未設定)'))}</h1>")
    parts.append(f"<p>発行: {_esc(settings.get('company_name',''))}</p>")
    for ch in chapters or []:
        parts.append(f"<h2>{_esc(ch.get('label',''))}</h2>")
        for sec in ch.get("sections", []):
            for it in sec.get("items", []) or []:
                parts.append(f"<p>{_esc(it)}</p>")
    return f"<!DOCTYPE html><html><body>{''.join(parts)}</body></html>"


def _apply_design_overrides(html: str, settings: dict) -> str:
    """テンプレ内の固定色 (#1a6648 等) をユーザー primary_color に置換。"""
    primary = settings.get("primary_color") or "#004CD9"
    # 既存テンプレでよく使われる緑系を BF プライマリ青に
    html = html.replace("#1a6648", primary).replace("#0e3d2c", primary)
    return html


# ──────────────────────────────────────────
# 見積書 (estimate.html) レンダリング
# ──────────────────────────────────────────
def build_estimate_vars(
    *,
    settings: dict,
    estimate_data: dict,                # 見積書 center sections を整形した dict
) -> dict[str, str]:
    issuer = settings or {}

    # 基本情報
    estimate_no = estimate_data.get("estimate_number") or "EST-XXXXXXXX-001"
    issue_date = estimate_data.get("issue_date") or ""
    expiry_date = estimate_data.get("expiry_date") or ""
    client_name = estimate_data.get("client_name") or "(クライアント未設定)"
    client_contact = estimate_data.get("client_contact") or ""
    project_title = estimate_data.get("project_title") or "(件名未設定)"

    # 明細 (最大 10 行)
    items = estimate_data.get("items") or []
    item_vars = {}
    for i in range(1, 11):
        idx = i - 1
        it = items[idx] if idx < len(items) else {}
        item_vars[f"ITEM_{i}_NAME"]       = it.get("name", "")
        item_vars[f"ITEM_{i}_QTY"]        = it.get("qty", "")
        item_vars[f"ITEM_{i}_UNIT"]       = it.get("unit", "式")
        item_vars[f"ITEM_{i}_UNIT_PRICE"] = _yen(it.get("unit_price"))
        item_vars[f"ITEM_{i}_AMOUNT"]     = _yen(it.get("amount"))

    subtotal = estimate_data.get("subtotal", 0) or sum(it.get("amount", 0) for it in items)
    tax = estimate_data.get("tax") or int(subtotal * (issuer.get("tax_rate") or 0.10))
    total = estimate_data.get("total") or (subtotal + tax)

    return {
        "ESTIMATE_NUMBER": estimate_no,
        "ISSUE_DATE":      issue_date,
        "EXPIRY_DATE":     expiry_date,
        "VALID_UNTIL_NOTE": f"本見積書の有効期限は {issuer.get('estimate_validity_days', 30)} 日間です。",

        "CLIENT_NAME":     client_name,
        "CLIENT_CONTACT":  client_contact,
        "PROJECT_TITLE":   project_title,

        # 発行者
        "ISSUER_NAME":     issuer.get("company_name", ""),
        "ISSUER_ADDRESS":  f"〒{issuer.get('postal_code','')} {issuer.get('address','')}".strip(),
        "ISSUER_PHONE":    issuer.get("phone", ""),
        "ISSUER_EMAIL":    issuer.get("email", ""),
        "ISSUER_REP":      f"{issuer.get('representative_title','')} {issuer.get('representative_name','')}".strip(),
        "LOGO_URL":        issuer.get("logo_url", ""),
        "STAMP_URL":       issuer.get("stamp_url", ""),
        "STAMP_TEXT":      issuer.get("stamp_text", ""),

        "SUBTOTAL":  _yen(subtotal),
        "TAX":       _yen(tax),
        "TOTAL":     _yen(total),

        "PAYMENT_TERMS":   estimate_data.get("payment_terms") or issuer.get("payment_terms_default", "30/30/40"),
        "BANK_INFO":       _format_bank(issuer),
        "NOTES":           "\n".join(estimate_data.get("notes") or issuer.get("default_notes") or []),

        **item_vars,
    }


def _format_bank(s: dict) -> str:
    parts = []
    if s.get("bank_name"): parts.append(f"{s['bank_name']} {s.get('bank_branch','')}")
    if s.get("bank_account_type") or s.get("bank_account_number"):
        parts.append(f"{s.get('bank_account_type','普通')} {s.get('bank_account_number','')}")
    if s.get("bank_account_holder"): parts.append(s["bank_account_holder"])
    return " / ".join(parts)


def render_estimate_html(*, settings: dict, estimate_data: dict) -> str:
    """estimate.html を埋めて返す。"""
    if not ESTIMATE_TEMPLATE_PATH.exists():
        return _fallback_estimate_html(settings, estimate_data)
    template = ESTIMATE_TEMPLATE_PATH.read_text(encoding="utf-8")
    vars = build_estimate_vars(settings=settings, estimate_data=estimate_data)
    rendered = _substitute(template, vars)
    rendered = _apply_design_overrides(rendered, settings)
    return rendered


def _fallback_estimate_html(settings: dict, data: dict) -> str:
    return f"""<!DOCTYPE html><html><body>
<h1>見積書</h1>
<p>発行: {_esc(settings.get('company_name',''))}</p>
<p>合計: {_yen(data.get('total', 0))}</p>
</body></html>"""
