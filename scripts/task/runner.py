"""
后台任务运行器

管理后台任务的执行。
"""
from __future__ import annotations

import asyncio
import logging

from .models import BackgroundTask, Task, TaskStatus, TaskType
from .store import TaskStore

logger = logging.getLogger(__name__)


class BackgroundTaskRunner:
    """后台任务运行器"""

    def __init__(self, store: TaskStore | None = None):
        self._store = store or TaskStore()
        self._running_tasks: dict[str, BackgroundTask] = {}
        self._lock = asyncio.Lock()

    async def run_task(
        self,
        task: Task,
        session_id: str,
    ) -> BackgroundTask:
        """运行任务"""
        async with self._lock:
            if task.id in self._running_tasks:
                raise ValueError(f"Task {task.id} is already running")

        bg_task = BackgroundTask(task=task)

        if task.task_type == TaskType.BASH:
            await self._run_bash_task(bg_task, session_id)
        elif task.task_type == TaskType.AGENT:
            await self._run_agent_task(bg_task, session_id)
        else:
            raise ValueError(f"Unknown task type: {task.task_type}")

        return bg_task

    async def _run_bash_task(
        self,
        bg_task: BackgroundTask,
        session_id: str,
    ) -> None:
        """运行 Bash 任务"""
        command = bg_task.task.metadata.get("command", "")

        if not command:
            bg_task.error = "No command specified"
            await self._update_task_status(bg_task.task.id, session_id, TaskStatus.FAILED)
            return

        async def run():
            try:
                await self._update_task_status(bg_task.task.id, session_id, TaskStatus.IN_PROGRESS)

                self._running_tasks[bg_task.task.id] = bg_task

                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                bg_task.process = process

                stdout, stderr = await process.communicate()

                if stdout:
                    bg_task.append_output(stdout.decode())
                if stderr:
                    bg_task.append_output(stderr.decode())

                if process.returncode == 0:
                    await self._update_task_status(bg_task.task.id, session_id, TaskStatus.COMPLETED)
                else:
                    bg_task.error = f"Exit code: {process.returncode}"
                    await self._update_task_status(bg_task.task.id, session_id, TaskStatus.FAILED)

            except Exception as e:
                bg_task.error = str(e)
                await self._update_task_status(bg_task.task.id, session_id, TaskStatus.FAILED)

            finally:
                async with self._lock:
                    self._running_tasks.pop(bg_task.task.id, None)

        bg_task.future = asyncio.create_task(run())

    async def _run_agent_task(
        self,
        bg_task: BackgroundTask,
        session_id: str,
    ) -> None:
        """运行 Agent 任务"""
        from scripts.subagent.executor import get_subagent_executor
        from scripts.subagent.types import SubagentType

        executor = get_subagent_executor()

        await self._update_task_status(bg_task.task.id, session_id, TaskStatus.IN_PROGRESS)
        self._running_tasks[bg_task.task.id] = bg_task

        try:
            prompt = bg_task.task.metadata.get("prompt", "")
            description = bg_task.task.metadata.get("description", "")
            subagent_type_str = bg_task.task.metadata.get("subagent_type", "GeneralPurpose")

            try:
                subagent_type = SubagentType.from_string(subagent_type_str)
            except ValueError:
                subagent_type = SubagentType.GENERAL_PURPOSE

            agent_info = await executor.execute_background(
                prompt=prompt,
                subagent_type=subagent_type,
                description=description,
            )

            # 等待子代理结果
            bg_task.future = asyncio.create_task(
                self._wait_for_agent_result(agent_info.agent_id, bg_task, session_id)
            )

        except Exception as e:
            bg_task.error = str(e)
            await self._update_task_status(bg_task.task.id, session_id, TaskStatus.FAILED)

    async def _wait_for_agent_result(
        self,
        agent_id: str,
        bg_task: BackgroundTask,
        session_id: str,
    ) -> None:
        """等待子代理完成并更新任务状态"""
        from scripts.subagent.executor import get_subagent_executor

        executor = get_subagent_executor()

        # 轮询等待子代理完成
        while True:
            agent_info = executor.get_status(agent_id)
            if agent_info is None:
                bg_task.error = f"Agent {agent_id} not found"
                await self._update_task_status(bg_task.task.id, session_id, TaskStatus.FAILED)
                return

            if agent_info.status == "completed":
                if agent_info.result:
                    bg_task.append_output(agent_info.result)
                await self._update_task_status(bg_task.task.id, session_id, TaskStatus.COMPLETED)
                return

            if agent_info.status == "failed":
                bg_task.error = agent_info.error or "Agent failed"
                await self._update_task_status(bg_task.task.id, session_id, TaskStatus.FAILED)
                return

            if agent_info.status == "stopped":
                await self._update_task_status(bg_task.task.id, session_id, TaskStatus.KILLED)
                return

            # 每 0.5 秒检查一次
            await asyncio.sleep(0.5)

    async def _update_task_status(
        self,
        task_id: str,
        session_id: str,
        status: TaskStatus,
    ) -> None:
        """更新任务状态"""
        self._store.update_status(task_id, session_id, status)

        if status == TaskStatus.IN_PROGRESS:
            bg_task = self._running_tasks.get(task_id)
            if bg_task:
                bg_task.task.status = status
        elif status == TaskStatus.COMPLETED:
            bg_task = self._running_tasks.get(task_id)
            if bg_task:
                bg_task.task.status = status
        elif status == TaskStatus.FAILED:
            bg_task = self._running_tasks.get(task_id)
            if bg_task:
                bg_task.task.status = status
        elif status == TaskStatus.KILLED:
            bg_task = self._running_tasks.get(task_id)
            if bg_task:
                bg_task.task.status = status

    async def stop_task(self, task_id: str) -> bool:
        """停止任务"""
        async with self._lock:
            bg_task = self._running_tasks.get(task_id)

            if not bg_task:
                return False

            if bg_task.future and not bg_task.future.done():
                bg_task.future.cancel()

                try:
                    await bg_task.future
                except asyncio.CancelledError:
                    pass

            if bg_task.process and bg_task.process.returncode is None:
                bg_task.process.terminate()
                try:
                    await asyncio.wait_for(bg_task.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    bg_task.process.kill()

            return True

    def get_running_task(self, task_id: str) -> BackgroundTask | None:
        """获取正在运行的任务"""
        return self._running_tasks.get(task_id)

    def get_task_output(self, task_id: str) -> str | None:
        """获取任务输出"""
        bg_task = self._running_tasks.get(task_id)
        return bg_task.output if bg_task else None

    def list_running_tasks(self) -> list[str]:
        """列出正在运行的任务 ID"""
        return list(self._running_tasks.keys())
