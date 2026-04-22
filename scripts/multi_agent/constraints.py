"""
约束系统 - Multi-Agent 约束数据结构

定义 Multi-Agent 系统中使用的约束类型和数据结构。

注意：主要的类型定义在 models.py 中，此文件保留向后兼容性。
"""

from __future__ import annotations

# 重新导出 models.py 中的类型以保持向后兼容
from .models import (
    FORBIDDEN_ACTIONS,
    Constraint,
    ConstraintType,
    TaskStatus,
)

__all__ = [
    "Constraint",
    "ConstraintType",
    "TaskStatus",
    "FORBIDDEN_ACTIONS",
]
