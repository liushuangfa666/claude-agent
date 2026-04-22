"""
Claude Agent - 参考 Claude Code 架构的 agent 实现
"""
from .agent import Agent, AgentConfig, create_agent
from .context import ContextBuilder, build_default_context
from .hooks import (
    AfterToolHook,
    BeforeToolHook,
    Hook,
    HookConfig,
    HookManager,
    HookResult,
    SessionStartHook,
    StopHook,
    get_hook_manager,
    reset_hook_manager,
)
from .permission import PermissionEngine, PermissionResult
from .plan_mode import (
    Plan,
    PlanModeManager,
    PlanStep,
    get_plan_mode_manager,
    reset_plan_mode,
)
from .plugins import (
    Plugin,
    PluginMetadata,
    PluginRegistry,
    get_plugin_registry,
    reset_plugin_registry,
)
from .system_prompt import SystemPromptBuilder, build_system_prompt
from .tool import BaseTool, ToolRegistry, ToolResult, get_registry, register
from .tools import BashTool, EditTool, GlobTool, GrepTool, ReadTool, WriteTool

__all__ = [
    "Agent",
    "AgentConfig",
    "create_agent",
    "BaseTool",
    "ToolResult",
    "ToolRegistry",
    "get_registry",
    "register",
    "PermissionEngine",
    "PermissionResult",
    "build_default_context",
    "ContextBuilder",
    "build_system_prompt",
    "SystemPromptBuilder",
    "ReadTool",
    "BashTool",
    "WriteTool",
    "GrepTool",
    "GlobTool",
    "EditTool",
    "PlanModeManager",
    "Plan",
    "PlanStep",
    "get_plan_mode_manager",
    "reset_plan_mode",
    "HookManager",
    "Hook",
    "HookConfig",
    "HookResult",
    "SessionStartHook",
    "BeforeToolHook",
    "AfterToolHook",
    "StopHook",
    "get_hook_manager",
    "reset_hook_manager",
    "PluginRegistry",
    "Plugin",
    "PluginMetadata",
    "get_plugin_registry",
    "reset_plugin_registry",
]
