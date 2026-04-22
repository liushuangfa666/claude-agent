"""Plan verification module for verifying plan execution."""
from dataclasses import dataclass
from typing import Literal

try:
    from tool import BaseTool, ToolResult
except ImportError:
    from scripts.tool import BaseTool, ToolResult


@dataclass
class VerificationCriterion:
    """A single verification criterion for checking plan execution."""
    type: Literal["file_exists", "file_contains", "command_succeeds", "task_status"]
    target: str
    expected: str | None = None
    description: str = ""


@dataclass
class VerificationResult:
    """Result of verifying a single criterion."""
    criterion: VerificationCriterion
    passed: bool
    actual: str | None = None
    error: str | None = None


class VerifyPlanExecutionTool(BaseTool):
    """
    Verify that a plan was executed correctly by checking verification criteria.
    
    This tool checks:
    - file_exists: Verify a file or directory exists
    - file_contains: Verify a file contains specific content
    - command_succeeds: Verify a command exits with code 0
    - task_status: Verify a task has a specific status
    """

    name = "VerifyPlanExecution"
    description = "Verify that a plan was executed correctly by checking verification criteria"
    input_schema = {
        "type": "object",
        "properties": {
            "verification_criteria": {
                "type": "array",
                "description": "List of verification criteria to check",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["file_exists", "file_contains", "command_succeeds", "task_status"],
                            "description": "Type of verification"
                        },
                        "target": {"type": "string", "description": "Target file path, command, or task ID"},
                        "expected": {"type": "string", "description": "Expected content or value (optional)"},
                        "description": {"type": "string", "description": "Human-readable description of this criterion"}
                    },
                    "required": ["type", "target"]
                }
            },
            "plan_id": {"type": "string", "description": "Optional plan ID for reference"}
        },
        "required": ["verification_criteria"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        criteria = args.get("verification_criteria", [])
        results: list[VerificationResult] = []

        for criterion_data in criteria:
            criterion = VerificationCriterion(
                type=criterion_data.get("type", ""),
                target=criterion_data.get("target", ""),
                expected=criterion_data.get("expected"),
                description=criterion_data.get("description", "")
            )
            try:
                result = await self._verify_single(criterion)
                results.append(result)
            except Exception as e:
                results.append(VerificationResult(
                    criterion=criterion,
                    passed=False,
                    error=str(e)
                ))

        all_passed = all(r.passed for r in results)

        return ToolResult(
            success=all_passed,
            data={
                "results": [
                    {
                        "type": r.criterion.type,
                        "target": r.criterion.target,
                        "passed": r.passed,
                        "actual": r.actual,
                        "error": r.error,
                        "description": r.criterion.description
                    }
                    for r in results
                ],
                "all_passed": all_passed,
                "passed_count": sum(1 for r in results if r.passed),
                "total_count": len(results)
            }
        )

    async def _verify_single(self, criterion: VerificationCriterion) -> VerificationResult:
        """Verify a single criterion."""
        import os
        import subprocess

        ctype = criterion.type
        target = criterion.target

        if ctype == "file_exists":
            passed = os.path.exists(target)
            is_dir = os.path.isdir(target) if passed else False
            is_file = os.path.isfile(target) if passed else False
            return VerificationResult(
                criterion=criterion,
                passed=passed,
                actual=f"{'directory' if is_dir else 'file' if is_file else 'not found'}"
            )

        elif ctype == "file_contains":
            if not os.path.exists(target):
                return VerificationResult(
                    criterion=criterion,
                    passed=False,
                    error="File not found"
                )
            if not os.path.isfile(target):
                return VerificationResult(
                    criterion=criterion,
                    passed=False,
                    error="Target is not a file"
                )
            try:
                with open(target, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                found = criterion.expected in content if criterion.expected else True
                return VerificationResult(
                    criterion=criterion,
                    passed=found,
                    actual="found" if found else "not found"
                )
            except Exception as e:
                return VerificationResult(
                    criterion=criterion,
                    passed=False,
                    error=str(e)
                )

        elif ctype == "command_succeeds":
            try:
                result = subprocess.run(
                    target,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                passed = result.returncode == 0
                return VerificationResult(
                    criterion=criterion,
                    passed=passed,
                    actual=f"exit_code={result.returncode}"
                )
            except subprocess.TimeoutExpired:
                return VerificationResult(
                    criterion=criterion,
                    passed=False,
                    error="Command timed out after 30 seconds"
                )
            except Exception as e:
                return VerificationResult(
                    criterion=criterion,
                    passed=False,
                    error=str(e)
                )

        elif ctype == "task_status":
            valid_statuses = ["pending", "in_progress", "completed", "failed", "killed"]
            passed = target in valid_statuses
            return VerificationResult(
                criterion=criterion,
                passed=passed,
                actual=target if target in valid_statuses else "invalid_status"
            )

        return VerificationResult(
            criterion=criterion,
            passed=False,
            error=f"Unknown criterion type: {ctype}"
        )
