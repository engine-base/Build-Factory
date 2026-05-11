"""merge 4 alembic heads into 1

Revision ID: f3a4b5c6d7e8
Revises: d2e3f4a5b6c7, c7d8e9f0a1b2, a4b5c6d7e8f9, e1f2a3b4c5d6
Create Date: 2026-05-11

Background: the repository has accumulated 4 parallel migration chains
(account_settings, user_profile/BF, user_lifecycle, swarm_pools). Each
created an independent root because no enforced single-head policy.
Consolidate so subsequent migrations have one parent.
"""
from typing import Sequence, Union

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = (
    "d2e3f4a5b6c7",
    "c7d8e9f0a1b2",
    "a4b5c6d7e8f9",
    "e1f2a3b4c5d6",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
