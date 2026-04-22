"""Rollback mechanism for plan execution."""
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RollbackAction:
    """
    Represents a single rollback action.
    
    Attributes:
        step_number: The step that was executed and needs rollback
        tool_name: Name of the tool that was executed
        args: Tool arguments
        result: Result of the tool execution
        rollback_command: Optional command to undo the action
        rollback_args: Arguments for the rollback tool
    """
    step_number: int
    tool_name: str
    args: dict[str, Any]
    result: str | None = None
    rollback_command: str | None = None
    rollback_args: dict[str, Any] | None = None


@dataclass
class RollbackPlan:
    """
    A plan for rolling back a series of executed steps.
    
    Attributes:
        original_task: The original task description
        executed_steps: List of steps that were executed
        rollback_actions: List of rollback actions to perform
        created_at: Timestamp when rollback was initiated
    """
    original_task: str
    executed_steps: list[dict[str, Any]] = field(default_factory=list)
    rollback_actions: list[RollbackAction] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    status: str = "pending"


class RollbackManager:
    """
    Manages rollback operations for plan execution.
    
    This class tracks executed steps and provides mechanisms to
    undo them in case of failures.
    """
    
    def __init__(self):
        self._rollback_plans: list[RollbackPlan] = []
        self._current_plan: RollbackPlan | None = None
    
    def start_rollback_plan(self, task: str) -> RollbackPlan:
        """
        Start a new rollback plan.
        
        Args:
            task: Description of the original task
            
        Returns:
            The new RollbackPlan
        """
        plan = RollbackPlan(original_task=task)
        self._rollback_plans.append(plan)
        self._current_plan = plan
        return plan
    
    def record_step(self, step_number: int, tool_name: str, 
                    args: dict[str, Any], result: str,
                    rollback_command: str | None = None,
                    rollback_args: dict[str, Any] | None = None) -> None:
        """
        Record a step execution for potential rollback.
        
        Args:
            step_number: The step number
            tool_name: Name of the tool executed
            args: Tool arguments
            result: Execution result
            rollback_command: Optional command to undo the action
            rollback_args: Arguments for the rollback tool
        """
        if self._current_plan is None:
            return
        
        self._current_plan.executed_steps.append({
            "step_number": step_number,
            "tool_name": tool_name,
            "args": args,
            "result": result
        })
        
        if rollback_command or rollback_args:
            action = RollbackAction(
                step_number=step_number,
                tool_name=tool_name,
                args=args,
                result=result,
                rollback_command=rollback_command,
                rollback_args=rollback_args
            )
            self._current_plan.rollback_actions.append(action)
    
    def add_rollback_action(self, action: RollbackAction) -> None:
        """
        Add a rollback action to the current plan.
        
        Args:
            action: The rollback action to add
        """
        if self._current_plan is None:
            return
        self._current_plan.rollback_actions.append(action)
    
    def generate_rollback_steps(self) -> list[dict[str, Any]]:
        """
        Generate the rollback steps in reverse order.
        
        Returns:
            List of rollback steps to execute
        """
        if self._current_plan is None:
            return []
        
        steps = []
        for action in reversed(self._current_plan.rollback_actions):
            if action.rollback_command:
                steps.append({
                    "tool_name": "Bash",
                    "args": {"command": action.rollback_command},
                    "description": f"Rollback step {action.step_number}",
                    "reason": f"Undo {action.tool_name} (step {action.step_number})"
                })
            elif action.rollback_args:
                steps.append({
                    "tool_name": action.tool_name,
                    "args": action.rollback_args,
                    "description": f"Rollback step {action.step_number}",
                    "reason": f"Undo {action.tool_name} (step {action.step_number})"
                })
        
        return steps
    
    def get_current_plan(self) -> RollbackPlan | None:
        """Get the current rollback plan."""
        return self._current_plan
    
    def cancel_rollback_plan(self) -> None:
        """Cancel the current rollback plan."""
        self._current_plan = None
    
    def finalize_rollback_plan(self) -> RollbackPlan | None:
        """
        Finalize and return the current rollback plan.
        
        Returns:
            The completed rollback plan, or None if no plan exists
        """
        plan = self._current_plan
        self._current_plan = None
        return plan
    
    def clear(self) -> None:
        """Clear all rollback plans."""
        self._rollback_plans.clear()
        self._current_plan = None


_global_rollback_manager: RollbackManager | None = None


def get_rollback_manager() -> RollbackManager:
    """Get the global rollback manager singleton."""
    global _global_rollback_manager
    if _global_rollback_manager is None:
        _global_rollback_manager = RollbackManager()
    return _global_rollback_manager


def reset_rollback_manager() -> None:
    """Reset the global rollback manager."""
    global _global_rollback_manager
    _global_rollback_manager = None
