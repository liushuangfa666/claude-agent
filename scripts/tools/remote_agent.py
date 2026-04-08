"""
RemoteAgentTask Tool - 使用多Agent系统执行远程任务

使用 multi_agent 系统的 L2/L3 架构来执行复杂任务：
- L2: Decomposer 分解 + Executor 执行 + Reviewer 审核
- L3: 多子域并行执行 + 跨域协调

引用文档：docs/MULTI_AGENT_DESIGN.md
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from scripts.multi_agent.models import (
    ComplexityLevel,
    Constraint,
    ConstraintType,
    TaskStatus,
)
from scripts.multi_agent.models import Task as MultiAgentTask
from scripts.multi_agent.executor import L2Executor, L3Executor
from scripts.multi_agent.decomposer import L2Decomposer, L3TopDecomposer
from scripts.multi_agent.reviewer import L2Reviewer
from scripts.multi_agent.session import MultiAgentSessionManager, LayerSession

try:
    from scripts.tool import BaseTool, ToolResult
except ImportError:
    from tool import BaseTool, ToolResult


logger = logging.getLogger(__name__)


@dataclass
class RemoteTaskConfig:
    """远程任务配置"""
    task_id: str
    description: str
    complexity: ComplexityLevel = ComplexityLevel.L1
    max_tokens: int = 8000
    timeout_seconds: int = 300
    allowed_tools: list[str] | None = None
    constraints: list[Constraint] = field(default_factory=list)
    subdomains: list[dict] = field(default_factory=list)  # L3 子域配置


class RemoteAgentTaskTool(BaseTool):
    """
    RemoteAgentTask 工具 - 使用多Agent系统执行远程任务

    根据任务复杂度自动选择执行层级：
    - L1: 单Agent直接执行（简单任务）
    - L2: Decomposer + Executor + Reviewer（中等复杂度）
    - L3: 多子域并行 + 跨域协调（复杂任务）
    """

    name = "RemoteAgentTask"
    description = """使用多Agent系统执行远程任务，支持复杂任务分解和并行执行。

根据任务复杂度自动选择执行层级：
- L1: 单Agent直接执行（简单任务）
- L2: Decomposer + Executor + Reviewer（中等复杂度）
- L3: 多子域并行执行（复杂任务）

