"""Step conditions for plan execution control."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepCondition:
    """
    Condition that must be met before a step can execute.
    
    Types:
    - file_exists: Check if a file or directory exists
    - output_contains: Check if previous step output contains text
    - previous_step_result: Check if previous step succeeded/failed
    """
    type: str  # "file_exists", "output_contains", "previous_step_result"
    expression: str
    description: str | None = None


@dataclass
class StepExecutionContext:
    """
    Context for tracking step execution history.
    
    This class maintains the history of executed steps and their results,
    allowing conditions to reference previous step outputs.
    """
    step_history: list[dict[str, Any]] = field(default_factory=list)
    
    def add_step_result(self, step_number: int, tool_name: str, args: dict, 
                        result: str, success: bool) -> None:
        """
        Record the result of a step execution.
        
        Args:
            step_number: The step number
            tool_name: Name of the tool executed
            args: Tool arguments
            result: Execution result string
            success: Whether the step succeeded
        """
        self.step_history.append({
            "step_number": step_number,
            "tool_name": tool_name,
            "args": args,
            "result": result,
            "success": success
        })
    
    def get_previous_step_result(self) -> dict[str, Any] | None:
        """
        Get the result of the most recently executed step.
        
        Returns:
            Dictionary with step info, or None if no steps have been executed
        """
        if not self.step_history:
            return None
        return self.step_history[-1]
    
    def get_step_result(self, step_number: int) -> dict[str, Any] | None:
        """
        Get the result of a specific step.
        
        Args:
            step_number: The step number to look up
            
        Returns:
            Dictionary with step info, or None if step not found
        """
        for entry in self.step_history:
            if entry["step_number"] == step_number:
                return entry
        return None
    
    def clear(self) -> None:
        """Clear the step history."""
        self.step_history.clear()


@dataclass
class PlanStep:
    """
    Extended plan step with conditions and rollback support.
    
    Attributes:
        step_number: Sequential step number
        description: Human-readable step description
        tool_name: Name of the tool to call
        args: Tool arguments
        reason: Why this step is needed
        conditions: Conditions that must be met before execution
        rollback_on_fail: Whether to rollback previous steps on failure
        status: Current status (pending, running, completed, failed)
        result: Execution result
    """
    step_number: int
    description: str
    tool_name: str
    args: dict[str, Any]
    reason: str = ""
    conditions: list[StepCondition] = field(default_factory=list)
    rollback_on_fail: bool = False
    status: str = "pending"  # "pending", "running", "completed", "failed"
    result: str | None = None

    def check_conditions(self, context: StepExecutionContext | None = None) -> bool:
        """
        Check if all conditions are met for this step.
        
        Args:
            context: Optional execution context for checking conditions that
                    require knowledge of previous step results.
                    
        Returns:
            True if all conditions pass or no conditions exist
        """
        import os

        for condition in self.conditions:
            if condition.type == "file_exists":
                if not os.path.exists(condition.expression):
                    return False
            elif condition.type == "output_contains":
                if not self._check_output_contains(condition.expression, context):
                    return False
            elif condition.type == "previous_step_result":
                if not self._check_previous_step_result(condition.expression, context):
                    return False
        return True
    
    def _check_output_contains(self, text: str, 
                                context: StepExecutionContext | None) -> bool:
        """
        Check if previous step output contains specified text.
        
        Args:
            text: Text to search for in previous step output
            context: Execution context containing step history
            
        Returns:
            True if text is found in previous output or no previous step exists
        """
        if context is None:
            return True
        
        previous = context.get_previous_step_result()
        if previous is None:
            return True
        
        result = previous.get("result", "")
        return text in str(result)
    
    def _check_previous_step_result(self, expression: str,
                                     context: StepExecutionContext | None) -> bool:
        """
        Check if previous step result matches the expression.
        
        Expression can be:
        - "success" or "succeeded" - previous step must have succeeded
        - "failed" or "failure" - previous step must have failed
        - A number (e.g., "123") - previous step number must match
        - "step_N" where N is a number - specific step must have succeeded
        
        Args:
            expression: The condition expression
            context: Execution context containing step history
            
        Returns:
            True if condition is satisfied or no previous step exists
        """
        if context is None:
            return True
        
        previous = context.get_previous_step_result()
        if previous is None:
            return True
        
        expr_lower = expression.lower().strip()
        
        if expr_lower in ("success", "succeeded"):
            return previous.get("success", False) is True
        
        if expr_lower in ("failed", "failure"):
            return previous.get("success", True) is False
        
        if expr_lower.startswith("step_"):
            try:
                step_num = int(expr_lower.split("_")[1])
                target_step = context.get_step_result(step_num)
                if target_step is None:
                    return False
                return target_step.get("success", False) is True
            except (ValueError, IndexError):
                return True
        
        return True

    def get_unmet_conditions(self, context: StepExecutionContext | None = None) -> list[StepCondition]:
        """Return list of conditions that are not met."""
        import os
        unmet = []
        for condition in self.conditions:
            if condition.type == "file_exists":
                if not os.path.exists(condition.expression):
                    unmet.append(condition)
            elif condition.type == "output_contains":
                if not self._check_output_contains(condition.expression, context):
                    unmet.append(condition)
            elif condition.type == "previous_step_result":
                if not self._check_previous_step_result(condition.expression, context):
                    unmet.append(condition)
        return unmet


def parse_step_conditions(step_config: dict) -> list[StepCondition]:
    """
    Parse step conditions from config dictionary.
    
    Args:
        step_config: Dictionary with 'conditions' key containing condition list
        
    Returns:
        List of StepCondition objects
    """
    conditions = []
    for cond in step_config.get("conditions", []):
        conditions.append(StepCondition(
            type=cond.get("type", ""),
            expression=cond.get("expression", ""),
            description=cond.get("description")
        ))
    return conditions


def create_step_from_config(config: dict, step_number: int) -> PlanStep:
    """
    Create a PlanStep from a configuration dictionary.
    
    Args:
        config: Step configuration with keys: description, tool_name, args, reason, conditions
        step_number: Sequential step number
        
    Returns:
        PlanStep object
    """
    return PlanStep(
        step_number=step_number,
        description=config.get("description", ""),
        tool_name=config.get("tool_name", ""),
        args=config.get("args", {}),
        reason=config.get("reason", ""),
        conditions=parse_step_conditions(config),
        rollback_on_fail=config.get("rollback_on_fail", False)
    )
