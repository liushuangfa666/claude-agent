"""
Skill Slash Command 解析器

负责解析 /skill-name arg1 arg2 格式的命令。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SlashCommand:
    """Slash 命令"""
    skill_name: str
    arguments: str

    @property
    def is_empty(self) -> bool:
        """是否为空命令"""
        return not self.skill_name


def parse_slash_command(text: str) -> SlashCommand | None:
    """
    解析 slash 命令

    支持格式:
    - /skill-name
    - /skill-name arg1 arg2
    - /skill-name "multi word arg"

    Args:
        text: 用户输入文本

    Returns:
        SlashCommand 或 None（如果不是有效的 slash 命令）
    """
    if not text or not isinstance(text, str):
        return None

    stripped = text.strip()

    # 必须以 / 开头
    if not stripped.startswith('/'):
        return None

    # 去掉开头的 /
    rest = stripped[1:]

    # 不能连续两个 /
    if rest.startswith('/'):
        return None

    # 解析 skill name 和 arguments
    # 格式: skill-name [args...]
    pattern = r'^(\w+)(?:\s+(.*))?$'
    match = re.match(pattern, rest)

    if not match:
        return None

    skill_name = match.group(1)
    arguments = match.group(2) or ""

    if not skill_name:
        return None

    return SlashCommand(skill_name=skill_name, arguments=arguments)


def is_slash_command(text: str) -> bool:
    """检查文本是否是 slash 命令"""
    return parse_slash_command(text) is not None


def extract_skill_invocation(text: str) -> tuple[str, str] | None:
    """
    从文本中提取 skill 调用

    如果文本是纯 slash 命令，返回 (skill_name, arguments)
    否则返回 None
    """
    cmd = parse_slash_command(text)
    if cmd is None:
        return None

    # 检查是否只是 slash 命令（没有其他内容）
    # /skill args 这种格式才是 skill 调用
    return (cmd.skill_name, cmd.arguments)
