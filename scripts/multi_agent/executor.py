"""
Executor - 执行Agent

L2Executor: L2 执行Agent（在约束内执行任务）
L3Executor: L3 执行Agent（支持跨子域依赖等待）

待增强功能：
- 并行执行引擎：按依赖关系分组，同组内并行执行
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .constraints import Constraint, ConstraintType
from .models import SubdomainResult, Task, TaskStatus

logger = logging.getLogger(__name__)


class TaskResult:
    """任务执行结果"""

    def __init__(
        self,
        task_id: str,
        status: str,
        result: Any = None,
        error: str | None = None,
        token_count: int = 0,
        summary: str = "",
    ):
        self.task_id = task_id
        self.status = status
        self.result = result
        self.error = error
        self.token_count = token_count
        self.summary = summary


class L2Executor:
    """
    L2 执行Agent: 在约束内执行

    负责：
    1. 确认前置依赖满足
    2. 准备回滚
    3. 执行任务
    4. 验证结果
    5. 失败时回滚
    6. 并行执行：按依赖关系分组，同组内并行执行
    """

    def __init__(
        self,
        llm_client: Any = None,
        tools: list[Any] | None = None,
    ):
        """
        初始化 L2 执行器

        Args:
            llm_client: LLM 客户端
            tools: 可用的工具列表
        """
        self.llm_client = llm_client
        self.tools = tools or []

    async def execute(self, task: Task) -> TaskResult:
        """
        执行单个任务

        Args:
            task: 任务

        Returns:
            TaskResult: 执行结果
        """
        try:
            # 1. 确认前置依赖满足
            if not self._wait_for_dependencies(task):
                return TaskResult(
                    task_id=task.id,
                    status="failed",
                    error="前置依赖未满足"
                )

            # 2. 准备回滚
            await self._prepare_rollback(task)

            # 3. 执行
            result = await self._do_execute(task)

            # 4. 验证
            if not await self._verify(result, task):
                await self._rollback(task)
                return TaskResult(
                    task_id=task.id,
                    status="failed",
                    error="验证失败"
                )

            return TaskResult(
                task_id=task.id,
                status="completed",
                result=result,
                summary=f"任务 {task.id} 执行完成"
            )

        except Exception as e:
            logger.error(f"任务 {task.id} 执行失败: {e}")
            await self._rollback(task)
            return TaskResult(
                task_id=task.id,
                status="failed",
                error=str(e)
            )

    async def execute_parallel(self, tasks: list[Task]) -> list[TaskResult]:
        """
        并行执行多个任务

        按依赖关系分组，同组内并行执行，不同组按依赖顺序执行。

        Args:
            tasks: 任务列表

        Returns:
            List[TaskResult]: 所有任务的执行结果
        """
        # 按依赖关系分组
        batches = self._group_by_dependencies(tasks)
        logger.info(f"任务分组: {len(batches)} 批")

        all_results = []
        for i, batch in enumerate(batches):
            logger.info(f"执行批次 {i + 1}/{len(batches)}: {len(batch)} 个任务")

            # 同批次并行执行
            results = await asyncio.gather(*[
                self.execute(task) for task in batch
            ])
            all_results.extend(results)

            # 检查是否有失败
            failed_tasks = [r for r in results if r.status == "failed"]
            if failed_tasks:
                logger.warning(f"批次 {i + 1} 中有 {len(failed_tasks)} 个任务失败")
                # 依赖失败，后续批次取消执行
                # 为未执行任务生成失败结果
                remaining_batches = batches[i + 1:]
                for remaining_batch in remaining_batches:
                    for task in remaining_batch:
                        all_results.append(TaskResult(
                            task_id=task.id,
                            status="cancelled",
                            error="前置任务失败导致取消"
                        ))
                break

        return all_results

    def _group_by_dependencies(self, tasks: list[Task]) -> list[list[Task]]:
        """
        按依赖关系分组，同一组可并行执行

        使用拓扑排序的逆序来分组：
        - 没有任何依赖的任务可以并行
        - 依赖已完成任务的任务在下一批次执行

        Args:
            tasks: 任务列表

        Returns:
            List[List[Task]]: 分组后的任务列表
        """
        batches = []
        remaining = tasks.copy()
        completed = set()

        while remaining:
            # 找所有依赖都已完成的任务
            ready = [
                t for t in remaining
                if all(dep in completed for dep in t.dependencies)
            ]

            if not ready:
                # 死锁或循环依赖，按原顺序将剩余任务作为最后一组
                if remaining:
                    batches.append(remaining)
                break

            batches.append(ready)
            for t in ready:
                completed.add(t.id)
                remaining.remove(t)

        return batches

    def _wait_for_dependencies(self, task: Task) -> bool:
        """
        等待前置依赖完成

        Args:
            task: 任务

        Returns:
            bool: 依赖是否满足
        """
        # 简单的实现：检查是否有 depends_on 约束
        for constraint in task.constraints:
            if constraint.type == ConstraintType.DEPENDS_ON:
                # 需要等待其他任务完成
                # 在实际实现中，这应该检查任务状态存储
                pass

        return True  # 默认认为依赖满足

    async def _prepare_rollback(self, task: Task) -> None:
        """
        准备回滚

        Args:
            task: 任务
        """
        # 如果任务没有回滚计划，创建一个
        if not task.rollback_plan and task.has_rollback_plan:
            task.rollback_plan = {
                "method": "git_branch",
                "backup_branch": f"backup_{task.id}",
            }

    async def _do_execute(self, task: Task) -> Any:
        """
        执行任务

        Args:
            task: 任务

        Returns:
            Any: 执行结果
        """
        # 如果配置了 LLM 客户端，使用 LLM 执行
        if self.llm_client:
            return await self._llm_execute(task)

        # 否则返回简单的成功结果
        return {"status": "completed", "task_id": task.id}

    async def _llm_execute(self, task: Task) -> Any:
        """
        使用 LLM 执行任务

        Args:
            task: 任务

        Returns:
            Any: 执行结果
        """
        prompt = self._build_execute_prompt(task)

        try:
            response = await self.llm_client.complete(prompt)
            return {"status": "completed", "task_id": task.id, "response": response}
        except Exception as e:
            raise RuntimeError(f"LLM 执行失败: {e}")

    def _build_execute_prompt(self, task: Task) -> str:
        """
        构建执行提示

        Args:
            task: 任务

        Returns:
            str: 提示文本
        """
        constraints_text = self._format_constraints(task.constraints)

        return f"""你是一个L2执行Agent。严格按照计划执行任务。

