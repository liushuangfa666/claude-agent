"""Tests for plan module - verification, step_conditions, interview"""
import os
import tempfile

import pytest

from scripts.plan import (
    VerificationCriterion,
    VerificationResult,
    VerifyPlanExecutionTool,
    StepCondition,
    PlanStep,
    parse_step_conditions,
    create_step_from_config,
    InterviewPhase,
    RollbackAction,
    RollbackManager,
    get_rollback_manager,
    reset_rollback_manager,
)


class TestVerifyPlanExecutionTool:
    @pytest.mark.asyncio
    async def test_file_exists_pass(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            path = f.name
        try:
            tool = VerifyPlanExecutionTool()
            result = await tool.call({
                "verification_criteria": [
                    {"type": "file_exists", "target": path}
                ]
            }, {})
            assert result.success is True
            assert result.data["all_passed"] is True
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_file_exists_fail(self):
        tool = VerifyPlanExecutionTool()
        result = await tool.call({
            "verification_criteria": [
                {"type": "file_exists", "target": "/nonexistent/file.txt"}
            ]
        }, {})
        assert result.success is False
        assert result.data["all_passed"] is False

    @pytest.mark.asyncio
    async def test_file_contains_pass(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("hello world test content")
            path = f.name
        try:
            tool = VerifyPlanExecutionTool()
            result = await tool.call({
                "verification_criteria": [
                    {"type": "file_contains", "target": path, "expected": "hello"}
                ]
            }, {})
            assert result.success is True
            assert result.data["all_passed"] is True
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_file_contains_fail(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("hello world")
            path = f.name
        try:
            tool = VerifyPlanExecutionTool()
            result = await tool.call({
                "verification_criteria": [
                    {"type": "file_contains", "target": path, "expected": "goodbye"}
                ]
            }, {})
            assert result.success is False
            assert result.data["all_passed"] is False
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_command_succeeds(self):
        tool = VerifyPlanExecutionTool()
        result = await tool.call({
            "verification_criteria": [
                {"type": "command_succeeds", "target": "echo hello"}
            ]
        }, {})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_command_fails(self):
        tool = VerifyPlanExecutionTool()
        result = await tool.call({
            "verification_criteria": [
                {"type": "command_succeeds", "target": "exit 1"}
            ]
        }, {})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_multiple_criteria(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            path = f.name
        try:
            tool = VerifyPlanExecutionTool()
            result = await tool.call({
                "verification_criteria": [
                    {"type": "file_exists", "target": path},
                    {"type": "command_succeeds", "target": "echo test"}
                ]
            }, {})
            assert result.success is True
            assert result.data["passed_count"] == 2
            assert result.data["total_count"] == 2
        finally:
            os.unlink(path)


class TestStepConditions:
    def test_plan_step_default(self):
        step = PlanStep(
            step_number=1,
            description="Test step",
            tool_name="Read",
            args={"file_path": "test.txt"}
        )
        assert step.status == "pending"
        assert step.rollback_on_fail is False
        assert step.conditions == []

    def test_plan_step_with_conditions(self):
        conditions = [
            StepCondition(type="file_exists", expression="config.yaml"),
            StepCondition(type="output_contains", expression="success")
        ]
        step = PlanStep(
            step_number=1,
            description="Test step",
            tool_name="Bash",
            args={"command": "make test"},
            conditions=conditions,
            rollback_on_fail=True
        )
        assert len(step.conditions) == 2
        assert step.rollback_on_fail is True

    def test_check_conditions_file_exists(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            path = f.name
        try:
            conditions = [StepCondition(type="file_exists", expression=path)]
            step = PlanStep(1, "test", "Read", {}, conditions=conditions)
            assert step.check_conditions() is True

            step2 = PlanStep(2, "test", "Read", {}, conditions=[
                StepCondition(type="file_exists", expression="/nonexistent/file")
            ])
            assert step2.check_conditions() is False
        finally:
            os.unlink(path)

    def test_check_conditions_output_contains(self):
        from scripts.plan.step_conditions import StepExecutionContext
        
        context = StepExecutionContext()
        context.add_step_result(1, "Bash", {"command": "echo hello"}, "hello world", True)
        
        conditions = [StepCondition(type="output_contains", expression="hello")]
        step = PlanStep(2, "test", "Read", {}, conditions=conditions)
        
        assert step.check_conditions(context) is True
        
        conditions2 = [StepCondition(type="output_contains", expression="goodbye")]
        step2 = PlanStep(3, "test", "Read", {}, conditions=conditions2)
        assert step2.check_conditions(context) is False
        
        step3 = PlanStep(4, "test", "Read", {}, conditions=conditions2)
        assert step3.check_conditions(None) is True

    def test_check_conditions_previous_step_result_success(self):
        from scripts.plan.step_conditions import StepExecutionContext
        
        context = StepExecutionContext()
        context.add_step_result(1, "Bash", {"command": "make test"}, "Tests passed", True)
        
        conditions = [StepCondition(type="previous_step_result", expression="success")]
        step = PlanStep(2, "test", "Read", {}, conditions=conditions)
        
        assert step.check_conditions(context) is True
        
        conditions2 = [StepCondition(type="previous_step_result", expression="failed")]
        step2 = PlanStep(3, "test", "Read", {}, conditions=conditions2)
        assert step2.check_conditions(context) is False

    def test_check_conditions_previous_step_result_failed(self):
        from scripts.plan.step_conditions import StepExecutionContext
        
        context = StepExecutionContext()
        context.add_step_result(1, "Bash", {"command": "make test"}, "Build failed", False)
        
        conditions = [StepCondition(type="previous_step_result", expression="failed")]
        step = PlanStep(2, "test", "Read", {}, conditions=conditions)
        
        assert step.check_conditions(context) is True
        
        conditions2 = [StepCondition(type="previous_step_result", expression="success")]
        step2 = PlanStep(3, "test", "Read", {}, conditions=conditions2)
        assert step2.check_conditions(context) is False

    def test_check_conditions_previous_step_result_specific_step(self):
        from scripts.plan.step_conditions import StepExecutionContext
        
        context = StepExecutionContext()
        context.add_step_result(1, "Bash", {"command": "echo hello"}, "hello", True)
        context.add_step_result(2, "Bash", {"command": "make build"}, "Build failed", False)
        
        conditions = [StepCondition(type="previous_step_result", expression="step_1")]
        step = PlanStep(3, "test", "Read", {}, conditions=conditions)
        
        assert step.check_conditions(context) is True
        
        conditions2 = [StepCondition(type="previous_step_result", expression="step_2")]
        step2 = PlanStep(4, "test", "Read", {}, conditions=conditions2)
        assert step2.check_conditions(context) is False

    def test_step_execution_context(self):
        from scripts.plan.step_conditions import StepExecutionContext
        
        context = StepExecutionContext()
        
        context.add_step_result(1, "Bash", {"command": "echo test"}, "test", True)
        context.add_step_result(2, "Read", {"file_path": "test.txt"}, "content", True)
        
        prev = context.get_previous_step_result()
        assert prev is not None
        assert prev["step_number"] == 2
        assert prev["tool_name"] == "Read"
        
        step1 = context.get_step_result(1)
        assert step1 is not None
        assert step1["success"] is True
        
        step3 = context.get_step_result(3)
        assert step3 is None
        
        context.clear()
        assert context.get_previous_step_result() is None

    def test_parse_step_conditions(self):
        config = {
            "conditions": [
                {"type": "file_exists", "expression": "config.yaml"},
                {"type": "output_contains", "expression": "OK"}
            ]
        }
        conditions = parse_step_conditions(config)
        assert len(conditions) == 2
        assert conditions[0].type == "file_exists"
        assert conditions[1].expression == "OK"

    def test_create_step_from_config(self):
        config = {
            "description": "Run tests",
            "tool_name": "Bash",
            "args": {"command": "pytest"},
            "reason": "To verify code",
            "conditions": [{"type": "file_exists", "expression": "test_file.py"}]
        }
        step = create_step_from_config(config, 1)
        assert step.step_number == 1
        assert step.description == "Run tests"
        assert step.tool_name == "Bash"
        assert len(step.conditions) == 1


class TestInterviewPhase:
    def test_add_question(self):
        interview = InterviewPhase()
        q = interview.add_question("What is the target file?")
        assert q.question == "What is the target file?"
        assert q.answer is None

    def test_add_answer(self):
        interview = InterviewPhase()
        interview.add_question("What is the target file?")
        interview.add_answer("What is the target file?", "config.yaml")
        assert interview.answers["What is the target file?"] == "config.yaml"

    def test_pending_questions(self):
        interview = InterviewPhase()
        interview.add_question("Q1")
        interview.add_question("Q2")
        interview.add_answer("Q1", "A1")
        pending = interview.get_pending_questions()
        assert len(pending) == 1
        assert "Q2" in pending

    def test_answered_questions(self):
        interview = InterviewPhase()
        interview.add_question("Q1")
        interview.add_answer("Q1", "A1")
        answered = interview.get_answered_questions()
        assert len(answered) == 1
        assert answered[0]["answer"] == "A1"

    def test_is_complete(self):
        interview = InterviewPhase()
        interview.add_question("Q1")
        assert interview.is_complete() is False
        interview.add_answer("Q1", "A1")
        assert interview.is_complete() is True

    def test_user_feedback(self):
        interview = InterviewPhase()
        interview.add_user_feedback("Looks good!")
        assert "Looks good!" in interview.feedback

    def test_clear(self):
        interview = InterviewPhase()
        interview.add_question("Q1")
        interview.add_answer("Q1", "A1")
        interview.clear()
        assert len(interview.questions) == 0
        assert len(interview.answers) == 0

    def test_to_dict(self):
        interview = InterviewPhase()
        interview.add_question("Q1")
        interview.add_answer("Q1", "A1")
        d = interview.to_dict()
        assert d["pending_count"] == 0
        assert len(d["questions"]) == 1


class TestRollbackManager:
    def test_rollback_manager_record_step(self):
        from scripts.plan import RollbackManager
        
        manager = RollbackManager()
        manager.start_rollback_plan("Test task")
        
        manager.record_step(1, "Write", {"file_path": "test.txt", "content": "hello"}, "File written")
        
        plan = manager.get_current_plan()
        assert plan is not None
        assert len(plan.executed_steps) == 1
        assert plan.executed_steps[0]["step_number"] == 1

    def test_rollback_manager_generate_rollback_steps(self):
        from scripts.plan import RollbackManager, RollbackAction
        
        manager = RollbackManager()
        manager.start_rollback_plan("Test task")
        
        action = RollbackAction(
            step_number=1,
            tool_name="Write",
            args={"file_path": "test.txt"},
            result="File written",
            rollback_command="rm test.txt"
        )
        manager.add_rollback_action(action)
        
        steps = manager.generate_rollback_steps()
        assert len(steps) == 1
        assert steps[0]["tool_name"] == "Bash"
        assert steps[0]["args"]["command"] == "rm test.txt"

    def test_rollback_manager_reverse_order(self):
        from scripts.plan import RollbackManager, RollbackAction
        
        manager = RollbackManager()
        manager.start_rollback_plan("Test task")
        
        manager.add_rollback_action(RollbackAction(
            step_number=1, tool_name="Write", args={},
            rollback_command="rm file1.txt"
        ))
        manager.add_rollback_action(RollbackAction(
            step_number=2, tool_name="Write", args={},
            rollback_command="rm file2.txt"
        ))
        
        steps = manager.generate_rollback_steps()
        assert len(steps) == 2
        assert "file2.txt" in steps[0]["args"]["command"]
        assert "file1.txt" in steps[1]["args"]["command"]

    def test_rollback_manager_clear(self):
        from scripts.plan import RollbackManager
        
        manager = RollbackManager()
        manager.start_rollback_plan("Test task")
        manager.clear()
        
        assert manager.get_current_plan() is None

    def test_get_rollback_manager_singleton(self):
        from scripts.plan import get_rollback_manager, reset_rollback_manager
        
        reset_rollback_manager()
        m1 = get_rollback_manager()
        m2 = get_rollback_manager()
        assert m1 is m2
        reset_rollback_manager()
