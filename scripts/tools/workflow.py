"""
WorkflowTool - 工作流编排工具

支持复杂工作流的执行，包括：
- 多步骤执行
- 条件判断
- 失败重试
- 步骤结果传递
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tool import BaseTool, ToolResult


@dataclass
class WorkflowStep:
    """工作流步骤定义"""
    name: str
    tool: str
    args: dict
    condition: str | None = None
    retry: int = 0


@dataclass
class WorkflowDefinition:
    """工作流定义"""
    name: str
    description: str
    steps: list[WorkflowStep] = field(default_factory=list)
    retry: int = 0
    continue_on_error: bool = False


class WorkflowTool(BaseTool):
    """工作流编排工具"""

    name = "Workflow"
    description = "Execute complex workflows with multiple steps, conditions, and retries"

    input_schema = {
        "type": "object",
        "properties": {
            "workflow": {
                "type": "object",
                "description": "Workflow definition",
                "properties": {
                    "name": {"type": "string", "description": "Workflow name"},
                    "description": {"type": "string", "description": "Workflow description"},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "tool": {"type": "string"},
                                "args": {"type": "object"},
                                "condition": {"type": "string"},
                                "retry": {"type": "integer", "default": 0},
                            },
                            "required": ["name", "tool", "args"],
                        },
                    },
                    "retry": {"type": "number", "default": 0},
                    "continue_on_error": {"type": "boolean", "default": False},
                },
                "required": ["name", "steps"],
            },
        },
        "required": ["workflow"],
    }

    async def call(self, args: dict, context: Any) -> ToolResult:
        workflow_def = args["workflow"]

        steps = []
        for step_data in workflow_def.get("steps", []):
            steps.append(WorkflowStep(
                name=step_data["name"],
                tool=step_data["tool"],
                args=step_data.get("args", {}),
                condition=step_data.get("condition"),
                retry=step_data.get("retry", 0),
            ))

        workflow = WorkflowDefinition(
            name=workflow_def["name"],
            description=workflow_def.get("description", ""),
            steps=steps,
            retry=workflow_def.get("retry", 0),
            continue_on_error=workflow_def.get("continue_on_error", False),
        )

        results = []
        step_results = {}

        for step in workflow.steps:
            if step.condition:
                if not self._evaluate_condition(step.condition, step_results):
                    results.append({
                        "step": step.name,
                        "tool": step.tool,
                        "skipped": True,
                        "condition": step.condition,
                    })
                    continue

            tool = self._get_tool(step.tool, context)
            if not tool:
                return ToolResult(
                    success=False,
                    data={"steps": results},
                    error=f"Tool not found: {step.tool}",
                )

            retry_count = 0
            step_result = None
            max_retries = max(step.retry, workflow.retry)

            while retry_count <= max_retries:
                try:
                    resolved_args = self._resolve_variables(step.args, step_results)
                    step_result = await tool.call(resolved_args, context)

                    if step_result.success:
                        break
                    elif retry_count < max_retries:
                        retry_count += 1
                        continue
                except Exception as e:
                    step_result = ToolResult(success=False, data=None, error=str(e))
                    if retry_count < max_retries:
                        retry_count += 1
                        continue

                retry_count += 1

            result_entry = {
                "step": step.name,
                "tool": step.tool,
                "success": step_result.success if step_result else False,
                "data": step_result.data if step_result else None,
                "error": step_result.error if step_result else "Unknown error",
            }
            results.append(result_entry)
            step_results[step.name] = step_result

            if step_result and not step_result.success and not workflow.continue_on_error:
                return ToolResult(
                    success=False,
                    data={"workflow": workflow.name, "steps": results},
                    error=f"Step {step.name} failed: {step_result.error}",
                )

        return ToolResult(
            success=True,
            data={
                "workflow": workflow.name,
                "description": workflow.description,
                "steps": results,
            },
        )

    def _get_tool(self, tool_name: str, context: Any) -> BaseTool | None:
        """从上下文或注册表获取工具"""
        tool_registry = getattr(context, "tool_registry", None)
        if tool_registry:
            return getattr(tool_registry, tool_name, None)

        try:
            from ..tools import get_tool_registry
            registry = get_tool_registry()
            return getattr(registry, tool_name, None)
        except ImportError:
            pass

        return None

    def _evaluate_condition(self, condition: str, results: dict) -> bool:
        """评估条件表达式"""
        if condition == "prev.success" and results:
            last_result = list(results.values())[-1]
            return last_result.success if last_result else False

        if ".success" in condition:
            parts = condition.split(".")
            if len(parts) == 2:
                step_name = parts[0]
                if step_name in results:
                    return results[step_name].success

        return True

    def _resolve_variables(self, args: dict, results: dict) -> dict:
        """解析变量引用"""
        resolved = {}
        for key, value in args.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                var_ref = value[2:-1]
                if var_ref == "prev":
                    last_result = list(results.values())[-1]
                    resolved[key] = last_result.data if last_result else None
                elif "." in var_ref:
                    parts = var_ref.split(".")
                    if parts[0] in results:
                        step_result = results[parts[0]]
                        data = step_result.data if step_result else None
                        for attr in parts[1:]:
                            if isinstance(data, dict):
                                data = data.get(attr)
                        resolved[key] = data
            else:
                resolved[key] = value
        return resolved
