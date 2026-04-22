"""
权限上下文 - Permission Context

子代理权限上下文构建和管理。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .rule_parser import PermissionRuleValue, permission_rule_value_from_string
from .types import SubagentType


class PermissionMode(Enum):
    """权限模式"""
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    BYPASS_PERMISSIONS = "bypassPermissions"
    DONT_ASK = "dontAsk"
    PLAN = "plan"


class RuleSource(Enum):
    """规则来源"""
    USER_SETTINGS = "userSettings"
    PROJECT_SETTINGS = "projectSettings"
    LOCAL_SETTINGS = "localSettings"
    CLI_ARG = "cliArg"
    SUBNET_TYPE = "subagentType"


class PermissionBehavior(Enum):
    """权限行为"""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass
class ToolPermissionContext:
    """工具权限上下文"""
    mode: PermissionMode = PermissionMode.DEFAULT
    additional_working_directories: dict[str, Any] = field(default_factory=dict)
    always_allow_rules: dict[RuleSource, list[str]] = field(default_factory=dict)
    always_deny_rules: dict[RuleSource, list[str]] = field(default_factory=dict)
    always_ask_rules: dict[RuleSource, list[str]] = field(default_factory=dict)


@dataclass
class SubagentToolConfig:
    """子代理工具配置"""
    allowed_tools: list[str]
    denied_tools: list[str] = field(default_factory=list)
    ask_tools: list[str] = field(default_factory=list)
    url_patterns: list[str] = field(default_factory=list)
    bash_allowed_patterns: list[str] = field(default_factory=list)
    bash_denied_patterns: list[str] = field(default_factory=list)


SUBAGENT_TOOL_CONFIGS: dict[SubagentType, SubagentToolConfig] = {
    SubagentType.EXPLORE: SubagentToolConfig(
        allowed_tools=["Read", "Glob", "Grep", "WebFetch", "WebSearch"],
        denied_tools=["WebFetch(*.exe)", "WebFetch(*.dmg)"],
        ask_tools=["WebFetch", "WebSearch"],
        url_patterns=["https://*", "http://localhost:*", "http://127.0.0.1:*"],
    ),
    SubagentType.PLAN: SubagentToolConfig(
        allowed_tools=["Read", "Glob", "Grep", "WebFetch", "WebSearch", "AskUserQuestion"],
        denied_tools=["WebFetch(*.exe)", "WebFetch(*.dmg)"],
        ask_tools=["WebFetch", "WebSearch"],
        url_patterns=["https://*"],
    ),
    SubagentType.VERIFICATION: SubagentToolConfig(
        allowed_tools=["Read", "Glob", "Grep", "Bash"],
        denied_tools=[
            "Bash(sudo *)",
            "Bash(rm -rf *)",
            "Bash(chmod 777 *)",
            "Bash(fdisk *)",
            "Bash(mkfs *)",
        ],
        ask_tools=["Bash"],
        bash_allowed_patterns=["git *", "npm *", "pytest *", "python *"],
    ),
    SubagentType.GENERAL_PURPOSE: SubagentToolConfig(
        allowed_tools=[],
        denied_tools=[],
    ),
}


def build_permission_context(
    subagent_type: SubagentType,
    mode: PermissionMode = PermissionMode.DEFAULT,
    extra_rules: dict[PermissionBehavior, list[str]] | None = None
) -> ToolPermissionContext:
    """
    根据子代理类型构建权限上下文。
    """
    config = SUBAGENT_TOOL_CONFIGS.get(subagent_type)
    
    context = ToolPermissionContext(
        mode=mode,
        always_allow_rules={RuleSource.SUBNET_TYPE: []},
        always_deny_rules={RuleSource.SUBNET_TYPE: []},
        always_ask_rules={RuleSource.SUBNET_TYPE: []},
    )
    
    if config is None:
        return context
    
    context.always_allow_rules[RuleSource.SUBNET_TYPE] = config.allowed_tools.copy()
    context.always_ask_rules[RuleSource.SUBNET_TYPE] = config.ask_tools.copy()
    context.always_deny_rules[RuleSource.SUBNET_TYPE] = config.denied_tools.copy()
    
    if extra_rules:
        for behavior, rules in extra_rules.items():
            if behavior == PermissionBehavior.ALLOW:
                context.always_allow_rules[RuleSource.SUBNET_TYPE].extend(rules)
            elif behavior == PermissionBehavior.DENY:
                context.always_deny_rules[RuleSource.SUBNET_TYPE].extend(rules)
            elif behavior == PermissionBehavior.ASK:
                context.always_ask_rules[RuleSource.SUBNET_TYPE].extend(rules)
    
    return context


def get_effective_rules(
    context: ToolPermissionContext,
) -> list[tuple[PermissionRuleValue, str]]:
    """
    获取合并后的有效规则。
    
    优先级：deny > ask > allow
    """
    rules: list[tuple[PermissionRuleValue, str]] = []
    
    for source, rule_strings in context.always_deny_rules.items():
        for rule_str in rule_strings:
            try:
                rule_value = permission_rule_value_from_string(rule_str)
                rules.append((rule_value, "deny"))
            except ValueError:
                pass
    
    for source, rule_strings in context.always_ask_rules.items():
        for rule_str in rule_strings:
            try:
                rule_value = permission_rule_value_from_string(rule_str)
                rules.append((rule_value, "ask"))
            except ValueError:
                pass
    
    for source, rule_strings in context.always_allow_rules.items():
        for rule_str in rule_strings:
            try:
                rule_value = permission_rule_value_from_string(rule_str)
                rules.append((rule_value, "allow"))
            except ValueError:
                pass
    
    return rules
