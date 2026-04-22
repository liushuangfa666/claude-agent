"""
Enhanced HookManager - 32种事件类型
"""
from __future__ import annotations

import asyncio
import fnmatch
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


HOOK_EVENTS = [
    # 工具相关 (6)
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "ToolUseBlocked",      # 工具被阻止（权限或其他原因）
    "ToolUseDenied",       # 工具被拒绝
    # 会话相关 (4)
    "SessionStart",
    "SessionEnd",
    "UserPromptSubmit",
    "Notification",
    # 子代理相关 (4)
    "SubagentStart",
    "SubagentStop",
    "PreAgentCreate",      # 子代理创建前
    "PostAgentCreate",     # 子代理创建后
    # 权限相关 (2)
    "PermissionRequest",
    "PermissionDenied",
    # LLM 相关 (2)
    "LLMStart",            # LLM 开始调用
    "LLMComplete",         # LLM 完成调用
    # 上下文相关 (6)
    "PreCompact",
    "PostCompact",
    "CwdChanged",
    "FileChanged",
    "InstructionsLoaded",
    "ConfigChange",
    # 任务相关 (2)
    "TaskCreated",
    "TaskCompleted",
    # 团队相关 (3)
    "TeammateIdle",
    "Elicitation",
    "ElicitationResult",
    # Worktree (2)
    "WorktreeCreate",
    "WorktreeRemove",
    # 其他 (3)
    "Stop",
    "StopFailure",
    "Setup",
]


@dataclass
class HookConfig:
    enabled: bool = True
    async_execution: bool = True
    timeout_seconds: int = 30
    retry_count: int = 0


@dataclass
class HookResult:
    hook_name: str
    success: bool
    message: str = ""
    error: str = ""
    duration_ms: int = 0
    modified_context: dict | None = None


@dataclass
class HookRegistration:
    name: str
    callback: Callable | str | None = None
    condition: str | None = None
    enabled: bool = True
    priority: int = 0


