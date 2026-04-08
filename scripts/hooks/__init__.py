"""
Enhanced Hook System - 32种事件类型 + PromptHook/HttpHook/AgentHook
"""
from .agent_hook import AgentHook
from .enhanced import (
    HOOK_EVENTS,
    EnhancedHookManager,
    EnvMatcher,
    Hook,
    HookCondition,
    HookConfig,
    HookResult,
    PathMatcher,
    ToolMatcher,
    get_enhanced_hook_manager,
    reset_enhanced_hook_manager,
)
from .http_hook import HttpHook
from .prompt_hook import PromptHook

HookManager = EnhancedHookManager

SessionStartHook = Hook
BeforeToolHook = Hook
AfterToolHook = Hook
StopHook = Hook


def get_hook_manager() -> EnhancedHookManager:
    return get_enhanced_hook_manager()


def reset_hook_manager() -> None:
    reset_enhanced_hook_manager()


__all__ = [
    "HOOK_EVENTS",
    "EnhancedHookManager",
    "HookManager",
    "Hook",
    "HookConfig",
    "HookResult",
    "HookCondition",
    "ToolMatcher",
    "EnvMatcher",
    "PathMatcher",
    "PromptHook",
    "HttpHook",
    "AgentHook",
    "SessionStartHook",
    "BeforeToolHook",
    "AfterToolHook",
    "StopHook",
    "get_hook_manager",
    "reset_hook_manager",
]
