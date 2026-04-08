"""
任务通知服务

在任务完成时发送通知。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from .models import Task

logger = logging.getLogger(__name__)


class TaskNotification:
    """任务通知服务"""

    def __init__(self):
        self._handlers: list[Callable[[Task], None]] = []

    def register_handler(self, handler: Callable[[Task], None]) -> None:
        """注册通知处理器"""
        self._handlers.append(handler)

    def unregister_handler(self, handler: Callable[[Task], None]) -> None:
        """取消注册通知处理器"""
        self._handlers.remove(handler)

    def notify(self, task: Task) -> None:
        """发送通知"""
        for handler in self._handlers:
            try:
                handler(task)
            except Exception as e:
                logger.error(f"Notification handler failed: {e}")

    async def notify_async(self, task: Task) -> None:
        """异步发送通知"""
        for handler in self._handlers:
            try:
                result = handler(task)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Notification handler failed: {e}")


class TaskNotifier:
    """任务状态监听器
    
    监听任务状态变化并发送通知。
    """

    def __init__(self, notification: TaskNotification | None = None):
        self._notification = notification or TaskNotification()
        self._monitored_tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def monitor_task(
        self,
        task_id: str,
        runner,
        session_id: str,
    ) -> None:
        """监视任务直到完成"""
        while True:
            bg_task = runner.get_running_task(task_id)

            if not bg_task:
                task = runner._store.get(task_id, session_id)
                if task:
                    self._notification.notify(task)
                break

            if not bg_task.is_running:
                self._notification.notify(bg_task.task)
                break

            await asyncio.sleep(0.5)

    async def start_monitoring(
        self,
        task_id: str,
        runner,
        session_id: str,
    ) -> None:
        """开始监视任务"""
        async with self._lock:
            if task_id in self._monitored_tasks:
                return

            monitor_task = asyncio.create_task(
                self.monitor_task(task_id, runner, session_id)
            )
            self._monitored_tasks[task_id] = monitor_task

    async def stop_monitoring(self, task_id: str) -> None:
        """停止监视任务"""
        async with self._lock:
            if task_id in self._monitored_tasks:
                self._monitored_tasks[task_id].cancel()
                try:
                    await self._monitored_tasks[task_id]
                except asyncio.CancelledError:
                    pass
                del self._monitored_tasks[task_id]

    async def stop_all(self) -> None:
        """停止所有监视"""
        for task_id in list(self._monitored_tasks.keys()):
            await self.stop_monitoring(task_id)
