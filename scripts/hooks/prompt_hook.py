"""
PromptHook - LLM 评估 Hook
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .enhanced import Hook, HookResult

logger = logging.getLogger(__name__)


@dataclass
class PromptEvaluation:
    approved: bool = True
    modified_input: str | None = None
    reason: str = ""
    suggestions: list[str] | None = None


class PromptHook(Hook):
    """Prompt Hook - 使用 LLM 评估用户输入"""

    def __init__(
        self,
        callback: Callable | str | None = None,
        llm_provider: Any = None,
        model: str = "gpt-4",
        temperature: float = 0.0,
    ):
        super().__init__("UserPromptSubmit", callback)
        self.llm_provider = llm_provider
        self.model = model
        self.temperature = temperature

    async def execute(self, context: dict) -> HookResult:
        if not self._enabled:
            return HookResult(hook_name=self.name, success=True, message="disabled")

        user_input = context.get("user_input", "")
        session_id = context.get("session_id", "default")

        try:
            if self.llm_provider:
                evaluation = await self._evaluate_with_llm(user_input, context)
                if not evaluation.approved:
                    return HookResult(
                        hook_name=self.name,
                        success=False,
                        error=f"Prompt rejected: {evaluation.reason}",
                        modified_context={"user_input": evaluation.modified_input},
                    )

                if evaluation.modified_input:
                    context["user_input"] = evaluation.modified_input
                    return HookResult(
                        hook_name=self.name,
                        success=True,
                        message=f"Modified: {evaluation.reason}",
                        modified_context={"user_input": evaluation.modified_input},
                    )

            if callable(self.callback):
                result = self.callback(context)
                import asyncio
                if asyncio.iscoroutine(result):
                    result = await result
                return HookResult(
                    hook_name=self.name,
                    success=True,
                    message=str(result) if result else "approved",
                )

            return HookResult(hook_name=self.name, success=True, message="approved")

        except Exception as e:
            logger.error(f"PromptHook evaluation failed: {e}")
            return HookResult(hook_name=self.name, success=False, error=str(e))

    async def _evaluate_with_llm(self, user_input: str, context: dict) -> PromptEvaluation:
        """使用 LLM 评估用户输入"""
        prompt = self._build_evaluation_prompt(user_input, context)

        try:
            response = await self.llm_provider.complete(
                prompt=prompt,
                model=self.model,
                temperature=self.temperature,
            )
            return self._parse_evaluation_response(response)
        except Exception as e:
            logger.error(f"LLM evaluation failed: {e}")
            return PromptEvaluation(approved=True, reason="LLM evaluation failed, defaulting to allow")

    def _build_evaluation_prompt(self, user_input: str, context: dict) -> str:
        instruction = self.callback or "评估用户输入是否安全、合适"
        return f"""{instruction}

用户输入: {user_input}

会话上下文:
- session_id: {context.get('session_id', 'unknown')}
- timestamp: {context.get('timestamp', 'unknown')}
- tool_history: {context.get('tool_history', [])}

请评估并返回 JSON 格式:
{{
    "approved": true/false,
    "reason": "评估理由",
    "modified_input": "修改后的输入(可选)",
    "suggestions": ["建议列表(可选)"]
}}
"""

    def _parse_evaluation_response(self, response: str) -> PromptEvaluation:
        try:
            for line in response.split("\n"):
                line = line.strip()
                if line.startswith("{") or line.startswith("```json"):
                    if line.startswith("```"):
                        line = line[7:]
                    try:
                        data = json.loads(line.strip("`"))
                        return PromptEvaluation(
                            approved=data.get("approved", True),
                            modified_input=data.get("modified_input"),
                            reason=data.get("reason", ""),
                            suggestions=data.get("suggestions"),
                        )
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

        return PromptEvaluation(approved=True, reason="Could not parse LLM response")


class BlockedPromptError(Exception):
    def __init__(self, reason: str, suggestions: list[str] | None = None):
        self.reason = reason
        self.suggestions = suggestions or []
        super().__init__(reason)
