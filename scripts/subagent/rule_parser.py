"""
规则解析器 - Permission Rule Parser

将规则字符串解析为 PermissionRuleValue 结构。

格式: "ToolName" 或 "ToolName(content)"
示例:
    "Bash"              → tool_name="Bash", rule_content=None
    "Bash(git *)"       → tool_name="Bash", rule_content="git *"
    "Bash(python -c \\(1\\))"  → tool_name="Bash", rule_content="python -c (1)"
"""
from dataclasses import dataclass


LEGACY_TOOL_NAME_ALIASES: dict[str, str] = {
    "Task": "Agent",
    "KillShell": "TaskStop",
}

UNESCAPE_CHARS: dict[str, str] = {
    "\\(": "(",
    "\\)": ")",
    "\\\\": "\\",
}


@dataclass
class PermissionRuleValue:
    """规则值"""
    tool_name: str
    rule_content: str | None = None

    def __str__(self) -> str:
        if self.rule_content is None:
            return self.tool_name
        return f"{self.tool_name}({self.rule_content})"


def escape_rule_content(content: str) -> str:
    """
    转义规则内容中的特殊字符。
    
    转义顺序：
    1. 先转义反斜杠 \\
    2. 再转义括号 ()
    
    Args:
        content: 原始内容
        
    Returns:
        转义后的内容
        
    Examples:
        >>> escape_rule_content("python -c 'print(1)'")
        "python -c 'print\\(1\\)'"
    """
    result = content.replace("\\", "\\\\")
    result = result.replace("(", "\\(")
    result = result.replace(")", "\\)")
    return result


def unescape_rule_content(content: str) -> str:
    """
    反转义规则内容。
    
    反转义顺序（与转义相反）：
    1. 先反转义括号
    2. 再反转义反斜杠
    
    Args:
        content: 转义后的内容
        
    Returns:
        原始内容
        
    Examples:
        >>> unescape_rule_content("python -c 'print\\(1\\)'")
        "python -c 'print(1)'"
    """
    result = content.replace("\\(", "(")
    result = result.replace("\\)", ")")
    result = result.replace("\\\\", "\\")
    return result


def normalize_tool_name(name: str) -> str:
    """规范化工具名"""
    return LEGACY_TOOL_NAME_ALIASES.get(name, name)


def permission_rule_value_from_string(rule_string: str) -> PermissionRuleValue:
    """
    解析规则字符串。
    
    Args:
        rule_string: 规则字符串，如 "Bash(npm install)"
        
    Returns:
        PermissionRuleValue
        
    Raises:
        ValueError: 格式错误
        
    Examples:
        >>> permission_rule_value_from_string("Bash")
        PermissionRuleValue(tool_name='Bash', rule_content=None)
        
        >>> permission_rule_value_from_string("Bash(git *)")
        PermissionRuleValue(tool_name='Bash', rule_content='git *')
        
        >>> permission_rule_value_from_string("Bash(python -c \\(1\\))")
        PermissionRuleValue(tool_name='Bash', rule_content='python -c (1)')
    """
    if not rule_string:
        raise ValueError("Empty rule string")
    
    open_paren_index = _find_first_unescaped(rule_string, "(")
    
    if open_paren_index == -1:
        return PermissionRuleValue(tool_name=normalize_tool_name(rule_string))
    
    close_paren_index = _find_last_unescaped(rule_string, ")")
    
    if close_paren_index == -1 or close_paren_index <= open_paren_index:
        return PermissionRuleValue(tool_name=normalize_tool_name(rule_string))
    
    if close_paren_index != len(rule_string) - 1:
        return PermissionRuleValue(tool_name=normalize_tool_name(rule_string))
    
    tool_name = rule_string[:open_paren_index]
    if not tool_name:
        return PermissionRuleValue(tool_name=normalize_tool_name(rule_string))
    
    raw_content = rule_string[open_paren_index + 1:close_paren_index]
    
    if raw_content == "" or raw_content == "*":
        return PermissionRuleValue(tool_name=normalize_tool_name(tool_name))
    
    rule_content = unescape_rule_content(raw_content)
    return PermissionRuleValue(
        tool_name=normalize_tool_name(tool_name),
        rule_content=rule_content
    )


def permission_rule_value_to_string(rule_value: PermissionRuleValue) -> str:
    """
    将规则值转换为字符串。
    
    Args:
        rule_value: 规则值
        
    Returns:
        规则字符串
    """
    if rule_value.rule_content is None:
        return rule_value.tool_name
    escaped = escape_rule_content(rule_value.rule_content)
    return f"{rule_value.tool_name}({escaped})"


def _find_first_unescaped(s: str, char: str) -> int:
    """查找第一个未转义的字符位置"""
    for i, c in enumerate(s):
        if c != char:
            continue
        backslash_count = 0
        j = i - 1
        while j >= 0 and s[j] == "\\":
            backslash_count += 1
            j -= 1
        if backslash_count % 2 == 0:
            return i
    return -1


def _find_last_unescaped(s: str, char: str) -> int:
    """查找最后一个未转义的字符位置"""
    for i in range(len(s) - 1, -1, -1):
        if s[i] != char:
            continue
        backslash_count = 0
        j = i - 1
        while j >= 0 and s[j] == "\\":
            backslash_count += 1
            j -= 1
        if backslash_count % 2 == 0:
            return i
    return -1
