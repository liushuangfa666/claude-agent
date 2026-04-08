"""
State 模块 - 统一状态管理

提供：
- Store: 泛型发布-订阅状态存储
- AppState: 全局应用状态定义
- 选择器: 基于选择器的订阅
"""
from __future__ import annotations

from .store import Store
from .app_state import (
    AppState,
    MCPState,
    PluginState,
    TaskState,
    TeamContext,
    ExpandedView,
    create_default_app_state,
)
from .selectors import (
    select_mcp_tools,
    select_enabled_plugins,
    select_task_by_id,
    select_tasks_by_status,
    select_pending_tasks,
    select_blocked_tasks,
    select_team_context,
    select_remote_connection,
)

__all__ = [
    # Store
    "Store",
    # AppState
    "AppState",
    "MCPState",
    "PluginState",
    "TaskState",
    "TeamContext",
    "ExpandedView",
    "create_default_app_state",
    # Selectors
    "select_mcp_tools",
    "select_enabled_plugins",
    "select_task_by_id",
    "select_tasks_by_status",
    "select_pending_tasks",
    "select_blocked_tasks",
    "select_team_context",
    "select_remote_connection",
]
