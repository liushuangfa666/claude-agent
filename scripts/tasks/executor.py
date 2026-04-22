"""
TaskExecutor - 统一任务执行器
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from .store import TaskStore
from .types import (
    BaseTaskState,
    TaskStatus,
    TaskType,
    TaskResult,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class TaskExecutor:
    """统一任务执行器"""

    def __init__(self, task_store: TaskStore) -> None:
        """
        初始化任务执行器

        Args:
            task_store: 任务存储实例
        """
        self._store = task_store
        self._running_tasks: dict[str, asyncio.Task] = {}

    async def execute(self, task: BaseTaskState) -> TaskResult:
        """
        执行任务

        Args:
            task: 任务状态

        Returns:
            任务结果
        """
        if not self._check_dependencies(task):
            return TaskResult(
                status=TaskStatus.PENDING, error="Blocked by dependencies"
            )

        self._store.update_dependencies(task.id)

        task.status = TaskStatus.RUNNING
        task.start_time = asyncio.get_event_loop().time()
        self._store.save(task)

        try:
            result = await self._run_task(task)
            task.result = result
            task.status = TaskStatus.COMPLETED
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.result = TaskResult(status=TaskStatus.FAILED, error=str(e))
        finally:
            task.end_time = asyncio.get_event_loop().time()
            self._store.save(task)
            self._store.update_dependencies(task.id)

        return task.result

    def _check_dependencies(self, task: BaseTaskState) -> bool:
        """
        检查依赖是否满足

        Args:
            task: 任务状态

        Returns:
            是否可以执行
        """
        for dep_id in task.blocked_by:
            dep = self._store.get(dep_id)
            if not dep or dep.status != TaskStatus.COMPLETED:
                return False
        return True

    async def _run_task(self, task: BaseTaskState) -> TaskResult:
        """
        根据类型运行任务

        Args:
            task: 任务状态

        Returns:
            任务结果
        """
        if task.type == TaskType.BASH:
            return await self._run_bash(task)
        elif task.type == TaskType.AGENT:
            return await self._run_agent(task)
        elif task.type == TaskType.REMOTE_AGENT:
            return await self._run_remote_agent(task)
        elif task.type == TaskType.IN_PROCESS_TEAMMATE:
            return await self._run_teammate(task)
        elif task.type == TaskType.MONITOR:
            return await self._run_monitor(task)
        elif task.type == TaskType.WORKFLOW:
            return await self._run_workflow(task)
        else:
            return TaskResult(
                status=TaskStatus.FAILED, error=f"Unknown task type: {task.type}"
            )

    async def _run_bash(self, task: BaseTaskState) -> TaskResult:
        """运行 Bash 任务"""
        # Placeholder - 实际调用 BashTool
        logger.info(f"Running bash task: {task.id}")
        return TaskResult(status=TaskStatus.COMPLETED, output="bash executed")

    async def _run_agent(self, task: BaseTaskState) -> TaskResult:
        """运行 Agent 任务"""
        logger.info(f"Running agent task: {task.id}")
        return TaskResult(status=TaskStatus.COMPLETED, output="agent executed")

    async def _run_remote_agent(self, task: BaseTaskState) -> TaskResult:
        """运行远程 Agent 任务"""
        logger.info(f"Running remote agent task: {task.id}")
        return TaskResult(
            status=TaskStatus.COMPLETED, output="remote agent executed"
        )

    async def _run_teammate(self, task: BaseTaskState) -> TaskResult:
        """运行进程内队友任务"""
        logger.info(f"Running teammate task: {task.id}")
        return TaskResult(status=TaskStatus.COMPLETED, output="teammate executed")

    async def _run_monitor(self, task: BaseTaskState) -> TaskResult:
        """运行监控任务"""
        logger.info(f"Running monitor task: {task.id}")
        return TaskResult(status=TaskStatus.COMPLETED, output="monitor executed")

    async def _run_workflow(self, task: BaseTaskState) -> TaskResult:
        """运行工作流任务"""
        logger.info(f"Running workflow task: {task.id}")
        return TaskResult(
            status=TaskStatus.COMPLETED, output="workflow executed"
        )

    async def submit(self, task: BaseTaskState) -> str:
        """
        提交任务

        Args:
            task: 任务状态

        Returns:
            任务 ID
        """
        self._store.save(task)

        if not task.is_blocked:
            asyncio.create_task(self.execute(task))

        return task.id

    async def kill(self, task_id: str) -> bool:
        """
        终止任务

        Args:
            task_id: 任务 ID

        Returns:
            是否成功终止
        """
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            return True
        return False
