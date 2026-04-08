"""
状态选择器 - 从 AppState 中提取特定数据

提供类型安全的 selectors 用于订阅状态变更。
"""
from __future__ import annotations

from typing import Optional

from .app_state import AppState, MCPState, PluginState, TaskState, TeamContext


def select_mcp_tools(state: AppState) -> tuple:
    """选择 MCP 工具"""
    return state.mcp.tools


def select_enabled_plugins(state: AppState) -> tuple:
    """选择启用的插件"""
    return state.plugins.enabled


def select_task_by_id(state: AppState, task_id: str) -> Optional[TaskState]:
    """选择指定任务"""
    return state.tasks.get(task_id)


def select_tasks_by_status(state: AppState, status: str) -> list[TaskState]:
    """选择指定状态的任务"""
    return [t for t in state.tasks.values() if t.status == status]


def select_pending_tasks(state: AppState) -> list[TaskState]:
    """选择待处理任务"""
    return select_tasks_by_status(state, "pending")


def select_blocked_tasks(state: AppState) -> list[TaskState]:
    """选择被阻塞的任务"""
    return [t for t in state.tasks.values() if t.blocked_by]


def select_team_context(state: AppState) -> Optional[TeamContext]:
    """选择团队上下文"""
    return state.team_context


def select_remote_connection(state: AppState) -> str:
    """选择远程连接状态"""
    return state.remote_connection_status


def select_expanded_view(state: AppState) -> str:
    """选择展开视图状态"""
    return state.expanded_view.value


def select_thinking_enabled(state: AppState) -> bool:
    """选择思考是否启用"""
    return state.thinking_enabled


def select_session_id(state: AppState) -> str:
    """选择会话 ID"""
    return state.session_id
