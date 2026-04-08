"""
计划模式 - 让 AI 先规划再执行

参考 Claude Code 的 EnterPlanMode/ExitPlanMode 设计。
在计划模式中，AI 生成执行计划但不实际执行工具。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class PlanStep:
    """计划步骤"""
    step_number: int
    tool_name: str
    args: dict
    reason: str
    status: str = "pending"  # pending, approved, rejected, executed
    result: str | None = None


@dataclass
class Plan:
    """执行计划"""
    task: str
    steps: list[PlanStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    approved: bool = False

    def to_markdown(self) -> str:
        """转换为 Markdown 格式"""
        lines = ["## 执行计划\n"]
        lines.append(f"**任务**: {self.task}\n")
        lines.append(f"**状态**: {'✅ 已批准' if self.approved else '⏳ 待批准'}\n")
        lines.append("\n### 步骤:\n")

        for step in self.steps:
            status_icon = {
                "pending": "⏳",
                "approved": "✅",
                "rejected": "❌",
                "executed": "🎉",
            }.get(step.status, "⚪")

            lines.append(f"{status_icon} **{step.step_number}. {step.tool_name}**")
            lines.append(f"   - 原因: {step.reason}")
            lines.append(f"   - 参数: {step.args}")
            if step.result:
                lines.append(f"   - 结果: {step.result}")
            lines.append("")

        return "\n".join(lines)


class PlanModeManager:
    """计划模式管理器"""

    def __init__(self):
        self._enabled: bool = False
        self._current_plan: Plan | None = None
        self._auto_approve: bool = False  # 是否自动批准

    @property
    def enabled(self) -> bool:
        """是否处于计划模式"""
        return self._enabled

    @property
    def current_plan(self) -> Plan | None:
        """获取当前计划"""
        return self._current_plan

    def enter_plan_mode(self, task: str) -> Plan:
        """进入计划模式"""
        self._enabled = True
        self._current_plan = Plan(task=task)
        return self._current_plan

    def exit_plan_mode(self, approved: bool = False) -> Plan | None:
        """退出计划模式"""
        if self._current_plan:
            self._current_plan.approved = approved
        self._enabled = False
        plan = self._current_plan
        self._current_plan = None
        return plan

    def add_step(
        self,
        tool_name: str,
        args: dict,
        reason: str,
    ) -> PlanStep:
        """添加计划步骤"""
        if not self._current_plan:
            raise RuntimeError("Not in plan mode")

        step = PlanStep(
            step_number=len(self._current_plan.steps) + 1,
            tool_name=tool_name,
            args=args,
            reason=reason,
        )
        self._current_plan.steps.append(step)
        return step

    def approve_step(self, step_number: int) -> bool:
        """批准某个步骤"""
        if not self._current_plan:
            return False

        for step in self._current_plan.steps:
            if step.step_number == step_number:
                step.status = "approved"
                return True
        return False

    def reject_step(self, step_number: int) -> bool:
        """拒绝某个步骤"""
        if not self._current_plan:
            return False

        for step in self._current_plan.steps:
            if step.step_number == step_number:
                step.status = "rejected"
                return True
        return False

    def mark_step_executed(self, step_number: int, result: str) -> bool:
        """标记步骤已执行"""
        if not self._current_plan:
            return False

        for step in self._current_plan.steps:
            if step.step_number == step_number:
                step.status = "executed"
                step.result = result
                return True
        return False

    def get_pending_steps(self) -> list[PlanStep]:
        """获取待执行的步骤"""
        if not self._current_plan:
            return []
        return [s for s in self._current_plan.steps if s.status == "approved"]

    def get_all_steps(self) -> list[PlanStep]:
        """获取所有步骤"""
        if not self._current_plan:
            return []
        return self._current_plan.steps


# 全局单例
_plan_mode_manager: PlanModeManager | None = None


def get_plan_mode_manager() -> PlanModeManager:
    """获取计划模式管理器单例"""
    global _plan_mode_manager
    if _plan_mode_manager is None:
        _plan_mode_manager = PlanModeManager()
    return _plan_mode_manager


def reset_plan_mode() -> None:
    """重置计划模式"""
    global _plan_mode_manager
    _plan_mode_manager = None
