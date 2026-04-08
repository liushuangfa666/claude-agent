"""
Hook 系统 - 参考 Claude Code 的 hooks 设计

支持以下钩子：
- Session Start Hook - 会话开始时
- Before Tool Hook - 工具执行前
- After Tool Hook - 工具执行后
- Stop Hook - 停止时
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class HookConfig:
    """Hook 配置"""
    enabled: bool = True
    async_execution: bool = True  # 是否异步执行钩子


@dataclass
class HookResult:
    """Hook 执行结果"""
    hook_name: str
    success: bool
    message: str = ""
    error: str = ""
    duration_ms: int = 0


class Hook:
    """Hook 基类"""

    def __init__(self, name: str, callback: Callable | str | None = None):
        self.name = name
        self.callback = callback
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    async def execute(self, context: dict) -> HookResult:
        """执行钩子"""
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
                # 命令字符串，执行 shell 命令
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


class SessionStartHook(Hook):
    """会话开始时执行"""

    def __init__(self, callback: Callable | str | None = None):
        super().__init__("SessionStart", callback)


class BeforeToolHook(Hook):
    """工具执行前执行"""

    def __init__(self, callback: Callable | str | None = None):
        super().__init__("BeforeTool", callback)

    async def execute(self, context: dict) -> HookResult:
        """执行前 hook，可返回 None 阻止工具执行"""
        if not self._enabled:
            return HookResult(hook_name=self.name, success=True, message="disabled")

        start = datetime.now()

        try:
            if callable(self.callback):
                result = self.callback(context)
                if asyncio.iscoroutine(result):
                    result = await result

                if result is False:
                    return HookResult(
                        hook_name=self.name,
                        success=False,
                        error="Hook returned False, tool execution blocked",
                        duration_ms=int((datetime.now() - start).total_seconds() * 1000),
                    )

                return HookResult(
                    hook_name=self.name,
                    success=True,
                    message="proceed",
                    duration_ms=int((datetime.now() - start).total_seconds() * 1000),
                )
            else:
                return HookResult(
                    hook_name=self.name,
                    success=True,
                    message="proceed",
                    duration_ms=int((datetime.now() - start).total_seconds() * 1000),
                )
        except Exception as e:
            logger.error(f"BeforeTool hook failed: {e}")
            return HookResult(
                hook_name=self.name,
                success=False,
                error=str(e),
                duration_ms=int((datetime.now() - start).total_seconds() * 1000),
            )


class AfterToolHook(Hook):
    """工具执行后执行"""

    def __init__(self, callback: Callable | str | None = None):
        super().__init__("AfterTool", callback)


class StopHook(Hook):
    """停止时执行"""

    def __init__(self, callback: Callable | str | None = None):
        super().__init__("Stop", callback)


class HookManager:
    """Hook 管理器"""

    def __init__(self):
        self._hooks: dict[str, list[Hook]] = {
            "SessionStart": [],
            "BeforeTool": [],
            "AfterTool": [],
            "Stop": [],
        }
        self._config = HookConfig()

    @property
    def config(self) -> HookConfig:
        return self._config

    def register(self, hook: Hook) -> None:
        """注册钩子"""
        if hook.name in self._hooks:
            self._hooks[hook.name].append(hook)
            logger.info(f"Registered hook: {hook.name}")
        else:
            logger.warning(f"Unknown hook type: {hook.name}")

    def unregister(self, hook_name: str, callback: Any = None) -> None:
        """注销钩子"""
        if hook_name not in self._hooks:
            return

        if callback is None:
            self._hooks[hook_name].clear()
        else:
            self._hooks[hook_name] = [
                h for h in self._hooks[hook_name] if h.callback != callback
            ]

    def get_hooks(self, hook_name: str) -> list[Hook]:
        """获取指定类型的钩子"""
        return self._hooks.get(hook_name, [])

    async def execute_session_start(self, context: dict) -> list[HookResult]:
        """执行会话开始钩子"""
        results = []
        for hook in self._hooks.get("SessionStart", []):
            result = await hook.execute(context)
            results.append(result)
        return results

    async def execute_before_tool(
        self, tool_name: str, tool_args: dict
    ) -> tuple[list[HookResult], bool]:
        """
        执行工具前钩子
        返回 (results, should_proceed)
        """
        results = []
        should_proceed = True

        context = {
            "tool_name": tool_name,
            "tool_args": tool_args,
            "timestamp": datetime.now().isoformat(),
        }

        for hook in self._hooks.get("BeforeTool", []):
            result = await hook.execute(context)
            results.append(result)
            if not result.success:
                should_proceed = False

        return results, should_proceed

    async def execute_after_tool(
        self, tool_name: str, tool_args: dict, tool_result: Any
    ) -> list[HookResult]:
        """执行工具后钩子"""
        results = []

        context = {
            "tool_name": tool_name,
            "tool_args": tool_args,
            "tool_result": tool_result,
            "timestamp": datetime.now().isoformat(),
        }

        for hook in self._hooks.get("AfterTool", []):
            result = await hook.execute(context)
            results.append(result)
        return results

    async def execute_stop(self, context: dict) -> list[HookResult]:
        """执行停止钩子"""
        results = []
        for hook in self._hooks.get("Stop", []):
            result = await hook.execute(context)
            results.append(result)
        return results

    def load_from_file(self, file_path: str | Path) -> None:
        """从配置文件加载钩子"""
        import json

        file_path = Path(file_path)
        if not file_path.exists():
            return

        try:
            with open(file_path, encoding="utf-8") as f:
                config = json.load(f)

            hooks_config = config.get("hooks", {})
            for hook_type, hooks in hooks_config.items():
                for hook_config in hooks:
                    callback = hook_config.get("callback")
                    hook = None

                    if hook_type == "SessionStart":
                        hook = SessionStartHook(callback)
                    elif hook_type == "BeforeTool":
                        hook = BeforeToolHook(callback)
                    elif hook_type == "AfterTool":
                        hook = AfterToolHook(callback)
                    elif hook_type == "Stop":
                        hook = StopHook(callback)

                    if hook:
                        hook.enabled = hook_config.get("enabled", True)
                        self.register(hook)

            logger.info(f"Loaded hooks from {file_path}")
        except Exception as e:
            logger.error(f"Failed to load hooks from {file_path}: {e}")


# 全局单例
_hook_manager: HookManager | None = None


def get_hook_manager() -> HookManager:
    """获取 Hook 管理器单例"""
    global _hook_manager
    if _hook_manager is None:
        _hook_manager = HookManager()
    return _hook_manager


def reset_hook_manager() -> None:
    """重置 Hook 管理器"""
    global _hook_manager
    _hook_manager = None
