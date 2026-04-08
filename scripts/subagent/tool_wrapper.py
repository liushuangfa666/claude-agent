"""
工具包装器 - Tool Wrapper

为工具调用添加权限检查层。
"""
from typing import Any, Callable

from .permission_context import (
    ToolPermissionContext,
    get_effective_rules,
    build_permission_context,
)
from .rule_matcher import RuleMatcher
from .security_checker import SecurityChecker
from .types import SubagentType


class ToolPermissionDeniedError(Exception):
    """工具权限被拒绝"""
    def __init__(self, message: str, tool_name: str):
        super().__init__(message)
        self.tool_name = tool_name


class ToolPermissionAskError(Exception):
    """工具需要用户确认"""
    def __init__(self, message: str, tool_name: str):
        super().__init__(message)
        self.tool_name = tool_name


class ToolWrapper:
    """工具包装器"""
    
    def __init__(
        self,
        context: ToolPermissionContext,
        security_checker: SecurityChecker | None = None,
    ):
        self.context = context
        self.security_checker = security_checker or SecurityChecker()
        self.rules = get_effective_rules(context)
        self.matcher = RuleMatcher(self.rules)
    
    def check(self, tool_name: str, tool_input: dict[str, Any]) -> None:
        """
        检查工具调用权限。
        
        Raises:
            ToolPermissionDeniedError: 权限被拒绝
            ToolPermissionAskError: 需要用户确认
        """
        if self.context.mode.value == "bypassPermissions":
            return
        
        behavior = self.matcher.check(tool_name, tool_input)
        
        if behavior == "deny":
            raise ToolPermissionDeniedError(
                f"Tool '{tool_name}' is denied by permission rules",
                tool_name
            )
        
        if behavior == "ask":
            raise ToolPermissionAskError(
                f"Tool '{tool_name}' requires user confirmation",
                tool_name
            )
        
        if tool_name in ("Bash", "PowerShell"):
            result = self.security_checker.check_bash_command(
                tool_input.get("command", "")
            )
            if not result.is_safe:
                raise ToolPermissionDeniedError(
                    f"Bash command is not safe: {result.message}",
                    tool_name
                )
        
        elif tool_name in ("Read", "Write", "Edit"):
            result = self.security_checker.check_file_path(
                tool_input.get("file_path", "")
            )
            if not result.is_safe:
                raise ToolPermissionDeniedError(
                    f"File path is not allowed: {result.message}",
                    tool_name
                )
        
        elif tool_name in ("WebFetch",):
            result = self.security_checker.check_url(
                tool_input.get("url", "")
            )
            if not result.is_safe:
                raise ToolPermissionDeniedError(
                    f"URL is not allowed: {result.message}",
                    tool_name
                )
        
        if behavior is None:
            pass
    
    def wrap_tool_call(
        self,
        tool_call_fn: Callable[..., Any]
    ) -> Callable[..., Any]:
        """
        包装工具调用函数。
        """
        def wrapped(tool_name: str, tool_input: dict[str, Any], **kwargs) -> Any:
            self.check(tool_name, tool_input)
            return tool_call_fn(tool_name, tool_input, **kwargs)
        
        return wrapped


def create_subagent_tool_wrapper(subagent_type: SubagentType) -> ToolWrapper:
    """
    为子代理类型创建工具包装器。
    """
    context = build_permission_context(subagent_type)
    return ToolWrapper(context)
