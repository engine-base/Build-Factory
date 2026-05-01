"""
seed_default_account.py — Build-Factory の初期 Account / Workspace を投入する

実行:
  cd backend && PYTHONPATH=. python scripts/seed_default_account.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def seed():
    from services import account_service, workspace_service

    # 既存 Account 確認
    existing = await account_service.list_accounts("masato")
    if existing:
        print(f"[seed] account 既存: {[a['name'] for a in existing]}")
        account_id = existing[0]["id"]
    else:
        acc = await account_service.create_account(
            name="ENGINE BASE",
            type="company",
            plan="business",
            owner_user_id="masato",
            billing_email="info@engine-base.com",
            metadata={"founder": "masato", "established": "2026"},
        )
        account_id = acc["id"]
        print(f"[seed] account 作成: ENGINE BASE (id={account_id})")

    # サンプル Workspace
    ws_list = await workspace_service.list_workspaces_by_account(account_id)
    if ws_list:
        print(f"[seed] workspace 既存: {len(ws_list)} 件")
        for w in ws_list:
            print(f"  - {w['name']} (id={w['id']})")
        return

    sample = await workspace_service.create_workspace(
        account_id=account_id,
        name="Build-Factory 初期 Workspace",
        description="初期テスト用・自社開発フローを試運転する場所",
        project_meta={"type": "internal", "stack_hint": "Next.js + FastAPI"},
        creator_user_id="masato",
    )
    print(f"[seed] workspace 作成: {sample['name']} (id={sample['id']})")


if __name__ == "__main__":
    asyncio.run(seed())
