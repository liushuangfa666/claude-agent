"""
AppState 定义 - 全局应用状态

包含所有应用状态的不可变数据类定义。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ExpandedView(Enum):
    """展开视图枚举"""
    NONE = "none"
    TASKS = "tasks"
    TEAMMATES = "teammates"


@dataclass(frozen=True)
class MCPState:
    """MCP 状态"""
    clients: tuple = field(default_factory=tuple)
    tools: tuple = field(default_factory=tuple)
    resources: dict = field(default_factory=dict)
    commands: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class PluginState:
    """插件状态"""
    enabled: tuple = field(default_factory=tuple)
    disabled: tuple = field(default_factory=tuple)
    commands: tuple = field(default_factory=tuple)
    errors: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class TaskState:
    """任务状态"""
    id: str
    type: str
    status: str  # pending | running | completed | failed | killed
    description: str
    blocked_by: tuple = field(default_factory=tuple)
    blocks: tuple = field(default_factory=tuple)
    start_time: int = 0
    end_time: Optional[int] = None


@dataclass(frozen=True)
class TeamContext:
    """团队上下文"""
    team_name: str
    teammates: dict
    is_leader: bool
    self_agent_id: Optional[str] = None


@dataclass(frozen=True)
class AppState:
    """
    全局应用状态

    所有应用级状态都存储在这里。
    使用 frozen=True 确保不可变。
    """
    # 会话与设置
    session_id: str = ""
    settings: dict = field(default_factory=dict)
    main_loop_model: str = ""

    # 视图状态
    expanded_view: ExpandedView = ExpandedView.NONE
    coordinator_task_index: int = 0
    footer_selection: Optional[str] = None

    # MCP
    mcp: MCPState = field(default_factory=MCPState)

    # 插件
    plugins: PluginState = field(default_factory=PluginState)

    # 任务
    tasks: dict = field(default_factory=dict)

    # Todo
    todos: dict = field(default_factory=dict)

    # 团队上下文
    team_context: Optional[TeamContext] = None

    # 推理状态
    speculation: dict = field(default_factory=dict)
    thinking_enabled: bool = True

    # 远程连接
    remote_connection_status: str = "disconnected"

    # REPL Bridge
    repl_bridge_enabled: bool = False
    repl_bridge_connected: bool = False


def create_default_app_state(session_id: str) -> AppState:
    """创建默认状态"""
    return AppState(
        session_id=session_id,
        mcp=MCPState(),
        plugins=PluginState(),
        tasks={},
        todos={},
    )