class Hook:
    """Hook 基类"""

    def __init__(
        self,
        name: str,
        callback: Callable | str | None = None,
        condition: str | None = None,
    ):
        self.name = name
        self.callback = callback
        self.condition = condition
        self._enabled = True
        self._priority = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    @property
    def priority(self) -> int:
        return self._priority

    @priority.setter
    def priority(self, value: int):
        self._priority = value

    async def execute(self, context: dict) -> HookResult:
        if not self._enabled:
            return HookResult(hook_name=self.name, success=True, message="disabled")

        start = datetime.now()

        try:
            if callable(self.callback):
                result = self.callback(context)
                if asyncio.iscoroutine(result):
                    result = await result
                return HookResult(
                    hook_name=self.name,
                    success=True,
                    message=str(result) if result else "executed",
                    duration_ms=int((datetime.now() - start).total_seconds() * 1000),
                )
            elif isinstance(self.callback, str):
                proc = await asyncio.create_subprocess_shell(
                    self.callback,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode == 0:
                    return HookResult(
                        hook_name=self.name,
                        success=True,
                        message=stdout.decode() if stdout else "executed",
                        duration_ms=int((datetime.now() - start).total_seconds() * 1000),
                    )
                else:
                    return HookResult(
                        hook_name=self.name,
                        success=False,
                        error=stderr.decode() if stderr else f"exit code {proc.returncode}",
                        duration_ms=int((datetime.now() - start).total_seconds() * 1000),
                    )
            else:
                return HookResult(
                    hook_name=self.name,
                    success=True,
                    message="no callback configured",
                    duration_ms=int((datetime.now() - start).total_seconds() * 1000),
                )
        except Exception as e:
            logger.error(f"Hook {self.name} failed: {e}")
            return HookResult(
                hook_name=self.name,
                success=False,
                error=str(e),
                duration_ms=int((datetime.now() - start).total_seconds() * 1000),
            )


class EnhancedHookManager:
    """增强的 Hook 管理器 - 支持 32 种事件类型"""

    def __init__(self):
        self._hooks: dict[str, list[Hook]] = {event: [] for event in HOOK_EVENTS}
        self._config = HookConfig()
        self._conditions: dict[str, list[HookCondition]] = {}

    @property
    def config(self) -> HookConfig:
        return self._config

    def register(self, hook: Hook) -> None:
        if hook.name in self._hooks:
            self._hooks[hook.name].append(hook)
            self._hooks[hook.name].sort(key=lambda h: h.priority, reverse=True)
            logger.info(f"Registered hook: {hook.name}")
        else:
            logger.warning(f"Unknown hook type: {hook.name}")

    def unregister(self, hook_name: str, callback: Any = None) -> None:
        if hook_name not in self._hooks:
            return

        if callback is None:
            self._hooks[hook_name].clear()
        else:
            self._hooks[hook_name] = [
                h for h in self._hooks[hook_name] if h.callback != callback
            ]

    def get_hooks(self, hook_name: str) -> list[Hook]:
        return self._hooks.get(hook_name, [])

    async def trigger(self, event: str, context: dict) -> HookResult:
        hooks = self.get_hooks(event)
        if not hooks:
            return HookResult(hook_name=event, success=True, message="no hooks registered")

        results = []
        for hook in hooks:
            result = await hook.execute(context)
            results.append(result)
            if not result.success:
                return result

        all_success = all(r.success for r in results)
        messages = [r.message for r in results if r.message]
        return HookResult(
            hook_name=event,
            success=all_success,
            message="; ".join(messages) if messages else "executed",
            duration_ms=sum(r.duration_ms for r in results),
        )

    async def trigger_async(self, event: str, context: dict) -> list[HookResult]:
        hooks = self.get_hooks(event)
        if not hooks:
            return [HookResult(hook_name=event, success=True, message="no hooks registered")]

        tasks = [hook.execute(context) for hook in hooks]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def should_trigger(self, event: str, context: dict) -> bool:
        hooks = self.get_hooks(event)
        if not hooks:
            return False

        for hook in hooks:
            if not hook.enabled:
                continue
            if hook.condition:
                cond = HookCondition()
                if cond.matches(context, hook.condition):
                    return True
            else:
                return True
        return False

    def load_from_config(self, config: dict) -> None:
        """
        从配置字典加载 hooks。

        配置格式:
        {
            "hooks": {
                "SessionStart": [{"callback": "echo start", "enabled": True}],
                "PreToolUse": [{"callback": "echo pre", "condition": "Bash(rm *)"}],
                ...
            },
            "http_hooks": [
                {"url": "https://example.com/webhook", "method": "POST", "event": "PostToolUse"},
                ...
            ]
        }
        """
        from .http_hook import HttpHook, load_http_hooks_from_config

        hooks_config = config.get("hooks", {})

        for event_name, hooks in hooks_config.items():
            if event_name not in HOOK_EVENTS:
                logger.warning(f"Unknown hook event: {event_name}")
                continue

            for hook_config in hooks:
                callback = hook_config.get("callback")
                if not callback:
                    continue

                hook = Hook(
                    name=event_name,
                    callback=callback,
                    condition=hook_config.get("condition"),
                )
                hook.enabled = hook_config.get("enabled", True)
                hook.priority = hook_config.get("priority", 0)
                self.register(hook)

        http_hooks = load_http_hooks_from_config(config)
        for hook in http_hooks:
            # HTTP hooks 的 condition 字段包含事件名，需要修改 hook 的 name
            if hook.condition and hook.condition in HOOK_EVENTS:
                hook.name = hook.condition
                hook.condition = None  # 清除 condition，因为 name 已经设置为事件
            self.register(hook)


class HookCondition:
    """Hook 条件匹配器"""

    TOOL_PATTERN = re.compile(r"^(\w+)\((.*)\)$")

    def matches(self, context: dict, pattern: str) -> bool:
        pattern = pattern.strip()

        if pattern.startswith("env:"):
            return self._match_env(pattern[4:], context)

        if pattern.startswith("path:"):
            return self._match_path(pattern[5:], context)

        tool_match = self.TOOL_PATTERN.match(pattern)
        if tool_match:
            tool_name = tool_match.group(1)
            args_pattern = tool_match.group(2)
            return self._match_tool(tool_name, args_pattern, context)

        if ":" in pattern:
            key, value = pattern.split(":", 1)
            if key == "tool_name":
                return context.get("tool_name") == value
            return context.get(key) == value

        return context.get("tool_name") == pattern

    def _match_env(self, pattern: str, context: dict) -> bool:
        if "=" in pattern:
            var_name, expected_value = pattern.split("=", 1)
            return os.environ.get(var_name) == expected_value
        return os.environ.get(pattern) is not None

    def _match_path(self, pattern: str, context: dict) -> bool:
        path = context.get("path") or context.get("file_path") or ""
        return bool(fnmatch.fnmatch(path, pattern))

    def _match_tool(self, tool_name: str, args_pattern: str, context: dict) -> bool:
        if context.get("tool_name") != tool_name:
            return False

        if not args_pattern or args_pattern == "*":
            return True

        tool_args = context.get("tool_args", {})
        args_str = str(tool_args)

        if "*" in args_pattern:
            return bool(fnmatch.fnmatch(args_str, f"*{args_pattern}*"))

        return args_pattern in args_str


class ToolMatcher:
    def __init__(self, patterns: list[str]):
        self.patterns = patterns

    def matches(self, tool_name: str) -> bool:
        for pattern in self.patterns:
            if fnmatch.fnmatch(tool_name, pattern):
                return True
        return False


class EnvMatcher:
    def __init__(self, env_conditions: dict[str, str]):
        self.conditions = env_conditions

    def matches(self) -> bool:
        for var_name, expected_value in self.conditions.items():
            actual_value = os.environ.get(var_name)
            if actual_value != expected_value:
                return False
        return True


class PathMatcher:
    def __init__(self, patterns: list[str]):
        self.patterns = patterns

    def matches(self, path: str) -> bool:
        for pattern in self.patterns:
            if fnmatch.fnmatch(path, pattern):
                return True
        return False


_enhanced_hook_manager: EnhancedHookManager | None = None


def get_enhanced_hook_manager() -> EnhancedHookManager:
    global _enhanced_hook_manager
    if _enhanced_hook_manager is None:
        _enhanced_hook_manager = EnhancedHookManager()
    return _enhanced_hook_manager


def reset_enhanced_hook_manager() -> None:
    global _enhanced_hook_manager
    _enhanced_hook_manager = None
