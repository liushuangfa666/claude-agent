"""
类型特定工具过滤 - Type-Specific Tool Restrictions

重构版本，基于权限规则系统。
支持细粒度的工具和参数控制。
"""
from __future__ import annotations

from typing import Any

from .permission_context import (
    build_permission_context,
    ToolPermissionContext,
    SubagentToolConfig,
    SUBAGENT_TOOL_CONFIGS,
)
from .security_checker import SecurityChecker
from .tool_wrapper import ToolWrapper
from .types import SubagentType


SUBAGENT_TOOLS: dict[str, list[str] | None] = {
    "Explore": ["Read", "Glob", "Grep", "WebFetch", "WebSearch"],
    "Plan": ["Read", "Glob", "Grep", "WebFetch", "WebSearch", "AskUserQuestion"],
    "Verification": ["Read", "Glob", "Grep", "Bash"],
    "GeneralPurpose": None,
}


def get_allowed_tools(subagent_type: str) -> list[str] | None:
    """获取指定类型的允许工具列表（简单版本）"""
    return SUBAGENT_TOOLS.get(subagent_type)


def filter_tools_by_type(
    all_tools: list[dict],
    subagent_type: str
) -> list[dict]:
    """根据子代理类型过滤工具列表（简单版本）"""
    allowed = get_allowed_tools(subagent_type)
    
    if allowed is None:
        return all_tools
    
    return [tool for tool in all_tools if tool.get("name") in allowed]


def is_tool_allowed(tool_name: str, subagent_type: str) -> bool:
    """检查工具是否在指定类型下允许使用"""
    allowed = get_allowed_tools(subagent_type)
    
    if allowed is None:
        return True
    
    return tool_name in allowed


def get_tool_restriction_message(subagent_type: str) -> str:
    """获取工具限制说明消息"""
    allowed = get_allowed_tools(subagent_type)
    
    if allowed is None:
        return "All tools are available."
    
    return f"Allowed tools: {', '.join(allowed)}"


def create_tool_wrapper(subagent_type: str) -> ToolWrapper:
    """为子代理类型创建工具包装器（新接口）"""
    try:
        st = SubagentType(subagent_type)
    except ValueError:
        st = SubagentType.GENERAL_PURPOSE
    
    return ToolWrapper(build_permission_context(st))


def check_tool_permission(
    tool_name: str,
    tool_input: dict[str, Any],
    subagent_type: str
) -> tuple[bool, str]:
    """检查工具调用权限（新接口）"""
    wrapper = create_tool_wrapper(subagent_type)
    
    try:
        wrapper.check(tool_name, tool_input)
        return True, "allowed"
    except Exception as e:
        return False, str(e)


def get_tool_config(subagent_type: str) -> SubagentToolConfig | None:
    """获取子代理工具配置"""
    try:
        st = SubagentType(subagent_type)
    except ValueError:
        return None
    
    return SUBAGENT_TOOL_CONFIGS.get(st)
