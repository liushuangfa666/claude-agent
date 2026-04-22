"""
Multi-Agent 执行引擎 - 端到端执行流程

实现 L1/L2/L3 的完整执行流程。

待增强功能：
- 并行执行引擎：L2 按依赖分组并行，L3 子域并行
- 结果摘要压缩：多任务结果压缩为摘要
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from .decomposer import L2Decomposer, L3SubDecomposer, L3TopDecomposer
from .executor import L2Executor, L3Executor, TaskResult
from .models import (
    ExecutionResult,
    Issue,
    SubdomainPlan,
    SubdomainResult,
    Task,
    TaskStatus,
)
from .reviewer import L2Reviewer, L3Reviewer
from .router import ComplexityLevel, HybridRouter
from .session import MultiAgentSessionManager

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """流式事件 - 与 Agent.StreamEvent 兼容"""
    type: str = ""  # thinking | tool_start | tool_progress | tool_result | text | done
    content: str = ""
    tool: str = ""
    args: dict = field(default_factory=dict)
    success: bool = True
    data: Any = None
    recovered: bool = False
    warning: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None and v != "" and v != {}}


class MultiAgentExecutor:
    """
    多层Agent执行引擎

    根据复杂度级别自动选择 L1/L2/L3 执行架构。
    """

    def __init__(
        self,
        llm_client: Any | None = None,
        session_manager: MultiAgentSessionManager | None = None,
    ):
        """
        初始化执行引擎

        Args:
            llm_client: LLM 客户端
            session_manager: Session 管理器
        """
        self.llm_client = llm_client
        self.router = HybridRouter(llm_client)
        self.session_manager = session_manager or MultiAgentSessionManager()

        # L2 组件
        self.l2_decomposer = L2Decomposer(llm_client)
        self.l2_reviewer = L2Reviewer(llm_client)
        self.l2_executor = L2Executor(llm_client)

        # L3 组件
        self.l3_top_decomposer = L3TopDecomposer(llm_client)
        self.l3_reviewer = L3Reviewer(llm_client)
        self.l3_executor = L3Executor(llm_client)

    async def execute(self, user_input: str) -> ExecutionResult:
        """
        执行用户请求

        Args:
            user_input: 用户输入

        Returns:
            ExecutionResult: 执行结果
        """
        # 1. 路由决策
        route_result = await self.router.route(user_input)
        logger.info(f"路由决策: {route_result.level} (置信度: {route_result.confidence})")

        # 2. 根据复杂度级别执行
        if route_result.level == ComplexityLevel.L1:
            return await self._execute_l1(user_input)
        elif route_result.level == ComplexityLevel.L2:
            return await self._execute_l2(user_input)
        else:
            return await self._execute_l3(user_input)

    async def run_stream(self, user_input: str) -> AsyncGenerator[StreamEvent, None]:
        """
        流式执行用户请求（与 Agent.run_stream 接口兼容）

        Args:
            user_input: 用户输入

        Yields:
            StreamEvent: 流式事件
        """
        # 1. 路由决策
        yield StreamEvent(type="thinking", content=f"正在分析任务复杂度...")
        route_result = await self.router.route(user_input)
        yield StreamEvent(
            type="text",
            content=f"[Multi-Agent] 路由决策: {route_result.level.value} (置信度: {route_result.confidence:.0%})\n"
        )
        logger.info(f"路由决策: {route_result.level} (置信度: {route_result.confidence})")

        # 2. 根据复杂度级别执行
        if route_result.level == ComplexityLevel.L1:
            async for event in self._run_stream_l1(user_input):
                yield event
        elif route_result.level == ComplexityLevel.L2:
            async for event in self._run_stream_l2(user_input):
                yield event
        else:
            async for event in self._run_stream_l3(user_input):
                yield event

    async def _run_stream_l1(self, user_input: str) -> AsyncGenerator[StreamEvent, None]:
        """L1 流式执行"""
        yield StreamEvent(type="thinking", content="执行 L1: 单Agent直接执行")

        try:
            if self.llm_client:
                yield StreamEvent(type="text", content="[L1] 直接执行简单任务...\n")
                response = await self.llm_client.complete(user_input)
                yield StreamEvent(type="text", content=f"[L1] 执行完成\n")
                yield StreamEvent(type="done", content=f"L1 执行完成: {response}")
            else:
                yield StreamEvent(type="done", content="L1 执行完成（无 LLM 客户端）")
        except Exception as e:
            logger.error(f"L1 执行失败: {e}")
            yield StreamEvent(type="error", error=str(e))
            yield StreamEvent(type="done", content=f"[错误] L1 执行失败: {e}")

    async def _run_stream_l2(self, user_input: str) -> AsyncGenerator[StreamEvent, None]:
        """L2 流式执行"""
        yield StreamEvent(type="thinking", content="执行 L2: 任务分解 → 审核 → 执行")

        session = self.session_manager.create_top_session(user_input)
        task = Task(
            id=str(uuid.uuid4()),
            description=user_input,
            target_files=[],
            estimated_steps=5,
        )

        # 分解阶段
        yield StreamEvent(type="text", content="[L2] 阶段1: 任务分解中...\n")
        yield StreamEvent(type="thinking", content="正在分解任务...")
        execution_plan = await self.l2_decomposer.decompose(task)

        if not execution_plan or not execution_plan.tasks:
            yield StreamEvent(type="done", content="[L2] 分解失败：无子任务")
            return

        yield StreamEvent(
            type="text",
            content=f"[L2] 分解完成: {len(execution_plan.tasks)} 个子任务\n"
        )

        # 审核阶段
        yield StreamEvent(type="text", content="[L2] 阶段2: 审核计划中...\n")
        yield StreamEvent(type="thinking", content="正在审核计划...")
        review_result = await self.l2_reviewer.review_plan(execution_plan)

        if not review_result.approved:
            reasons = review_result.get_rejection_reasons()
            yield StreamEvent(
                type="text",
                content=f"[L2] 审核未通过: {reasons}\n"
            )
            yield StreamEvent(type="done", content=f"[L2] 计划被拒绝: {reasons}")
            return

        yield StreamEvent(type="text", content="[L2] 审核通过\n")

        # 执行阶段
        yield StreamEvent(type="text", content=f"[L2] 阶段3: 执行 {len(execution_plan.tasks)} 个任务...\n")

        task_results = []
        for i, t in enumerate(execution_plan.tasks):
            yield StreamEvent(
                type="tool_start",
                tool="Executor",
                args={"task_id": t.id, "description": t.description}
            )
            yield StreamEvent(type="thinking", content=f"执行任务: {t.description}")

            result = await self.l2_executor.execute_task(t)
            task_results.append(result)

            if result.success:
                yield StreamEvent(
                    type="tool_result",
                    tool="Executor",
                    success=True,
                    data={"task_id": t.id}
                )
            else:
                yield StreamEvent(
                    type="tool_error",
                    tool="Executor",
                    error=result.error or "任务执行失败"
                )

        # 汇总
        completed = sum(1 for r in task_results if r.success)
        failed = sum(1 for r in task_results if not r.success)

        summary = f"[L2] 执行完成: {completed} 成功, {failed} 失败"
        yield StreamEvent(type="text", content=f"\n{summary}\n")
        yield StreamEvent(type="done", content=summary)

    async def _run_stream_l3(self, user_input: str) -> AsyncGenerator[StreamEvent, None]:
        """L3 流式执行"""
        yield StreamEvent(type="thinking", content="执行 L3: 全局规划 → 子域并行 → 汇总审核")

        session = self.session_manager.create_top_session(user_input)
        task = Task(
            id=str(uuid.uuid4()),
            description=user_input,
            target_files=[],
            estimated_steps=10,
        )

        # 全局规划
        yield StreamEvent(type="text", content="[L3] 阶段1: 全局规划中...\n")
        yield StreamEvent(type="thinking", content="正在进行全局规划...")

        l3_plan = await self.l3_top_decomposer.decompose(task)

        if not l3_plan or not l3_plan.subdomains:
            yield StreamEvent(type="done", content="[L3] 规划失败：无子域")
            return

        yield StreamEvent(
            type="text",
            content=f"[L3] 全局规划完成: {len(l3_plan.subdomains)} 个子域\n"
        )

        # 全局审核
        yield StreamEvent(type="text", content="[L3] 阶段2: 全局审核中...\n")
        global_review = await self.l3_reviewer.approve_global(l3_plan)

        if not global_review.approved:
            yield StreamEvent(
                type="done",
                content=f"[L3] 全局审核未通过: {global_review.issues}"
            )
            return

        yield StreamEvent(type="text", content="[L3] 全局审核通过\n")

        # 子域并行执行
        yield StreamEvent(
            type="text",
            content=f"[L3] 阶段3: 并行执行 {len(l3_plan.subdomains)} 个子域...\n"
        )

        # 执行单个子域（内部执行，不流式输出中间状态）
        async def execute_single_subdomain(subdomain_plan: SubdomainPlan) -> SubdomainResult:
            subdomain_id = subdomain_plan.subdomain_id

            sub_decomposer = L3SubDecomposer(subdomain_plan)
            sub_plan = await sub_decomposer.decompose()

            results = await self.l3_executor.execute_parallel(sub_plan.tasks)

            for t, r in zip(sub_plan.tasks, results):
                if r.status == "completed":
                    self.l3_executor.register_subdomain_output(subdomain_id, r.result)

            completed_tasks = [t for t, r in zip(sub_plan.tasks, results) if r.status == "completed"]
            failed_tasks = [t for t, r in zip(sub_plan.tasks, results) if r.status == "failed"]

            return SubdomainResult(
                subdomain_id=subdomain_id,
                status=TaskStatus.FAILED if failed_tasks else TaskStatus.COMPLETED,
                completed=not failed_tasks,
                has_rollback_capability=True,
                completed_tasks=completed_tasks,
                failed_tasks=failed_tasks,
            )

        # 所有子域并行执行
        subdomain_results = await asyncio.gather(*[
            execute_single_subdomain(sd) for sd in l3_plan.subdomains
        ])

        # 输出子域执行摘要
        completed_subdomains = sum(1 for r in subdomain_results if r.completed)
        failed_subdomains = sum(1 for r in subdomain_results if not r.completed)
        yield StreamEvent(
            type="text",
            content=f"[L3] 子域执行完成: {completed_subdomains} 成功, {failed_subdomains} 失败\n"
        )

        # 最终审核
        yield StreamEvent(type="text", content="[L3] 阶段4: 最终审核中...\n")
        final_review = await self.l3_reviewer.approve_final(subdomain_results)

        if final_review.approved:
            summary = _summarize_subdomain_results(subdomain_results)
            yield StreamEvent(type="text", content=f"\n[L3] {summary}\n")
            yield StreamEvent(type="done", content=f"[L3] 执行完成: {summary}")
        else:
            yield StreamEvent(
                type="done",
                content=f"[L3] 最终审核未通过，需要回滚"
            )

    async def _execute_l1(self, user_input: str) -> ExecutionResult:
        """
        L1 执行：单Agent直接执行

        Args:
            user_input: 用户输入

        Returns:
            ExecutionResult: 执行结果
        """
        logger.info("执行 L1: 单Agent直接执行")

        try:
            # 直接使用 LLM 执行简单任务
            if self.llm_client:
                response = await self.llm_client.complete(user_input)
                return ExecutionResult(
                    status="completed",
                    results=[{"response": response}],
                    summary="L1 执行完成"
                )

            return ExecutionResult(
                status="completed",
                results=[],
                summary="L1 执行完成（无 LLM 客户端）"
            )
        except Exception as e:
            logger.error(f"L1 执行失败: {e}")
            return ExecutionResult(
                status="failed",
                issues=[Issue(
                    type="execution_error",
                    severity="high",
                    details=str(e)
                )]
            )

    async def _execute_l2(self, user_input: str) -> ExecutionResult:
        """
        L2 执行：两层规划执行（支持并行）

        流程：
        1. Decomposer 分解任务
        2. Reviewer 审核计划
        3. Executor 并行执行任务（按依赖分组）
        4. 最终审核 + 摘要压缩

        Args:
            user_input: 用户输入

        Returns:
            ExecutionResult: 执行结果
        """
        logger.info("执行 L2: 两层规划执行")

        # 创建顶层 Session
        session = self.session_manager.create_top_session(user_input)

        # 创建任务
        task = Task(
            id=str(uuid.uuid4()),
            description=user_input,
            target_files=[],
            estimated_steps=5,
        )

        # === 第一步：分解 + 审核 ===
        plan = await self.l2_decomposer.decompose(task)
        review_result = await self.l2_reviewer.approve(plan)

        if not review_result.approved:
            logger.warning(f"L2 计划审核未通过: {review_result.issues}")
            return ExecutionResult(
                status="rejected",
                issues=review_result.issues
            )

        # === 第二步：并行执行 ===
        # 创建 L2 Session
        l2_session = self.session_manager.create_layer2_session(
            session.session_id,
            task.id
        )

        # 使用并行执行引擎
        results = await self.l2_executor.execute_parallel(plan.tasks)

        # 更新 Session
        for task_item, result in zip(plan.tasks, results):
            l2_session.add_message(
                "assistant",
                f"Task {task_item.id}: {result.status}"
            )

        # === 第三步：汇总 + 最终审核 ===
        summary = _summarize_results(results)
        final_review = await self.l2_reviewer.final_approve(summary)

        if final_review.approved:
            return ExecutionResult(
                status="completed",
                results=results,
                summary=summary
            )
        else:
            # 回滚 + 重新执行
            logger.warning(f"L2 最终审核未通过: {final_review.issues}")
            reasons = final_review.get_rejection_reasons()
            return ExecutionResult(
                status="rejected",
                issues=final_review.issues,
                summary=f"审核拒绝，原因: {reasons}"
            )

    async def _execute_l3(self, user_input: str) -> ExecutionResult:
        """
        L3 执行：三层复杂规划（子域并行）

        流程：
        1. Top Decomposer 全局规划
        2. Top Reviewer 全局审核
        3. 子域并行执行（每个子域内部使用并行执行）
        4. Top Reviewer 最终审核

        Args:
            user_input: 用户输入

        Returns:
            ExecutionResult: 执行结果
        """
        logger.info("执行 L3: 三层复杂规划")

        # 创建顶层 Session
        session = self.session_manager.create_top_session(user_input)

        # 创建任务
        task = Task(
            id=str(uuid.uuid4()),
            description=user_input,
            target_files=[],
            estimated_steps=10,
        )

        # === 第一层：全局规划 ===
        l3_plan = await self.l3_top_decomposer.decompose(task)
        global_review = await self.l3_reviewer.approve_global(l3_plan)

        if not global_review.approved:
            logger.warning(f"L3 全局审核未通过: {global_review.issues}")
            return ExecutionResult(
                status="rejected",
                issues=global_review.issues
            )

        # === 第二层：子域并行执行 ===
        async def execute_subdomain(subdomain_plan: SubdomainPlan) -> SubdomainResult:
            """执行单个子域（内部并行执行）"""
            # 创建 L3 Session（用于追踪）
            _ = self.session_manager.create_layer3_session(
                session.session_id,
                subdomain_plan.subdomain_id
            )

            # 子域内分解
            sub_decomposer = L3SubDecomposer(subdomain_plan)
            sub_plan = await sub_decomposer.decompose()

            # 子域审核
            # 注意：这里简化了，实际应该调用子域审核

            # 第三层：子域内并行执行任务
            results = await self.l3_executor.execute_parallel(sub_plan.tasks)

            # 注册子域输出（供其他子域使用）
            for task_item, result in zip(sub_plan.tasks, results):
                if result.status == "completed":
                    self.l3_executor.register_subdomain_output(
                        subdomain_plan.subdomain_id,
                        result.result
                    )

            # 将 results 分类为 completed_tasks 和 failed_tasks
            completed_tasks = [t for t, r in zip(sub_plan.tasks, results) if r.status == "completed"]
            failed_tasks = [t for t, r in zip(sub_plan.tasks, results) if r.status == "failed"]
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

        # 所有子域并行执行
        subdomain_results = await asyncio.gather(*[
            execute_subdomain(sd) for sd in l3_plan.subdomains
        ])

        # === 第一层：最终审核 ===
        final_review = await self.l3_reviewer.approve_final(subdomain_results)

        if final_review.approved:
            # 压缩子域结果摘要
            summary = _summarize_subdomain_results(subdomain_results)
            return ExecutionResult(
                status="completed",
                results=subdomain_results,
                summary=summary
            )
        else:
            # 全局回滚（简化实现）
            logger.warning(f"L3 最终审核未通过: {final_review.issues}")
            return ExecutionResult(
                status="rejected",
                issues=final_review.issues,
                summary="L3 执行被拒绝"
            )


async def execute_simple(user_input: str, llm_client: Any | None = None) -> ExecutionResult:
    """
    简单的执行函数

    Args:
        user_input: 用户输入
        llm_client: LLM 客户端

    Returns:
        ExecutionResult: 执行结果
    """
    executor = MultiAgentExecutor(llm_client)
    return await executor.execute(user_input)


# ============ 辅助方法 ============

def _summarize_results(results: list[TaskResult]) -> str:
    """
    将多个任务结果压缩为摘要

    Args:
        results: 任务结果列表

    Returns:
        str: 摘要文本
    """
    if not results:
        return "无任务执行"

    completed = [r for r in results if r.status == "completed"]
    failed = [r for r in results if r.status == "failed"]
    cancelled = [r for r in results if r.status == "cancelled"]

    parts = [f"共 {len(results)} 个任务"]

    if completed:
        parts.append(f"完成: {len(completed)}")

    if failed:
        parts.append(f"失败: {len(failed)}")
        for r in failed:
            parts.append(f"  - {r.task_id}: {r.error or '未知错误'}")

    if cancelled:
        parts.append(f"取消: {len(cancelled)}")

    # 添加摘要信息
    summaries = [r.summary for r in results if r.summary]
    if summaries:
        parts.append("\n摘要:")
        for s in summaries[:5]:  # 最多5条
            parts.append(f"  {s}")
        if len(summaries) > 5:
            parts.append(f"  ... 还有 {len(summaries) - 5} 条")

    return "\n".join(parts)


def _summarize_subdomain_results(subdomain_results: list[SubdomainResult]) -> str:
    """
    将多个子域结果压缩为摘要

    Args:
        subdomain_results: 子域结果列表

    Returns:
        str: 摘要文本
    """
    if not subdomain_results:
        return "无子域执行"

    completed = [r for r in subdomain_results if r.completed]
    failed = [r for r in subdomain_results if not r.completed]

    parts = [f"共 {len(subdomain_results)} 个子域"]

    if completed:
        parts.append(f"完成: {len(completed)}")

    if failed:
        parts.append(f"失败: {len(failed)}")
        for r in failed:
            parts.append(f"  - {r.subdomain_id}: {len(r.failed_tasks)} 个任务失败")

    return "\n".join(parts)
