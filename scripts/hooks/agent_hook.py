"""
AgentHook - Agent 验证器 Hook
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .enhanced import Hook, HookResult

logger = logging.getLogger(__name__)


@dataclass
class VerificationTask:
    task_id: str
    task_type: str
    prompt: str
    tools: list[str] | None = None
    timeout_seconds: int = 60
    result: Any = None
    completed: bool = False


class AgentHook(Hook):
    """Agent 验证器 Hook"""

    def __init__(
        self,
        callback: Callable | str | None = None,
        agent_provider: Any = None,
        task_type: str = "general",
        default_tools: list[str] | None = None,
        timeout_seconds: int = 60,
    ):
        super().__init__("PostToolUse", callback)
        self.agent_provider = agent_provider
        self.task_type = task_type
        self.default_tools = default_tools or ["Read", "Glob", "Grep", "Bash"]
        self.timeout_seconds = timeout_seconds
        self._verification_tasks: dict[str, VerificationTask] = {}

    async def execute(self, context: dict) -> HookResult:
        if not self._enabled:
            return HookResult(hook_name=self.name, success=True, message="disabled")

        tool_name = context.get("tool_name", "")
        tool_args = context.get("tool_args", {})
        tool_result = context.get("tool_result")

        import time
        start = time.time()

        try:
            if not self._should_verify(tool_name, tool_args):
                return HookResult(hook_name=self.name, success=True, message="no verification needed")

            task = await self._create_verification_task(context)
            if not task:
                return HookResult(hook_name=self.name, success=True, message="verification not applicable")

            result = await self._execute_verification(task)

            duration_ms = int((time.time() - start) * 1000)

            if result.get("passed", False):
                return HookResult(
                    hook_name=self.name,
                    success=True,
                    message=result.get("message", "verification passed"),
                    duration_ms=duration_ms,
                )
            else:
                return HookResult(
                    hook_name=self.name,
                    success=False,
                    error=result.get("error", "verification failed"),
                    duration_ms=duration_ms,
                )

        except Exception as e:
            logger.error(f"AgentHook verification failed: {e}")
            duration_ms = int((time.time() - start) * 1000)
            return HookResult(hook_name=self.name, success=False, error=str(e), duration_ms=duration_ms)

    def _should_verify(self, tool_name: str, tool_args: dict) -> bool:
        verify_extensions = {".py", ".js", ".ts", ".go", ".rs", ".java"}

        path = tool_args.get("file_path") or tool_args.get("path") or ""
        if path:
            ext = path.split(".")[-1] if "." in path else ""
            if f".{ext}" in verify_extensions:
                return True

        high_risk_tools = {"Bash", "Write", "Edit", "BashTool"}
        if tool_name in high_risk_tools:
            command = tool_args.get("command", "") or tool_args.get("text", "")
            danger_patterns = ["rm ", "delete", "DROP", "truncate", "sudo"]
            return any(p.lower() in command.lower() for p in danger_patterns)

        return False

    async def _create_verification_task(self, context: dict) -> VerificationTask | None:
        tool_name = context.get("tool_name", "")
        tool_args = context.get("tool_args", {})

        task_id = f"verify_{tool_name}_{int(datetime.now().timestamp())}"
        prompt = self._build_verification_prompt(tool_name, tool_args, context)

        return VerificationTask(
            task_id=task_id,
            task_type=self.task_type,
            prompt=prompt,
            tools=self.default_tools,
            timeout_seconds=self.timeout_seconds,
        )

    def _build_verification_prompt(self, tool_name: str, tool_args: dict, context: dict) -> str:
        base_instruction = (
            self.callback if isinstance(self.callback, str)
            else f"Verify the {tool_name} operation is safe and correct"
        )

        return f"""{base_instruction}

Operation: {tool_name}
Arguments: {tool_args}

Context:
- Session: {context.get('session_id', 'unknown')}
- Tool Result: {context.get('tool_result', 'N/A')}

Please verify:
1. Is this operation safe?
2. Are there any potential issues?
3. Should this operation proceed?

Return JSON:
{{
    "passed": true/false,
    "message": "verification message",
    "issues": ["issue list if any"]
}}
"""

    async def _execute_verification(self, task: VerificationTask) -> dict:
        if not self.agent_provider:
            logger.warning("No agent provider configured for AgentHook")
            return {"passed": True, "message": "no agent provider, skipped"}

        try:
            agent = await self.agent_provider(
                task_type=self.task_type,
                prompt=task.prompt,
                tools=task.tools,
            )

            result = await asyncio.wait_for(
                agent.run(),
                timeout=task.timeout_seconds,
            )

            return self._parse_verification_result(result)

        except asyncio.TimeoutError:
            return {"passed": False, "error": f"Verification timeout after {task.timeout_seconds}s"}
        except Exception as e:
            return {"passed": False, "error": f"Verification error: {str(e)}"}

    def _parse_verification_result(self, result: Any) -> dict:
        import json

        if isinstance(result, str):
            try:
                for line in result.split("\n"):
                    if line.strip().startswith("{"):
                        data = json.loads(line)
                        return {
                            "passed": data.get("passed", True),
                            "message": data.get("message", ""),
                            "issues": data.get("issues", []),
                        }
            except json.JSONDecodeError:
                pass

        if isinstance(result, dict):
            return {
                "passed": result.get("passed", True),
                "message": result.get("message", ""),
                "issues": result.get("issues", []),
            }

        return {"passed": True, "message": str(result)[:200]}


class SecurityVerificationHook(AgentHook):
    """安全验证 Hook"""

    def __init__(self, agent_provider: Any = None):
        super().__init__(
            callback="Perform security verification",
            agent_provider=agent_provider,
            task_type="security",
            default_tools=["Read", "Grep", "Glob"],
            timeout_seconds=120,
        )

    def _should_verify(self, tool_name: str, tool_args: dict) -> bool:
        write_tools = {"Write", "Edit", "Bash", "WriteTool", "EditTool"}
        if tool_name in write_tools:
            return True
        if tool_name in {"Bash", "BashTool"}:
            return True
        return False
