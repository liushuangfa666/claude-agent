"""
核心数据模型 - Multi-Agent 系统数据结构

定义任务、执行计划、审核结果等核心数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ComplexityLevel(Enum):
    """复杂度级别"""
    L1 = "L1"  # 简单：单Agent直接执行
    L2 = "L2"  # 中等：Decomposer + 审核 → Executor集群
    L3 = "L3"  # 复杂：三层架构 + 逐级审核


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    WAITING = "waiting"  # 等待依赖完成


class ConstraintType(Enum):
    """约束类型"""
    FILE_SCOPE = "file_scope"  # 文件边界约束
    DEPENDS_ON = "depends_on"  # 依赖约束
    ROLLBACK_REQUIRED = "rollback_required"  # 回滚方案约束
    FORBIDDEN = "forbidden"  # 禁止操作
    WAIT_FOR_EXTERNAL = "wait_for_external"  # 等待外部输入
    SUBDOMAIN_BOUNDARY = "subdomain_boundary"  # 子域边界
    OUTPUTS_FOR_OTHERS = "outputs_for_others"  # 输出给其他子域
    NO_CROSS_DOMAIN_FILES = "no_cross_domain_files"
    INTERFACE_FROZEN = "interface_frozen"
    GLOBAL_ROLLBACK = "global_rollback"


# 危险操作列表
FORBIDDEN_ACTIONS = [
    "rm -rf",
    "DROP TABLE",
    "git push --force",
    "truncate",
    "del /f /s /q",
    "mkfs",
    "fdisk",
]


@dataclass
class Constraint:
    """执行约束"""
    type: ConstraintType
    description: str
    files: list[str] | None = None
    tasks: list[str] | None = None
    actions: list[str] | None = None
    method: str | None = None
    source: str | None = None  # 来源（如 subdomain_id）
    condition: str | None = None  # 触发条件

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value if isinstance(self.type, Enum) else self.type,
            "description": self.description,
            "files": self.files,
            "tasks": self.tasks,
            "actions": self.actions,
            "method": self.method,
            "source": self.source,
            "condition": self.condition,
        }


@dataclass
class Issue:
    """审核问题"""
    type: str
    severity: str  # "critical", "high", "medium", "low"
    details: Any | None = None
    resolution: str | None = None
    task_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "details": self.details,
            "resolution": self.resolution,
            "task_id": self.task_id,
        }


@dataclass
class SubTask:
    """子任务定义（用于Decomposer输出）"""
    id: str
    description: str
    target_files: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    estimated_steps: int = 1


@dataclass
class ReviewResult:
    """审核结果"""
    approved: bool
    issues: list[Issue] = field(default_factory=list)
    requires_redo: bool = False
    rejection_reasons: list[str] = field(default_factory=list)
    reviewed_at: datetime = field(default_factory=datetime.now)

    @property
    def critical_issues(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "critical"]

    @property
    def high_issues(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "high"]

    def get_rejection_reasons(self) -> list[str]:
        """获取拒绝原因列表"""
        reasons = []
        for issue in self.issues:
            reason = f"[{issue.severity}] {issue.type}"
            if issue.task_id:
                reason += f" (task: {issue.task_id})"
            if issue.resolution:
                reason += f" - {issue.resolution}"
            reasons.append(reason)
        return reasons


@dataclass
class RollbackPlan:
    """回滚计划"""
    method: str  # "git_branch", "copy", "snapshot"
    checkpoint_path: str | None = None
    backup_created: bool = False
    rollback_steps: list[str] = field(default_factory=list)


@dataclass
class Task:
    """执行任务"""
    id: str
    description: str
    target_files: list[str] = field(default_factory=list)
    estimated_steps: int = 0
    dependencies: list[str] = field(default_factory=list)  # 依赖的任务ID
    constraints: list[Constraint] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: Any | None = None
    error: str | None = None
    rollback_plan: RollbackPlan | None = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    parent_id: str | None = None  # 父任务ID（用于层级追踪）
    has_rollback_plan: bool = False
    depends_on_subdomain: str | None = None

    def add_constraint(self, constraint: Constraint) -> None:
        """添加约束"""
        self.constraints.append(constraint)

    def is_ready(self, completed_tasks: set[str]) -> bool:
        """检查依赖是否满足"""
        return all(dep in completed_tasks for dep in self.dependencies)


@dataclass
class ExecutionPlan:
    """执行计划"""
    id: str
    level: ComplexityLevel
    tasks: list[Task] = field(default_factory=list)
    global_constraints: list[Constraint] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    parent_task_id: str | None = None

    def add_task(self, task: Task) -> None:
        """添加任务"""
        self.tasks.append(task)

    def get_task(self, task_id: str) -> Task | None:
        """获取任务"""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def topological_sort(self) -> list[Task]:
        """
        拓扑排序：按依赖顺序返回任务列表
        使得所有依赖都在任务之前
        """
        sorted_tasks = []
        completed = set()
        remaining = {t.id: t for t in self.tasks}

        while remaining:
            # 找所有依赖都已完成的任务
            ready = [
                t for tid, t in remaining.items()
                if all(dep in completed for dep in t.dependencies)
            ]

            if not ready:
                # 有环或死锁（不应该发生）
                # 剩余任务按原始顺序返回
                sorted_tasks.extend(remaining.values())
                break

            sorted_tasks.extend(ready)
            for t in ready:
                completed.add(t.id)
                del remaining[t.id]

        return sorted_tasks


@dataclass
class CrossDomainDep:
    """跨子域依赖"""
    source_subdomain: str
    target_subdomain: str
    interface_files: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class SubdomainPlan:
    """L3子域计划"""
    subdomain_id: str
    tasks: list[Task] = field(default_factory=list)
    local_constraints: list[Constraint] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)  # 本子域为其他子域提供的输出
    depends_on: list[str] = field(default_factory=list)  # 依赖的其他子域ID
    cross_domain_deps: list[CrossDomainDep] = field(default_factory=list)
    allowed_files: list[str] = field(default_factory=list)
    outputs_interface: list[str] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """添加任务"""
        task.parent_id = self.subdomain_id
        self.tasks.append(task)


@dataclass
class SubdomainResult:
    """子域执行结果"""
    subdomain_id: str
    status: TaskStatus
    completed_tasks: list[Task] = field(default_factory=list)
    failed_tasks: list[Task] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    summary: str = ""
    token_count: int = 0
    completed: bool = False
    has_rollback_capability: bool = True


@dataclass
class L3Plan:
    """L3完整计划"""
    subdomains: list[SubdomainPlan] = field(default_factory=list)
    cross_domain_dependencies: list[CrossDomainDep] = field(default_factory=list)
    global_review_criteria: list[str] = field(default_factory=list)
    global_constraints: list[Constraint] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """执行结果"""
    status: str  # "completed", "rejected", "failed"
    results: list[Any] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    summary: str = ""


@dataclass
class RouteResult:
    """路由结果"""
    level: ComplexityLevel
    reasoning: str
    confidence: float  # 0.0 - 1.0
    method: str  # "rule_based" | "llm_assisted"
    estimated_tasks: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "method": self.method,
            "estimated_tasks": self.estimated_tasks,
        }
