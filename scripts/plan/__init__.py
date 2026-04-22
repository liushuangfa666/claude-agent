"""Plan module for plan mode and verification.

This module provides:
- verification: VerifyPlanExecutionTool for checking plan execution
- step_conditions: PlanStep with conditions and rollback support
- rollback: RollbackManager for undoing failed plan steps
- interview: InterviewPhase for clarifying questions during planning
"""

from .interview import InterviewPhase, InterviewQuestion
from .rollback import RollbackAction, RollbackManager, RollbackPlan, get_rollback_manager, reset_rollback_manager
from .step_conditions import PlanStep, StepCondition, StepExecutionContext, create_step_from_config, parse_step_conditions
from .verification import VerificationCriterion, VerificationResult, VerifyPlanExecutionTool

__all__ = [
    "VerifyPlanExecutionTool",
    "VerificationCriterion",
    "VerificationResult",
    "StepCondition",
    "StepExecutionContext",
    "PlanStep",
    "parse_step_conditions",
    "create_step_from_config",
    "InterviewPhase",
    "InterviewQuestion",
    "RollbackAction",
    "RollbackManager",
    "RollbackPlan",
    "get_rollback_manager",
    "reset_rollback_manager",
]
