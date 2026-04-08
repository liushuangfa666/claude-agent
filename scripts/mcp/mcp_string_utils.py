"""
MCP 字符串工具函数

MCP 工具名称格式: mcp__serverName__toolName
示例: mcp__github__create_issue
"""
from __future__ import annotations

import re

# MCP 工具名称前缀
MCP_TOOL_PREFIX = "mcp__"

# 工具名称格式的正则表达式
TOOL_NAME_PATTERN = re.compile(r"^mcp__([a-zA-Z0-9_-]+)__([a-zA-Z0-9_-]+)$")


def format_mcp_tool_name(server_name: str, tool_name: str) -> str:
    """
    格式化 MCP 工具名称
    
    Args:
        server_name: 服务器名称
        tool_name: 工具名称
    
    Returns:
        格式化的工具名称，格式为 mcp__serverName__toolName
    
    Examples:
        >>> format_mcp_tool_name("github", "create_issue")
        'mcp__github__create_issue'
        >>> format_mcp_tool_name("filesystem", "read_file")
        'mcp__filesystem__read_file'
    """
    server_name = server_name.lower().strip().replace(" ", "_").replace("-", "_")
    tool_name = tool_name.lower().strip().replace(" ", "_").replace("-", "_")

    return f"{MCP_TOOL_PREFIX}{server_name}__{tool_name}"


def parse_mcp_tool_name(full_name: str) -> tuple[str, str] | None:
    """
    解析 MCP 工具完整名称
    
    Args:
        full_name: 完整的工具名称，格式为 mcp__serverName__toolName
    
    Returns:
        (server_name, tool_name) 元组，如果格式不正确则返回 None
    
    Examples:
        >>> parse_mcp_tool_name("mcp__github__create_issue")
        ('github', 'create_issue')
        >>> parse_mcp_tool_name("mcp__filesystem__read_file")
        ('filesystem', 'read_file')
        >>> parse_mcp_tool_name("invalid_name")
        None
    """
    if not full_name:
        return None

    match = TOOL_NAME_PATTERN.match(full_name)
    if not match:
        return None

    return (match.group(1), match.group(2))


def get_server_name_from_tool_name(full_name: str) -> str | None:
    """
    从完整工具名称中提取服务器名称
    
    Args:
        full_name: 完整的工具名称
    
    Returns:
        服务器名称，如果格式不正确则返回 None
    """
    result = parse_mcp_tool_name(full_name)
    return result[0] if result else None


def get_tool_name_from_mcp_name(full_name: str) -> str | None:
    """
    从完整工具名称中提取工具名称
    
    Args:
        full_name: 完整的工具名称
    
    Returns:
        工具名称，如果格式不正确则返回 None
    """
    result = parse_mcp_tool_name(full_name)
    return result[1] if result else None


def is_mcp_tool_name(name: str) -> bool:
    """
    检查名称是否为有效的 MCP 工具名称格式
    
    Args:
        name: 要检查的名称
    
    Returns:
        如果是有效的 MCP 工具名称格式返回 True
    """
    return TOOL_NAME_PATTERN.match(name) is not None


def normalize_tool_name(name: str) -> str:
    """
    标准化工具名称
    
    将各种格式的工具名称转换为标准的小写下划线格式。
    """
    return name.lower().strip().replace(" ", "_").replace("-", "_")


def create_mcp_tool_description(
    server_name: str,
    tool_name: str,
    original_description: str | None = None,
) -> str:
    """
    创建 MCP 工具的描述
    """
    base = f"[{server_name}] {tool_name}"
    if original_description:
        base += f": {original_description}"
    return base
