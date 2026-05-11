"""workspace domain — public barrel (T-001-01b AC-2).

責務: workspace lifecycle / clone opt-in / bf profile.
"""
from __future__ import annotations

from services.workspace_service import (
    list_workspaces_for_user,
    get_workspace,
    create_workspace,
    update_workspace,
    archive_workspace,
)
from services.clone_opt_in import (
    set_opt_in,
    check_opt_in,
    log_interaction,
    revoke_opt_in_and_delete_data,
)

__all__ = [
    "list_workspaces_for_user",
    "get_workspace",
    "create_workspace",
    "update_workspace",
    "archive_workspace",
    "set_opt_in",
    "check_opt_in",
    "log_interaction",
    "revoke_opt_in_and_delete_data",
]
