"""
Task 数据模型

定义任务相关的数据结构。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


class TaskType(str, Enum):
    """任务类型枚举"""
    BASH = "bash"
    AGENT = "agent"
    WORKFLOW = "workflow"


@dataclass
class Task:
    """任务定义"""
    id: str
    subject: str
    description: str = ""
    active_form: str = ""
    status: TaskStatus = TaskStatus.PENDING
    task_type: TaskType = TaskType.BASH
    owner: str | None = None
    blocks: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "subject": self.subject,
            "description": self.description,
            "active_form": self.active_form,
            "status": self.status.value,
            "task_type": self.task_type.value,
            "owner": self.owner,
            "blocks": self.blocks,
            "blocked_by": self.blocked_by,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        """从字典创建"""
        return cls(
            id=data["id"],
            subject=data["subject"],
            description=data.get("description", ""),
            active_form=data.get("active_form", ""),
            status=TaskStatus(data.get("status", "pending")),
            task_type=TaskType(data.get("task_type", "bash")),
            owner=data.get("owner"),
            blocks=data.get("blocks", []),
            blocked_by=data.get("blocked_by", []),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.now(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        )


@dataclass
class BackgroundTask:
    """后台任务"""
    task: Task
    process: asyncio.subprocess.Process | None = None
    future: asyncio.Future | None = None
    output: str = ""
    error: str | None = None

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        if self.future is None:
            return False
        return not self.future.done()

    def append_output(self, text: str) -> None:
        """追加输出"""
        self.output += text

    def set_error(self, error: str) -> None:
        """设置错误"""
        self.error = error
