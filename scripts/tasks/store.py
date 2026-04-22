"""
TaskStore - 任务持久化存储
"""
from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from dataclasses import asdict
from typing import Optional

from .types import BaseTaskState, TaskStatus


class TaskStore:
    """任务存储"""

    def __init__(self, storage_path: Optional[str] = None) -> None:
        """
        初始化任务存储

        Args:
            storage_path: 存储文件路径，默认 .claude-agent/tasks.json
        """
        self._storage_path = (
            storage_path or ".claude-agent/tasks.json"
        )
        self._tasks: dict[str, BaseTaskState] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        """从磁盘加载"""
        if os.path.exists(self._storage_path):
            try:
                with open(self._storage_path, encoding="utf-8") as f:
                    data = json.load(f)
                    for task_data in data.values():
                        self._tasks[task_data["id"]] = self._deserialize(
                            task_data
                        )
            except Exception:
                pass

    def _save_to_disk(self) -> None:
        """保存到磁盘"""
        os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)
        with open(self._storage_path, "w", encoding="utf-8") as f:
            data = {k: self._serialize(v) for k, v in self._tasks.items()}
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _serialize(self, task: BaseTaskState) -> dict:
        """序列化任务"""
        return asdict(task)

    def _deserialize(self, data: dict) -> BaseTaskState:
        """反序列化任务"""
        from .types import TaskStatus, TaskType

        data["status"] = TaskStatus(data["status"])
        data["type"] = TaskType(data["type"])
        return BaseTaskState(**data)

    def save(self, task: BaseTaskState) -> None:
        """保存任务"""
        with self._lock:
            self._tasks[task.id] = deepcopy(task)
            self._save_to_disk()

    def get(self, task_id: str) -> Optional[BaseTaskState]:
        """获取任务"""
        return self._tasks.get(task_id)

    def list(self, status: Optional[TaskStatus] = None) -> list[BaseTaskState]:
        """列出任务"""
        if status:
            return [t for t in self._tasks.values() if t.status == status]
        return list(self._tasks.values())

    def delete(self, task_id: str) -> bool:
        """删除任务"""
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._save_to_disk()
            return True
        return False

    def update_dependencies(self, completed_task_id: str) -> list[str]:
        """
        更新依赖，返回可以执行的任务 ID

        Args:
            completed_task_id: 已完成的任务 ID

        Returns:
            解除阻塞的任务 ID 列表
        """
        unblocked = []
        with self._lock:
            for task in self._tasks.values():
                if task.status == TaskStatus.PENDING and task.is_blocked:
                    if completed_task_id in task.blocked_by:
                        task.blocked_by.remove(completed_task_id)
                        self.save(task)
                        if not task.is_blocked:
                            unblocked.append(task.id)
        return unblocked
