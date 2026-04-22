"""
Task 存储服务

负责任务的磁盘持久化和文件锁。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from filelock import FileLock

from .models import Task, TaskStatus

logger = logging.getLogger(__name__)


class TaskStore:
    """任务存储服务"""

    def __init__(self, base_dir: Path | None = None):
        if base_dir is None:
            base_dir = Path.home() / ".crush" / "tasks"

        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock_file = self._base_dir / ".lock"

    def _get_session_dir(self, session_id: str) -> Path:
        """获取会话任务目录"""
        session_dir = self._base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def _get_lock(self, session_id: str) -> FileLock:
        """获取文件锁"""
        session_dir = self._get_session_dir(session_id)
        return FileLock(session_dir / ".lock", is_singleton=True)

    def _list_task_files(self, session_id: str) -> list[Path]:
        """列出任务文件"""
        session_dir = self._get_session_dir(session_id)
        return sorted(session_dir.glob("*.json"), key=lambda p: int(p.stem))

    def _get_next_id(self, session_id: str) -> int:
        """获取下一个任务 ID"""
        lock = self._get_lock(session_id)

        with lock:
            task_files = self._list_task_files(session_id)

            if not task_files:
                return 1

            max_id = max(int(f.stem) for f in task_files)
            return max_id + 1

    def create(self, task: Task, session_id: str) -> Task:
        """创建任务"""
        lock = self._get_lock(session_id)

        with lock:
            task.id = str(self._get_next_id(session_id))
            task.created_at = datetime.now()
            task.updated_at = datetime.now()

            task_file = self._get_session_dir(session_id) / f"{task.id}.json"

            with open(task_file, "w", encoding="utf-8") as f:
                json.dump(task.to_dict(), f, indent=2, ensure_ascii=False)

            logger.info(f"Created task {task.id}: {task.subject}")

            return task

    def get(self, task_id: str, session_id: str) -> Task | None:
        """获取任务"""
        task_file = self._get_session_dir(session_id) / f"{task_id}.json"

        if not task_file.exists():
            return None

        try:
            with open(task_file, encoding="utf-8") as f:
                data = json.load(f)
            return Task.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load task {task_id}: {e}")
            return None

    def list_all(self, session_id: str) -> list[Task]:
        """列出所有任务"""
        tasks = []

        for task_file in self._list_task_files(session_id):
            try:
                with open(task_file, encoding="utf-8") as f:
                    data = json.load(f)
                tasks.append(Task.from_dict(data))
            except Exception as e:
                logger.error(f"Failed to load task {task_file}: {e}")

        return sorted(tasks, key=lambda t: int(t.id))

    def update(self, task: Task, session_id: str) -> Task:
        """更新任务"""
        lock = self._get_lock(session_id)

        with lock:
            task.updated_at = datetime.now()

            task_file = self._get_session_dir(session_id) / f"{task.id}.json"

            with open(task_file, "w", encoding="utf-8") as f:
                json.dump(task.to_dict(), f, indent=2, ensure_ascii=False)

            logger.info(f"Updated task {task.id}: {task.status.value}")

            return task

    def delete(self, task_id: str, session_id: str) -> bool:
        """删除任务"""
        lock = self._get_lock(session_id)

        with lock:
            task_file = self._get_session_dir(session_id) / f"{task_id}.json"

            if task_file.exists():
                task_file.unlink()
                logger.info(f"Deleted task {task_id}")
                return True

            return False

    def update_status(
        self,
        task_id: str,
        session_id: str,
        status: TaskStatus,
    ) -> Task | None:
        """更新任务状态"""
        task = self.get(task_id, session_id)

        if not task:
            return None

        task.status = status

        if status == TaskStatus.IN_PROGRESS:
            task.started_at = datetime.now()
        elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.KILLED):
            task.completed_at = datetime.now()

        return self.update(task, session_id)

    def get_by_status(
        self,
        session_id: str,
        status: TaskStatus,
    ) -> list[Task]:
        """按状态获取任务"""
        all_tasks = self.list_all(session_id)
        return [t for t in all_tasks if t.status == status]
