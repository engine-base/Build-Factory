"""
skill_detector.py — ユーザー入力からどの SKILL.md をフルロードすべきか判定する。

Claude/ChatGPT 方式: 該当時はフル全文ロード、非該当時はゼロロード。
要約は使わない。
"""

from __future__ import annotations

import re
from pathlib import Path

# ──────────────────────────────────────────────────────
# スキル → トリガーキーワード
# ──────────────────────────────────────────────────────

SKILL_TRIGGERS: dict[str, list[str]] = {
    # 組織変更（人事 hr_05 専用）
    "staff-management": [
        "採用", "雇い", "雇う", "メンバー追加", "新しい社員",
        "退職", "解任", "アサイン解除", "外して",
        "編集して", "個性変更", "口調変更", "担当変更",
        "組織図", "体制確認", "誰がいる",
    ],

    # 営業
    "01_sales": ["営業メール", "フォローメール", "案件", "パイプライン", "商談"],
    "sales-email": ["営業メール", "フォローメール", "コールドメール"],
    "pipeline-management": ["パイプライン", "案件管理", "受注予測"],
    "proposal": ["提案書", "提案資料"],

    # 経理
    "invoice-create": ["請求書", "見積書", "インボイス"],
    "expense-management": ["経費", "支出", "領収書"],
    "cashflow-forecast": ["キャッシュフロー", "資金繰り"],

    # マーケ
    "sns-management": ["SNS", "ツイート", "Instagram", "TikTok", "投稿文"],
    "ad-management": ["広告", "Meta広告", "Google広告"],
    "seo-design": ["SEO", "検索エンジン"],
    "content-strategy": ["コンテンツ戦略", "ブログ計画"],

    # CS
    "support-response": ["サポート対応", "問い合わせ返信", "クレーム対応"],

    # 共通
    "knowledge-base": ["ナレッジ整理", "知識整理"],
    "browser-action": ["ブラウザで", "Notion で", "ブラウザ操作"],

    # スキル開発（メタ）
    "skill-creator": [
        "スキル作成", "スキル作って", "スキル作りたい", "新しいスキル",
        "スキル改善", "スキル直して", "スキル評価", "スキル最適化",
        "skill creator", "skill-creator", "SKILL.md", "skill 作って",
        "description 最適化", "skill description", "skill のテスト",
    ],
}

# 直前の応答にスキル使用形跡があれば継続
SKILL_CONTINUATION_HINTS: dict[str, list[str]] = {
    "staff-management": [
        "リーダー", "メンバー", "親リーダー", "特化分野",
        "採用確認", "退職処理", "ナレッジ引継",
    ],
}


def detect_skill(
    message: str,
    history: list[dict] | None = None,
    employee_primary_skill: str | None = None,
) -> str | None:
    """
    ユーザー入力から発火すべき SKILL.md 名を返す。
    該当なしなら None。

    判定優先順:
      1. 明示キーワード（強い）
      2. 直前ターンが特定スキル中なら継続
      3. 社員 primary_skill との整合性
    """
    msg = (message or "").strip()
    if not msg:
        return None

    # 1. キーワード判定
    for skill, kws in SKILL_TRIGGERS.items():
        for kw in kws:
            if kw in msg:
                return skill

    # 2. 直前ターン継続
    if history:
        # 直近 assistant 発言を見る
        for h in reversed(history[-4:]):
            if h.get("role") != "assistant":
                continue
            content = (h.get("content") or h.get("message") or "")
            for skill, hints in SKILL_CONTINUATION_HINTS.items():
                hit = sum(1 for hint in hints if hint in content)
                if hit >= 2:   # 2つ以上ヒットなら継続
                    return skill
            break

    return None


def load_skill_md(skill_name: str) -> str | None:
    """SKILL.md のフル全文をロード（要約しない・Claude 方式）。"""
    if not skill_name:
        return None
    candidates = [
        Path(__file__).resolve().parents[2] / "data" / "skills" / skill_name / "SKILL.md",
        Path.home() / ".claude" / "skills" / skill_name / "SKILL.md",
    ]
    for p in candidates:
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except Exception:
                continue
    return None
