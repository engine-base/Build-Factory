"""
Obsidian Vault のディレクトリ構造初期化。

階層:
    data/obsidian-vault/
    ├── accounts/
    │   └── {account_slug}/                # 会社レベル (例: engine-base)
    │       ├── shared/                    # 全メンバー読み書き可
    │       │   ├── policies/              # 社内ルール
    │       │   ├── playbook/              # 業務プレイブック
    │       │   ├── client-history/        # 顧客履歴
    │       │   └── decisions/             # 意思決定ログ
    │       ├── members/                   # 個人ナレッジ
    │       │   └── {user_slug}/
    │       │       ├── private/           # 本人のみ
    │       │       └── shared-with-team/  # チーム公開
    │       └── ai-personas/               # 社員 AI 専用
    │           ├── nana-pm/               # PM秘書ナナ
    │           ├── ken-architect/         # アーキテクトケン
    │           ├── haru-engineer/         # エンジニアハル
    │           ├── rin-reviewer/          # レビュアーリン
    │           ├── saki-qa/               # QAサキ
    │           ├── taku-devops/           # DevOpsタク
    │           └── mio-docs/              # Docsミオ
    └── workspaces/
        └── {workspace_slug}/              # ワークスペース個別 (案件単位)
            ├── shared/
            ├── ai-personas/               # この案件専用 AI 知識
            └── design-system/             # この案件のデザインシステム

scope_path → visibility のマッピングルール (sync 側で適用):
    accounts/*/shared/**            → account_shared
    accounts/*/members/*/private/** → private (owner_user_id = user_slug)
    accounts/*/members/*/shared-**  → member_shared
    accounts/*/ai-personas/*/**     → ai_only (assigned_employee_id = persona_slug の AI)
    workspaces/*/shared/**          → account_shared (workspace_id 指定)
    workspaces/*/ai-personas/*/**   → ai_only (workspace_id + persona)
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
VAULT_ROOT = ROOT / "data" / "obsidian-vault"
DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
)

# 7 dev AI personas のディレクトリ slug
AI_PERSONA_SLUGS = [
    ("nana-pm", "ナナ・PM秘書"),
    ("ken-architect", "ケン・アーキテクト"),
    ("haru-engineer", "ハル・エンジニア"),
    ("rin-reviewer", "リン・レビュアー"),
    ("saki-qa", "サキ・QA"),
    ("taku-devops", "タク・DevOps"),
    ("mio-docs", "ミオ・Docs"),
]


def slugify(s: str) -> str:
    return (
        s.replace(" ", "-")
        .replace("/", "-")
        .replace(".", "-")
        .lower()
        .strip("-")
    )


def write_readme(path: Path, body: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    readme = path / "README.md"
    if not readme.exists():
        readme.write_text(body, encoding="utf-8")


async def main():
    async with await psycopg.AsyncConnection.connect(DSN, row_factory=dict_row) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id, name FROM accounts WHERE is_active = TRUE ORDER BY id"
            )
            accounts = await cur.fetchall()

            await cur.execute(
                "SELECT id, name, account_id FROM workspaces ORDER BY id"
            )
            workspaces = await cur.fetchall()

            await cur.execute(
                "SELECT id, employee_name, display_name, category, account_id FROM ai_employee_config ORDER BY id"
            )
            personas = await cur.fetchall()

    print(f"[INFO] Vault root: {VAULT_ROOT}")
    VAULT_ROOT.mkdir(parents=True, exist_ok=True)

    write_readme(
        VAULT_ROOT,
        "# Build-Factory Obsidian Vault\n\n"
        "AI 社員 + 人間メンバー共有のナレッジハブ。\n\n"
        "## 階層\n"
        "- `accounts/{account}/shared/` — 会社共有\n"
        "- `accounts/{account}/members/{user}/private/` — 個人のみ\n"
        "- `accounts/{account}/members/{user}/shared-with-team/` — チーム共有\n"
        "- `accounts/{account}/ai-personas/{persona}/` — AI 専用知識\n"
        "- `workspaces/{workspace}/shared/` — 案件共有\n"
        "- `workspaces/{workspace}/ai-personas/{persona}/` — 案件×AI\n"
        "\n"
        "ファイルを変更すると自動で Supabase Postgres (knowledge_base) と同期されます。\n",
    )

    # accounts
    for acc in accounts:
        acc_slug = slugify(acc["name"])
        acc_root = VAULT_ROOT / "accounts" / acc_slug
        write_readme(
            acc_root,
            f"# {acc['name']}\n\n会社レベルのナレッジルート (account_id={acc['id']})\n",
        )
        # shared
        for sub in ("policies", "playbook", "client-history", "decisions"):
            write_readme(
                acc_root / "shared" / sub,
                f"# {sub}\n\nvisibility: account_shared\n",
            )
        # members (初期は空ディレクトリのみ・人間ごとに後から作る)
        (acc_root / "members").mkdir(parents=True, exist_ok=True)
        write_readme(
            acc_root / "members",
            "# Members\n\nメンバー個人ナレッジルート。`{user_slug}/private/` は本人のみ、`{user_slug}/shared-with-team/` はチーム共有。\n",
        )
        # ai-personas
        for slug, label in AI_PERSONA_SLUGS:
            persona_dir = acc_root / "ai-personas" / slug
            write_readme(
                persona_dir,
                f"# {label}\n\nvisibility: ai_only\n\n"
                f"このディレクトリは {label} 専用のナレッジ領域です。\n"
                f"- 人間からの検索結果には表示されません\n"
                f"- {label} の AI 応答コンテキストとして使用されます\n",
            )
            for sub in ("rules", "examples", "patterns", "incidents"):
                (persona_dir / sub).mkdir(exist_ok=True)

        # masato 個人ディレクトリだけ作っておく（既存メンバー）
        masato_dir = acc_root / "members" / "masato"
        write_readme(
            masato_dir / "private",
            "# masato — Private\n\nvisibility: private (owner=masato)\n",
        )
        write_readme(
            masato_dir / "shared-with-team",
            "# masato — Shared with team\n\nvisibility: member_shared\n",
        )

    # workspaces
    for ws in workspaces:
        ws_slug = slugify(ws["name"])
        ws_root = VAULT_ROOT / "workspaces" / ws_slug
        write_readme(
            ws_root,
            f"# {ws['name']}\n\n案件 workspace_id={ws['id']} (account_id={ws['account_id']})\n",
        )
        for sub in ("decisions", "design", "qa-log", "release-notes"):
            write_readme(
                ws_root / "shared" / sub,
                f"# {sub}\n\nvisibility: account_shared / workspace_id={ws['id']}\n",
            )
        for slug, label in AI_PERSONA_SLUGS:
            write_readme(
                ws_root / "ai-personas" / slug,
                f"# {label} ({ws['name']} 専用)\n\nvisibility: ai_only\n",
            )
        write_readme(
            ws_root / "design-system",
            "# Design System\n\nこの案件で使用するデザインシステム (DESIGN.md など)\n",
        )

    print("[OK] Obsidian vault 初期化完了")
    print(f"   accounts:   {len(accounts)}")
    print(f"   workspaces: {len(workspaces)}")
    print(f"   personas/account: {len(AI_PERSONA_SLUGS)}")


if __name__ == "__main__":
    asyncio.run(main())