适用于：
- 需要多步骤执行的任务
- 需要并行处理的子任务
- 需要审核验证的任务
- 跨域依赖的任务"""

    input_schema = {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "要执行的任务描述"
            },
            "complexity": {
                "type": "string",
                "enum": ["L1", "L2", "L3"],
                "description": "任务复杂度级别，默认自动检测",
                "default": "auto"
            },
            "subdomains": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "tasks": {"type": "array", "items": {"type": "string"}},
                        "depends_on": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "description": "L3子域配置列表"
            },
            "max_tokens": {
                "type": "integer",
                "description": "最大token数，默认8000",
                "default": 8000
            },
            "timeout": {
                "type": "integer",
                "description": "超时秒数，默认300",
                "default": 300
            }
        },
        "required": ["task"]
    }

    def __init__(self):
        super().__init__()
        self._session_manager = MultiAgentSessionManager()
        self._l2_executor = L2Executor()
        self._l3_executor = L3Executor()
        self._l2_decomposer = L2Decomposer()
        self._l2_reviewer = L2Reviewer()
        self._l3_decomposer = L3TopDecomposer()

    async def call(self, args: dict, context: dict) -> ToolResult:
        """执行远程任务"""
        task_description = args.get("task", "")
        complexity_str = args.get("complexity", "auto")
        subdomains_config = args.get("subdomains", [])
        max_tokens = args.get("max_tokens", 8000)
        timeout = args.get("timeout", 300)

        # 解析复杂度级别
        if complexity_str == "auto":
            complexity = self._detect_complexity(task_description, subdomains_config)
        else:
            complexity = ComplexityLevel(complexity_str)

        task_id = f"remote_task_{uuid.uuid4().hex[:8]}"

        try:
            if complexity == ComplexityLevel.L1:
                result = await self._execute_l1(task_id, task_description, context)
            elif complexity == ComplexityLevel.L2:
                result = await self._execute_l2(task_id, task_description, context, max_tokens)
            else:  # L3
                result = await self._execute_l3(
                    task_id, task_description, context, subdomains_config, max_tokens
                )

            return ToolResult(success=True, data=result)

        except Exception as e:
            logger.error(f"RemoteAgentTask 执行失败: {e}")
            return ToolResult(success=False, data=None, error=str(e))

    def _detect_complexity(
        self,
        task_description: str,
        subdomains_config: list[dict]
    ) -> ComplexityLevel:
        """自动检测任务复杂度"""
        # 有子域配置肯定是 L3
        if subdomains_config:
            return ComplexityLevel.L3

        # 复杂关键词检测
        complex_keywords = [
            "多个", "并行", "分布式", "微服务", "重构",
            "测试", "审核", "验证", "跨域", "集成",
            "同时", "分别", "各自", "组合"
        ]

        has_complex_keyword = any(kw in task_description for kw in complex_keywords)

        # 任务长度超过阈值认为是中等复杂度
        if len(task_description) > 500 or has_complex_keyword:
            return ComplexityLevel.L2

        return ComplexityLevel.L1

    async def _execute_l1(
        self,
        task_id: str,
        task_description: str,
        context: dict
    ) -> dict[str, Any]:
        """L1 执行：单Agent直接执行"""
        logger.info(f"[{task_id}] L1 执行模式")

        # 创建简单的任务
        task = MultiAgentTask(
            id=task_id,
            description=task_description,
            status=TaskStatus.IN_PROGRESS
        )

        # 使用 L2Executor 执行（它支持 L1）
        result = await self._l2_executor.execute(task)

        return {
            "task_id": task_id,
            "level": "L1",
            "status": result.status,
            "result": result.result,
            "summary": result.summary,
            "error": result.error
        }

    async def _execute_l2(
        self,
        task_id: str,
        task_description: str,
        context: dict,
        max_tokens: int
    ) -> dict[str, Any]:
        """L2 执行：Decomposer + Executor + Reviewer"""
        logger.info(f"[{task_id}] L2 执行模式")

        # 创建任务对象
        main_task = MultiAgentTask(
            id=task_id,
            description=task_description,
            status=TaskStatus.PENDING
        )

        # 1. Decomposer 分解任务
        decomposed = await self._l2_decomposer.decompose(main_task)

        if not decomposed or not decomposed.tasks:
            return {
                "task_id": task_id,
                "level": "L2",
                "status": "failed",
                "error": "任务分解失败"
            }

        # 2. 创建任务列表
        tasks = decomposed.tasks

        # 3. Executor 并行执行
        results = await self._l2_executor.execute_parallel(tasks)

        # 4. Reviewer 审核
        review_result = await self._l2_reviewer.approve(decomposed)

        completed_count = sum(1 for r in results if r.status == "completed")
        failed_count = sum(1 for r in results if r.status == "failed")

        return {
            "task_id": task_id,
            "level": "L2",
            "status": "completed" if review_result.approved else "needs_revision",
            "tasks_count": len(tasks),
            "completed_count": completed_count,
            "failed_count": failed_count,
            "review": {
                "approved": review_result.approved,
                "issues": [i.to_dict() for i in review_result.issues]
            },
            "results": [
                {
                    "task_id": r.task_id,
                    "status": r.status,
                    "result": r.result,
                    "error": r.error
                }
                for r in results
            ]
        }

    async def _execute_l3(
        self,
        task_id: str,
        task_description: str,
        context: dict,
        subdomains_config: list[dict],
        max_tokens: int
    ) -> dict[str, Any]:
        """L3 执行：多子域并行 + 跨域协调"""
        logger.info(f"[{task_id}] L3 执行模式")

        # 创建主任务
        main_task = MultiAgentTask(
            id=task_id,
            description=task_description,
            status=TaskStatus.PENDING
        )

        # 1. 使用 L3 Decomposer
        l3_plan = await self._l3_decomposer.decompose(main_task)

        if not l3_plan or not l3_plan.subdomains:
            return {
                "task_id": task_id,
                "level": "L3",
                "status": "failed",
                "error": "L3 计划生成失败"
            }

        # 2. 并行执行各子域
        subdomain_results = []
        for subdomain_plan in l3_plan.subdomains:
            subdomain_id = subdomain_plan.subdomain_id

            # 子域内并行执行
            results = await self._l3_executor.execute_parallel(subdomain_plan.tasks)

            completed = sum(1 for r in results if r.status == "completed")
            failed = sum(1 for r in results if r.status == "failed")

            subdomain_results.append({
                "subdomain_id": subdomain_id,
                "status": "completed" if failed == 0 else "partial",
                "tasks_count": len(subdomain_plan.tasks),
                "completed_count": completed,
                "failed_count": failed
            })

        # 3. 跨域结果汇总
        total_completed = sum(r["completed_count"] for r in subdomain_results)
        total_failed = sum(r["failed_count"] for r in subdomain_results)

        return {
            "task_id": task_id,
            "level": "L3",
            "status": "completed" if total_failed == 0 else "partial",
            "subdomains": subdomain_results,
            "summary": {
                "total_completed": total_completed,
                "total_failed": total_failed
            }
        }


class RemoteAgentTaskRegistry:
    """远程任务注册表"""

    def __init__(self):
        self._tasks: dict[str, dict] = {}
        self._results: dict[str, Any] = {}

    def register(self, task_id: str, config: RemoteTaskConfig) -> None:
        self._tasks[task_id] = {
            "config": config,
            "status": "pending",
            "created_at": datetime.now()
        }

    def update_status(self, task_id: str, status: str, result: Any = None) -> None:
        if task_id in self._tasks:
            self._tasks[task_id]["status"] = status
            self._tasks[task_id]["updated_at"] = datetime.now()
            if result:
                self._results[task_id] = result

    def get_status(self, task_id: str) -> dict | None:
        return self._tasks.get(task_id)

    def get_result(self, task_id: str) -> Any:
        return self._results.get(task_id)

    def list_tasks(self, status: str | None = None) -> list[dict]:
        if status:
            return [t for t in self._tasks.values() if t["status"] == status]
        return list(self._tasks.values())


# 全局注册表
_remote_task_registry = RemoteAgentTaskRegistry()


def get_remote_task_registry() -> RemoteAgentTaskRegistry:
    return _remote_task_registry


# 注册工具
def register_remote_agent_tools():
    """注册远程任务工具"""
    from scripts.tool import get_registry
    get_registry().register(RemoteAgentTaskTool())


# 延迟注册，等待 multi_agent 模块加载完成
import atexit
atexit.register(register_remote_agent_tools)
