#!/usr/bin/env python3
"""T-S0-13c: tickets.json 全件 AC 整合検査.

検出する不整合:
  1. テンプレ転用 (verbatim 重複): 同じ AC text が 2 件以上の ticket に出現
  2. title↔AC キーワード乖離: title が DDL/UI/API などのテーマを示すのに
     AC にそのテーマの語が無い
  3. 1 件しか AC が無い、または AC 不在の ticket (EARS は最低 3 件推奨)

出力:
  docs/audit/2026-05-10_v1/ac-coherence-report.md (人間可読)

read-only: tickets.json は変更しない (AC-3 STATE)。
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TICKETS = ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
OUT_MD = ROOT / "docs" / "audit" / "2026-05-10_v1" / "ac-coherence-report.md"

# 既に AC 修正済み (verbatim 重複ではない理由を明示) — AC-4 OPTIONAL
PREVIOUSLY_FIXED = {
    "T-019-01", "T-S0-13", "T-S0-13b", "T-S0-13c",
    "T-001-01", "T-001-01b", "T-001-02", "T-001-04", "T-001-06",
    "T-S0-08", "T-S0-09", "T-S0-09b",
}

# Title テーマ → AC に出現すべき語のセット (どれか 1 つ含めば OK)
TITLE_KEYWORD_RULES: list[tuple[re.Pattern, set[str], str]] = [
    # (title regex, expected_terms_in_AC, theme_label)
    (re.compile(r"DDL|テーブル|migration|スキーマ", re.I),
     {"table", "migration", "schema", "create table", "alter table",
      "column", "constraint", "index", "ddl", "rls"},
     "DDL/schema"),
    (re.compile(r"UI|モック|画面|mockup|frontend|shadcn|Lucide|アイコン", re.I),
     {"render", "click", "display", "shadcn", "lucide", "icon", "css",
      "tailwind", "component", "mock", "frame", "ui", "html", "screen"},
     "UI/frontend"),
    (re.compile(r"API|エンドポイント|endpoint|REST", re.I),
     {"endpoint", "request", "response", "200", "201", "400", "401",
      "403", "404", "500", "post", "get", "put", "patch", "delete",
      "header", "body", "json"},
     "API"),
    (re.compile(r"runner|sandbox|subprocess|claude-agent-sdk|swarm", re.I),
     {"subprocess", "spawn", "session", "claude-agent-sdk", "sandbox",
      "bwrap", "sandbox-exec", "runner", "task tool", "agent"},
     "runner/sandbox"),
    (re.compile(r"認証|Auth|JWT|2FA|TOTP|OAuth", re.I),
     {"jwt", "auth", "token", "login", "session", "2fa", "totp", "oauth",
      "credential", "password", "verify", "claim"},
     "auth"),
    (re.compile(r"RLS|Row Level Security|権限|RBAC|custom_permissions", re.I),
     {"rls", "row level security", "auth.uid", "policy", "permissions",
      "scope", "workspace", "owner", "role"},
     "RLS"),
    (re.compile(r"インベントリ|audit|監査", re.I),
     {"inventory", "audit", "report", "classification", "REUSE",
      "REFACTOR", "ARCHIVE", "NEW"},
     "audit/inventory"),
    (re.compile(r"環境変数|env|Supabase project init", re.I),
     {"env", "environment variable", "SUPABASE_", "config", ".env",
      "fail fast", "missing"},
     "env/config"),
]


def load_tickets() -> list[dict]:
    return json.load(TICKETS.open())["tickets"]


def find_verbatim_duplicates(tickets: list[dict]) -> dict[str, list[str]]:
    """同じ AC text が 2 件以上の ticket に出現した場合を {text: [ticket_ids]}"""
    text_to_tids: dict[str, list[str]] = defaultdict(list)
    for t in tickets:
        for ac in t.get("acceptance_criteria") or []:
            text = (ac.get("text") or "").strip()
            if not text:
                continue
            text_to_tids[text].append(t["id"])
    return {txt: tids for txt, tids in text_to_tids.items() if len(tids) > 1}


def title_keyword_mismatch(t: dict) -> tuple[bool, str | None]:
    """title が示すテーマと AC キーワードが一致しているかチェック。

    Returns:
        (mismatched: bool, theme_label: str | None)
    """
    title = (t.get("title") or "").lower()
    ac_blob = " ".join(
        (ac.get("text") or "").lower()
        for ac in (t.get("acceptance_criteria") or [])
    )
    for pat, expected, label in TITLE_KEYWORD_RULES:
        if pat.search(title):
            if any(term.lower() in ac_blob for term in expected):
                return False, label  # OK
            return True, label  # mismatch
    return False, None  # title が rule に該当しない → 判定保留


def insufficient_ac(t: dict) -> bool:
    """AC が 3 件未満なら不足 (EARS は ≥ 3 推奨)."""
    acs = t.get("acceptance_criteria") or []
    return len(acs) < 3


def main() -> int:
    tickets = load_tickets()
    dups = find_verbatim_duplicates(tickets)
    mismatch_results = []
    insufficient = []
    review_needed = []
    for t in tickets:
        tid = t["id"]
        mismatched, theme = title_keyword_mismatch(t)
        if mismatched:
            mismatch_results.append((tid, theme, t))
        if insufficient_ac(t):
            if not (t.get("acceptance_criteria")):
                review_needed.append((tid, "no AC at all"))
            else:
                insufficient.append((tid, len(t.get("acceptance_criteria") or [])))

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    with OUT_MD.open("w", encoding="utf-8") as f:
        f.write("# T-S0-13c: tickets.json AC 整合検査結果\n\n")
        f.write(f"- Total tickets: {len(tickets)}\n")
        f.write(f"- 既修正 (PREVIOUSLY_FIXED): {len(PREVIOUSLY_FIXED)}\n")
        f.write(f"- Verbatim 重複 AC text: {len(dups)} 件\n")
        f.write(f"- title↔AC キーワード乖離: {len(mismatch_results)} 件\n")
        f.write(f"- AC < 3 件 (insufficient): {len(insufficient)} 件\n")
        f.write(f"- AC 不在 / review_needed: {len(review_needed)} 件\n\n")

        f.write("## 1. Verbatim 重複 AC text (テンプレ転用シグナル)\n\n")
        if not dups:
            f.write("(なし)\n\n")
        else:
            for text, tids in sorted(dups.items(), key=lambda x: -len(x[1])):
                marker = ""
                if all(tid in PREVIOUSLY_FIXED for tid in tids):
                    marker = " `[previously_fixed]`"
                f.write(f"- **{len(tids)} tickets**{marker}: {tids}\n")
                f.write(f"  - 文言: \"{text[:200]}{'...' if len(text)>200 else ''}\"\n\n")

        f.write("\n## 2. title↔AC キーワード乖離\n\n")
        if not mismatch_results:
            f.write("(なし)\n\n")
        else:
            for tid, theme, t in mismatch_results:
                marker = " `[previously_fixed]`" if tid in PREVIOUSLY_FIXED else ""
                f.write(f"### {tid}{marker} (theme: {theme})\n")
                f.write(f"- title: \"{t.get('title','')}\"\n")
                f.write(f"- AC excerpt:\n")
                for ac in (t.get("acceptance_criteria") or [])[:2]:
                    f.write(f"  - [{ac.get('type','?')}] {(ac.get('text') or '')[:150]}\n")
                f.write("\n")

        f.write("\n## 3. AC < 3 件 (insufficient — EARS は最低 3 件推奨)\n\n")
        if not insufficient:
            f.write("(なし)\n\n")
        else:
            for tid, n in insufficient:
                marker = " `[previously_fixed]`" if tid in PREVIOUSLY_FIXED else ""
                f.write(f"- {tid}{marker}: {n} 件\n")

        f.write("\n## 4. AC 不在 / review_needed\n\n")
        if not review_needed:
            f.write("(なし)\n\n")
        else:
            for tid, reason in review_needed:
                f.write(f"- {tid}: {reason}\n")

    print(f"Total tickets:                  {len(tickets)}")
    print(f"Verbatim 重複 AC text:          {len(dups)}")
    print(f"title↔AC キーワード乖離:         {len(mismatch_results)}")
    print(f"AC < 3 件 (insufficient):       {len(insufficient)}")
    print(f"AC 不在 / review_needed:        {len(review_needed)}")
    print(f"\nWritten: {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
