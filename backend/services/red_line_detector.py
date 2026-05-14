"""T-012-02: red_line pattern detection middleware (approval.py 拡張用).

F-012 (赤線リスト + 自動停止) の中核 detector. 既存 `routers/approval.py` の前段で
呼ばれ、提案された action / content / cmd を pattern match して

  - block (severity='block')  : 承認 reject、承認キューにも入らない
  - warn  (severity='warn')   : 承認キューに入るが warn flag 付与
  - log   (severity='log')    : 通過、audit log のみ

の 3 種類の action を返す.

CLAUDE.md §5.4 セキュリティ / レッドライン (即セッション kill) の literal text:

  - 本番 DB に DROP / TRUNCATE / DELETE *     = 即セッション kill
  - .env / 鍵ファイルのコミット                 = git pre-commit + GitHub secret scanning
  - --no-verify / --force push (公開後)        = 明示承認時のみ
  - AGPL ライセンス依存追加                     = 自動レビューキュー → 不採用が原則

F-012 default_categories:
  api_key_leak / db_destructive / force_push / infinite_loop / deploy_decision

各 pattern は **個別に detect** され、複数 hit したら全件 violations に積む.
1 つの汎用 regex でまとめて "動いた" と称するのは禁止 (drift guard).

REUSE invariant: `routers/approval.py` の既存 CRUD endpoint は無改変.
本 module は detect 関数のみ提供し、approval.py の create_approval から
optional に呼ばれる pre-flight hook.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

PHASE = "1"

# ──────────────────────────────────────────────────────────────────────
# Public constants
# ──────────────────────────────────────────────────────────────────────

SEVERITY_BLOCK = "block"
SEVERITY_WARN = "warn"
SEVERITY_LOG = "log"

ACTION_BLOCK = "block"
ACTION_WARN = "warn"
ACTION_LOG = "log"

# F-012 default_categories (features.json 1:1)
CATEGORY_API_KEY_LEAK = "api_key_leak"
CATEGORY_DB_DESTRUCTIVE = "db_destructive"
CATEGORY_FORCE_PUSH = "force_push"
CATEGORY_INFINITE_LOOP = "infinite_loop"
CATEGORY_DEPLOY_DECISION = "deploy_decision"

DEFAULT_CATEGORIES = (
    CATEGORY_API_KEY_LEAK,
    CATEGORY_DB_DESTRUCTIVE,
    CATEGORY_FORCE_PUSH,
    CATEGORY_INFINITE_LOOP,
    CATEGORY_DEPLOY_DECISION,
)


class RedLineDetectorError(ValueError):
    """invalid input (空 / 非 str / 巨大) を呼び出し前に弾く."""


@dataclass(frozen=True)
class RedLineRule:
    """個別 red-line rule.

    rule_key は features.json default_categories と整合する識別子.
    pattern_type:
      "sql"     — SQL text (大文字小文字無視で WORD-BOUNDARY 必須)
      "git"     — git command line (--no-verify / --force / push -f 等)
      "fs"      — filesystem commit (.env / credentials.json 等)
      "dep"     — dependency manifest (AGPL license)
      "loop"    — infinite loop heuristic
      "deploy"  — deploy decision flag
    severity: block | warn | log
    """

    rule_key: str
    category: str
    pattern: str
    pattern_type: str
    severity: str
    description: str

    def matches(self, target: str) -> bool:
        if not isinstance(target, str):
            return False
        try:
            return re.search(self.pattern, target, re.IGNORECASE) is not None
        except re.error:
            return False


# ──────────────────────────────────────────────────────────────────────
# CLAUDE.md §5.4 + F-012 rules — 個別 (1 pattern == 1 rule)
# ──────────────────────────────────────────────────────────────────────
#
# 各 rule は **個別 regex**. WORD-BOUNDARY (\b) と適切な anchor で
# `DROP TABLE IF EXISTS` のような fixture false-positive を回避する.

# db_destructive — DROP / TRUNCATE / DELETE * を 3 件に分離.
RULE_SQL_DROP = RedLineRule(
    rule_key="no_drop_table",
    category=CATEGORY_DB_DESTRUCTIVE,
    # DROP (TABLE|DATABASE|SCHEMA) WITHOUT 'IF EXISTS' guard
    # negative lookahead で `DROP TABLE IF EXISTS` を除外 (drift guard)
    pattern=r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA)(?!\s+IF\s+EXISTS)\b",
    pattern_type="sql",
    severity=SEVERITY_BLOCK,
    description="本番 DB への DROP は即セッション kill (CLAUDE.md §5.4)",
)

RULE_SQL_TRUNCATE = RedLineRule(
    rule_key="no_truncate",
    category=CATEGORY_DB_DESTRUCTIVE,
    pattern=r"\bTRUNCATE\s+(?:TABLE\s+)?[\w\.\"`]+",
    pattern_type="sql",
    severity=SEVERITY_BLOCK,
    description="TRUNCATE は即セッション kill (CLAUDE.md §5.4)",
)

RULE_SQL_DELETE_STAR = RedLineRule(
    rule_key="no_delete_star",
    category=CATEGORY_DB_DESTRUCTIVE,
    # DELETE FROM <table> ... WITHOUT WHERE  →  "DELETE *" 相当
    pattern=r"\bDELETE\s+FROM\s+[\w\.\"`]+\s*(?:;|$|--)(?!.*\bWHERE\b)",
    pattern_type="sql",
    severity=SEVERITY_BLOCK,
    description="WHERE 無し DELETE は DELETE * 相当 / 即セッション kill",
)

# force_push — git operations
RULE_GIT_FORCE_PUSH = RedLineRule(
    rule_key="no_force_push",
    category=CATEGORY_FORCE_PUSH,
    pattern=r"git\s+push\s+(?:[^\n]*\s)?(?:--force\b|-f\b|--force-with-lease\b)",
    pattern_type="git",
    severity=SEVERITY_BLOCK,
    description="--force push は明示承認時のみ (CLAUDE.md §5.4)",
)

RULE_GIT_NO_VERIFY = RedLineRule(
    rule_key="no_skip_hooks",
    category=CATEGORY_FORCE_PUSH,
    pattern=r"git\s+(?:commit|push|merge|rebase)\s+(?:[^\n]*\s)?--no-verify\b",
    pattern_type="git",
    severity=SEVERITY_BLOCK,
    description="--no-verify は明示承認時のみ (CLAUDE.md §5.4)",
)

# api_key_leak — .env / credentials commit
RULE_FS_DOTENV_COMMIT = RedLineRule(
    rule_key="no_env_commit",
    category=CATEGORY_API_KEY_LEAK,
    # `git add .env` / `git commit ... .env` / staged path `.env\n` (NOT .env.example)
    pattern=r"(?:git\s+(?:add|commit)\b[^\n]*\s|\s|^)\.env(?!\.example|\.sample|\.template)\b",
    pattern_type="fs",
    severity=SEVERITY_BLOCK,
    description=".env コミットは GitHub secret scanning (CLAUDE.md §5.4)",
)

RULE_FS_CREDENTIALS_COMMIT = RedLineRule(
    rule_key="no_credentials_commit",
    category=CATEGORY_API_KEY_LEAK,
    pattern=r"(?:git\s+(?:add|commit)\b[^\n]*\s|\s|^)credentials\.json\b",
    pattern_type="fs",
    severity=SEVERITY_BLOCK,
    description="credentials.json コミットは GitHub secret scanning",
)

# api_key_leak — secret literals
RULE_FS_API_KEY_LITERAL = RedLineRule(
    rule_key="no_api_key_literal",
    category=CATEGORY_API_KEY_LEAK,
    # Anthropic / OpenAI / GitHub PAT prefixes
    pattern=r"\b(?:sk-ant-[A-Za-z0-9_\-]{30,}|sk-[A-Za-z0-9]{40,}|gh[pousr]_[A-Za-z0-9]{30,})\b",
    pattern_type="fs",
    severity=SEVERITY_BLOCK,
    description="API key literal の混入 (CLAUDE.md §5.4)",
)

# deploy_decision — AGPL license
RULE_DEP_AGPL = RedLineRule(
    rule_key="no_agpl_dependency",
    category=CATEGORY_DEPLOY_DECISION,
    # "license": "AGPL-3.0" / "GNU Affero" / "AGPLv3" 表記
    pattern=r"\b(?:AGPL[-\s]?(?:v?3(?:\.0)?(?:[-\s]?or[-\s]?later)?)?|GNU\s+Affero(?:\s+General\s+Public\s+License)?)\b",
    pattern_type="dep",
    severity=SEVERITY_BLOCK,
    description="AGPL 依存は SaaS 提供時に問題 (CLAUDE.md §5.4)",
)

# infinite_loop — while True without break heuristic
RULE_LOOP_WHILE_TRUE = RedLineRule(
    rule_key="no_infinite_loop",
    category=CATEGORY_INFINITE_LOOP,
    # `while True:` / `while 1:` / `for(;;)` without 30 chars proceed `break` token
    pattern=r"(?:while\s+(?:True|1)\s*:|for\s*\(\s*;\s*;\s*\))",
    pattern_type="loop",
    severity=SEVERITY_WARN,
    description="while True / for(;;) は明示的な break/return を併設する (F-012)",
)

# deploy_decision — prod deploy without approval
RULE_DEPLOY_PROD = RedLineRule(
    rule_key="deploy_decision_required",
    category=CATEGORY_DEPLOY_DECISION,
    pattern=r"\b(?:deploy|release|publish)\s+(?:to\s+)?(?:production|prod|live)\b",
    pattern_type="deploy",
    severity=SEVERITY_WARN,
    description="prod deploy は承認必須 (F-012 deploy_decision)",
)

DEFAULT_RULES: tuple[RedLineRule, ...] = (
    RULE_SQL_DROP,
    RULE_SQL_TRUNCATE,
    RULE_SQL_DELETE_STAR,
    RULE_GIT_FORCE_PUSH,
    RULE_GIT_NO_VERIFY,
    RULE_FS_DOTENV_COMMIT,
    RULE_FS_CREDENTIALS_COMMIT,
    RULE_FS_API_KEY_LITERAL,
    RULE_DEP_AGPL,
    RULE_LOOP_WHILE_TRUE,
    RULE_DEPLOY_PROD,
)


# ──────────────────────────────────────────────────────────────────────
# Severity → Action mapping
# ──────────────────────────────────────────────────────────────────────

_SEVERITY_TO_ACTION = {
    SEVERITY_BLOCK: ACTION_BLOCK,
    SEVERITY_WARN: ACTION_WARN,
    SEVERITY_LOG: ACTION_LOG,
}


def severity_to_action(severity: str) -> str:
    """severity → action を 1:1 で対応付ける.

    block → block / warn → warn / log → log.
    未知値は ValueError.
    """
    if severity not in _SEVERITY_TO_ACTION:
        raise RedLineDetectorError(f"unknown severity: {severity!r}")
    return _SEVERITY_TO_ACTION[severity]


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────

MAX_TARGET_LEN = 200_000  # 200KB 超は拒否 (DoS guard)


def _validate_target(target: str) -> str:
    if target is None:
        raise RedLineDetectorError("target is None")
    if not isinstance(target, str):
        raise RedLineDetectorError(f"target must be str, got {type(target).__name__}")
    if len(target) == 0:
        raise RedLineDetectorError("target is empty")
    if len(target) > MAX_TARGET_LEN:
        raise RedLineDetectorError(
            f"target too long: {len(target)} bytes > {MAX_TARGET_LEN}"
        )
    return target


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def detect_patterns(
    target: str,
    rules: Iterable[RedLineRule] | None = None,
) -> list[dict[str, str]]:
    """target を全 rule に対して match check し、hit 集合を deterministic 順で返す.

    Returns:
      list of {
        rule_key: str,
        category: str,
        severity: str,
        action: str,
        pattern_type: str,
        description: str,
      }
      hit が無ければ空 list.

    Raises:
      RedLineDetectorError: invalid input.
    """
    _validate_target(target)
    rules_tuple = tuple(rules) if rules is not None else DEFAULT_RULES

    violations: list[dict[str, str]] = []
    for rule in rules_tuple:
        if rule.matches(target):
            violations.append({
                "rule_key": rule.rule_key,
                "category": rule.category,
                "severity": rule.severity,
                "action": severity_to_action(rule.severity),
                "pattern_type": rule.pattern_type,
                "description": rule.description,
            })

    # deterministic order: category asc, rule_key asc
    violations.sort(key=lambda v: (v["category"], v["rule_key"]))
    return violations


def evaluate_approval(
    title: str,
    content: str,
    action_type: str | None = None,
) -> dict[str, object]:
    """approval_queue 投入予定のレコードを pre-flight pattern check.

    Returns:
      {
        "allowed": bool,           # block 系 violation が 0 件か
        "action": "block"|"warn"|"log"|"pass",
        "violations": list[...],   # detect_patterns の結果
        "categories": list[str],   # hit した unique category
      }

    Raises:
      RedLineDetectorError: invalid input.
    """
    # title と content を結合して judge (action_type は metadata、pattern なし)
    target = _build_target(title, content, action_type)
    violations = detect_patterns(target)

    has_block = any(v["severity"] == SEVERITY_BLOCK for v in violations)
    has_warn = any(v["severity"] == SEVERITY_WARN for v in violations)

    if has_block:
        action = ACTION_BLOCK
    elif has_warn:
        action = ACTION_WARN
    elif violations:
        action = ACTION_LOG
    else:
        action = "pass"

    categories = sorted({v["category"] for v in violations})
    return {
        "allowed": not has_block,
        "action": action,
        "violations": violations,
        "categories": categories,
        "phase": PHASE,
    }


def _build_target(
    title: str,
    content: str,
    action_type: str | None,
) -> str:
    """validate + concat. invalid なら raise."""
    if not isinstance(title, str):
        raise RedLineDetectorError(
            f"title must be str, got {type(title).__name__}"
        )
    if not isinstance(content, str):
        raise RedLineDetectorError(
            f"content must be str, got {type(content).__name__}"
        )
    if action_type is not None and not isinstance(action_type, str):
        raise RedLineDetectorError(
            f"action_type must be str|None, got {type(action_type).__name__}"
        )
    if len(title) == 0 and len(content) == 0:
        raise RedLineDetectorError("title and content are both empty")
    parts = [title, content]
    if action_type:
        parts.append(action_type)
    target = "\n".join(parts)
    if len(target) > MAX_TARGET_LEN:
        raise RedLineDetectorError(
            f"combined target too long: {len(target)} > {MAX_TARGET_LEN}"
        )
    return target


__all__ = [
    "PHASE",
    "SEVERITY_BLOCK",
    "SEVERITY_WARN",
    "SEVERITY_LOG",
    "ACTION_BLOCK",
    "ACTION_WARN",
    "ACTION_LOG",
    "CATEGORY_API_KEY_LEAK",
    "CATEGORY_DB_DESTRUCTIVE",
    "CATEGORY_FORCE_PUSH",
    "CATEGORY_INFINITE_LOOP",
    "CATEGORY_DEPLOY_DECISION",
    "DEFAULT_CATEGORIES",
    "DEFAULT_RULES",
    "RedLineRule",
    "RedLineDetectorError",
    "MAX_TARGET_LEN",
    "severity_to_action",
    "detect_patterns",
    "evaluate_approval",
    # Rule instances (test 用 individual access)
    "RULE_SQL_DROP",
    "RULE_SQL_TRUNCATE",
    "RULE_SQL_DELETE_STAR",
    "RULE_GIT_FORCE_PUSH",
    "RULE_GIT_NO_VERIFY",
    "RULE_FS_DOTENV_COMMIT",
    "RULE_FS_CREDENTIALS_COMMIT",
    "RULE_FS_API_KEY_LITERAL",
    "RULE_DEP_AGPL",
    "RULE_LOOP_WHILE_TRUE",
    "RULE_DEPLOY_PROD",
]
