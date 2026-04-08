"""
Task 类型定义
"""
from __future__ import annotations

import random
import string
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


class TaskType(Enum):
    """任务类型枚举"""
    BASH = "bash"
    AGENT = "agent"
    WORKFLOW = "workflow"
    REMOTE_AGENT = "remote_agent"
    IN_PROCESS_TEAMMATE = "in_process_teammate"
    MONITOR = "monitor"


@dataclass
class TaskResult:
    """任务结果"""
    status: TaskStatus
    output: Any = None
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class BaseTaskState:
    """基础任务状态"""
    id: str
    type: TaskType
    status: TaskStatus = TaskStatus.PENDING
    description: str = ""
    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    result: Optional[TaskResult] = None

    @property
    def is_blocked(self) -> bool:
        """是否被阻塞"""
        return len(self.blocked_by) > 0


def generate_task_id(task_type: TaskType) -> str:
    """
    生成任务 ID

    Args:
        task_type: 任务类型

    Returns:
        任务 ID，格式为 "类型首字母 + 8位随机字符"
    """
    prefix = task_type.value[0]  # b, a, w, r, t, m
    suffix = "".join(
        random.choices(string.ascii_lowercase + string.digits, k=8)
    )
    return f"{prefix}{suffix}"