## 你的约束（必须遵守）

{constraints_text}

## 你的任务
{task.description}

开始执行。
"""

    def _format_constraints(self, constraints: list[Constraint]) -> str:
        """
        格式化约束

        Args:
            constraints: 约束列表

        Returns:
            str: 格式化的约束文本
        """
        parts = []

        for constraint in constraints:
            if constraint.type == ConstraintType.FILE_SCOPE:
                files = ", ".join(constraint.files or [])
                parts.append(f"### 文件边界\n{files}\n- 只能修改上述文件\n- 不得修改任何其他文件")

            elif constraint.type == ConstraintType.DEPENDS_ON:
                tasks = ", ".join(constraint.tasks or [])
                parts.append(f"### 依赖约束\n{tasks}\n- 必须等待前置任务完成才能开始")

            elif constraint.type == ConstraintType.ROLLBACK_REQUIRED:
                rollback_text = (
                    "### 回滚约束\n"
                    "- 每个变更前必须创建backup/checkpoint\n"
                    "- 变更后必须验证\n"
                    "- 失败时立即回滚"
                )
                parts.append(rollback_text)

            elif constraint.type == ConstraintType.FORBIDDEN:
                actions = ", ".join(constraint.actions or [])
                parts.append(f"### 禁止操作\n{actions}\n- 绝对禁止执行上述操作")

        return "\n\n".join(parts)

    async def _verify(self, result: Any, task: Task) -> bool:
        """
        验证结果

        Args:
            result: 执行结果
            task: 任务

        Returns:
            bool: 验证是否通过
        """
        # 简单的验证：检查结果是否非空
        return result is not None

    async def _rollback(self, task: Task) -> None:
        """
        回滚

        Args:
            task: 任务
        """
        if task.rollback_plan:
            logger.info(f"回滚任务 {task.id}: {task.rollback_plan}")
            # 实际实现中应该执行 git checkout 或其他回滚操作


class L3Executor(L2Executor):
    """
    L3 执行Agent: 在约束内执行，支持跨子域依赖等待

    继承自 L2Executor，额外支持：
    1. 等待其他子域的输出
    2. 子域级约束
    """

    def __init__(
        self,
        llm_client: Any = None,
        tools: list[Any] | None = None,
    ):
        """
        初始化 L3 执行器

        Args:
            llm_client: LLM 客户端
            tools: 可用的工具列表
        """
        L2Executor.__init__(self, llm_client, tools)
        self.subdomain_outputs: dict[str, Any] = {}

    def register_subdomain_output(self, subdomain_id: str, output: Any) -> None:
        """
        注册子域输出

        Args:
            subdomain_id: 子域ID
            output: 输出内容
        """
        self.subdomain_outputs[subdomain_id] = output

    def _wait_for_dependencies(self, task: Task) -> bool:
        """
        等待前置依赖完成（包含跨子域依赖）

        Args:
            task: 任务

        Returns:
            bool: 依赖是否满足
        """
        # 检查普通依赖
        if not super()._wait_for_dependencies(task):
            return False

        # 检查跨子域依赖
        for constraint in task.constraints:
            if constraint.type == ConstraintType.WAIT_FOR_EXTERNAL:
                if not self._is_subdomain_output_ready(constraint.source):
                    # 需要等待子域输出
                    return False

        return True

    def _is_subdomain_output_ready(self, source: str) -> bool:
        """
        检查子域输出是否就绪

        Args:
            source: 子域源标识

        Returns:
            bool: 输出是否就绪
        """
        if source.startswith("subdomain:"):
            subdomain_id = source.split(":", 1)[1]
            return subdomain_id in self.subdomain_outputs
        return True

    async def _wait_for_subdomain_output(self, constraint: Constraint) -> Any:
        """
        等待子域输出

        Args:
            constraint: 约束

        Returns:
            Any: 子域输出
        """
        source = constraint.source
        if source.startswith("subdomain:"):
            subdomain_id = source.split(":", 1)[1]

            # 轮询等待子域输出
            max_attempts = 60
            for _ in range(max_attempts):
                if subdomain_id in self.subdomain_outputs:
                    return self.subdomain_outputs[subdomain_id]
                await asyncio.sleep(1)

        return None

    async def execute_subdomain_parallel(
        self,
        subdomain_plan: Any,
        tasks: list[Task],
    ) -> SubdomainResult:
        """
        并行执行子域内的任务

        Args:
            subdomain_plan: 子域计划
            tasks: 任务列表

        Returns:
            SubdomainResult: 子域结果
        """
        results = await self.execute_parallel(tasks)

        completed_tasks = []
        failed_tasks = []
        for task, result in zip(tasks, results):
            if result.status == "completed":
                completed_tasks.append(task)
            else:
                failed_tasks.append(task)

        has_failures = len(failed_tasks) > 0

        return SubdomainResult(
            subdomain_id=subdomain_plan.subdomain_id,
            status=TaskStatus.FAILED if has_failures else TaskStatus.COMPLETED,
            completed=not has_failures,
            has_rollback_capability=True,
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            issues=[],
        )
