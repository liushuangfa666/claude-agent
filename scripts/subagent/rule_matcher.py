"""
规则匹配器 - Permission Rule Matcher

检查工具调用是否匹配权限规则。
"""
import fnmatch
from dataclasses import dataclass
from typing import Any

from .rule_parser import PermissionRuleValue


@dataclass
class MatchResult:
    """匹配结果"""
    matched: bool
    matched_rule: str | None = None
    reason: str | None = None


TOOL_MATCH_FIELDS: dict[str, str] = {
    "Bash": "command",
    "PowerShell": "command",
    "Read": "file_path",
    "Write": "file_path",
    "Edit": "file_path",
    "Glob": "pattern",
    "Grep": "pattern",
    "WebFetch": "url",
    "WebSearch": "query",
}


def match_tool_call(
    tool_name: str,
    tool_input: dict[str, Any],
    rule: PermissionRuleValue
) -> MatchResult:
    """
    检查工具调用是否匹配规则。
    
    Args:
        tool_name: 工具名称
        tool_input: 工具输入参数
        rule: 权限规则
        
    Returns:
        MatchResult
    """
    if rule.tool_name != tool_name:
        return MatchResult(matched=False)
    
    if rule.rule_content is None:
        return MatchResult(matched=True, reason="tool-wide rule")
    
    match_value = extract_match_value(tool_name, tool_input)
    if match_value is None:
        return MatchResult(matched=False, reason="no match value")
    
    if _match_content(match_value, rule.rule_content):
        return MatchResult(
            matched=True,
            matched_rule=rule.rule_content,
            reason=f"matched: {rule.rule_content}"
        )
    
    return MatchResult(matched=False, reason="content mismatch")


def _match_content(value: str, pattern: str) -> bool:
    """
    匹配内容。
    
    支持的匹配模式：
    - 精确匹配: "git commit"
    - 通配符: "git *"
    - 前缀匹配: "git commit:*"
    - Glob 模式: "*.py"
    """
    if pattern.endswith(":*"):
        prefix = pattern[:-2]
        return value.startswith(prefix)
    
    if "*" in pattern:
        return fnmatch.fnmatch(value, pattern)
    
    return value == pattern


def extract_match_value(tool_name: str, tool_input: dict[str, Any]) -> str | None:
    """
    从工具输入中提取用于匹配的值。
    """
    field = TOOL_MATCH_FIELDS.get(tool_name)
    if field is None:
        return None
    
    value = tool_input.get(field)
    if value is None:
        return None
    
    return str(value)


class RuleMatcher:
    """规则匹配器"""
    
    def __init__(self, rules: list[tuple[PermissionRuleValue, str]]):
        """
        初始化匹配器。
        
        Args:
            rules: [(rule_value, behavior), ...]
        """
        self.rules = rules
    
    def check(
        self,
        tool_name: str,
        tool_input: dict[str, Any]
    ) -> str | None:
        """
        检查工具调用。
        
        Returns:
            "allow", "deny", "ask" 或 None（无匹配规则）
        """
        for rule, behavior in self.rules:
            if behavior == "deny":
                result = match_tool_call(tool_name, tool_input, rule)
                if result.matched:
                    return "deny"
        
        for rule, behavior in self.rules:
            if behavior == "ask":
                result = match_tool_call(tool_name, tool_input, rule)
                if result.matched:
                    return "ask"
        
        for rule, behavior in self.rules:
            if behavior == "allow":
                result = match_tool_call(tool_name, tool_input, rule)
                if result.matched:
                    return "allow"
        
        return None
