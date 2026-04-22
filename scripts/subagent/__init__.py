"""
Subagent Type System - 子代理类型系统

提供四种类型的子代理:
- Explore: 只读代码探索 (Haiku)
- Plan: 复杂任务规划 (Opus)
- Verification: 测试验证 (Sonnet)
- GeneralPurpose: 通用类型 (默认)
"""
from __future__ import annotations

from .executor import SubagentExecutor, create_subagent_executor
from .permission_context import (
    PermissionMode,
    RuleSource,
    PermissionBehavior,
    ToolPermissionContext,
    SubagentToolConfig,
    SUBAGENT_TOOL_CONFIGS,
    build_permission_context,
    get_effective_rules,
)
from .prompts import SUBAGENT_PROMPTS, get_subagent_prompt
from .registry import SubagentRegistry, get_subagent_registry
from .rule_matcher import RuleMatcher, MatchResult, match_tool_call
from .rule_parser import (
    PermissionRuleValue,
    escape_rule_content,
    unescape_rule_content,
    normalize_tool_name,
    permission_rule_value_from_string,
    permission_rule_value_to_string,
)
from .security_checker import SecurityChecker, RiskLevel, SecurityCheckResult
from .tool_filter import (
    SUBAGENT_TOOLS,
    filter_tools_by_type,
    get_allowed_tools,
    is_tool_allowed,
    get_tool_restriction_message,
    create_tool_wrapper,
    check_tool_permission,
    get_tool_config,
)
from .tool_wrapper import (
    ToolWrapper,
    ToolPermissionDeniedError,
    ToolPermissionAskError,
    create_subagent_tool_wrapper,
)
from .types import SUBAGENT_TYPE_NAMES, SubagentType

__all__ = [
    # Types
    "SubagentType",
    "SUBAGENT_TYPE_NAMES",
    # Prompts
    "SUBAGENT_PROMPTS",
    "get_subagent_prompt",
    # Tool Filter
    "SUBAGENT_TOOLS",
    "get_allowed_tools",
    "filter_tools_by_type",
    "is_tool_allowed",
    "get_tool_restriction_message",
    "create_tool_wrapper",
    "check_tool_permission",
    "get_tool_config",
    # Registry
    "SubagentRegistry",
    "get_subagent_registry",
    # Executor
    "SubagentExecutor",
    "create_subagent_executor",
    # Rule Parser
    "PermissionRuleValue",
    "escape_rule_content",
    "unescape_rule_content",
    "normalize_tool_name",
    "permission_rule_value_from_string",
    "permission_rule_value_to_string",
    # Rule Matcher
    "RuleMatcher",
    "MatchResult",
    "match_tool_call",
    # Security Checker
    "SecurityChecker",
    "RiskLevel",
    "SecurityCheckResult",
    # Permission Context
    "PermissionMode",
    "RuleSource",
    "PermissionBehavior",
    "ToolPermissionContext",
    "SubagentToolConfig",
    "SUBAGENT_TOOL_CONFIGS",
    "build_permission_context",
    "get_effective_rules",
    # Tool Wrapper
    "ToolWrapper",
    "ToolPermissionDeniedError",
    "ToolPermissionAskError",
    "create_subagent_tool_wrapper",
]
