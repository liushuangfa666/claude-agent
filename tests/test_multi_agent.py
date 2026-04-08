"""
Multi-Agent 系统测试

测试 multi_agent 模块的所有核心功能：
- 路由决策
- 任务分解
- 审核机制
- 执行流程
- Session 管理
- 端到端集成
"""

import asyncio
import json
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from scripts.multi_agent import (
    # 枚举
    ComplexityLevel,
    TaskStatus,
    ConstraintType,
    # 模型
    Constraint,
    Issue,
    ReviewResult,
    RollbackPlan,
    Task,
    ExecutionPlan,
    CrossDomainDep,
    SubdomainPlan,
    SubdomainResult,
    L3Plan,
    ExecutionResult,
    RouteResult,
    FORBIDDEN_ACTIONS,
    # 路由
    HybridRouter,
    route_simple,
    # Decomposer
    L2Decomposer,
    L3TopDecomposer,
    L3SubDecomposer,
    # Reviewer
    L2Reviewer,
    L3Reviewer,
    # Executor
    L2Executor,
    L3Executor,
    TaskResult,
    # Session
    LayerSession,
    LayerContextManager,
    MultiAgentSessionManager,
    # Execute
    MultiAgentExecutor,
    execute_simple,
)


class TestModels:
    """测试核心数据模型"""

    def test_complexity_level_enum(self):
        """测试复杂度枚举"""
        assert ComplexityLevel.L1.value == "L1"
        assert ComplexityLevel.L2.value == "L2"
        assert ComplexityLevel.L3.value == "L3"
        assert len(ComplexityLevel) == 3

    def test_task_status_enum(self):
        """测试任务状态枚举"""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.ROLLED_BACK.value == "rolled_back"
        assert TaskStatus.WAITING.value == "waiting"

    def test_constraint_type_enum(self):
        """测试约束类型枚举"""
        assert ConstraintType.FILE_SCOPE.value == "file_scope"
        assert ConstraintType.DEPENDS_ON.value == "depends_on"
        assert ConstraintType.ROLLBACK_REQUIRED.value == "rollback_required"
        assert ConstraintType.FORBIDDEN.value == "forbidden"

    def test_constraint_creation(self):
        """测试约束创建"""
        constraint = Constraint(
            type=ConstraintType.FILE_SCOPE,
            description="只允许修改这些文件",
            files=["src/a.py", "src/b.py"]
        )
        assert constraint.type == ConstraintType.FILE_SCOPE
        assert len(constraint.files) == 2
        assert constraint.to_dict()["files"] == ["src/a.py", "src/b.py"]

    def test_issue_creation(self):
        """测试问题创建"""
        issue = Issue(
            type="file_conflict",
            severity="critical",
            details={"file": "a.py", "tasks": ["t1", "t2"]},
            resolution="重新划分文件边界",
            task_id="task-1"
        )
        assert issue.type == "file_conflict"
        assert issue.severity == "critical"
        assert issue.task_id == "task-1"

    def test_task_creation_and_methods(self):
        """测试任务创建和方法"""
        task = Task(
            id="task-1",
            description="修复登录bug",
            target_files=["src/auth.py"],
            estimated_steps=3,
        )
        assert task.id == "task-1"
        assert task.status == TaskStatus.PENDING
        
        # 测试 is_ready 方法
        assert task.is_ready(set()) is True
        assert task.is_ready({"task-1"}) is True
        
        # 测试 add_constraint
        constraint = Constraint(
            type=ConstraintType.FILE_SCOPE,
            description="test",
            files=["test.py"]
        )
        task.add_constraint(constraint)
        assert len(task.constraints) == 1

    def test_task_is_ready_with_dependencies(self):
        """测试任务依赖检查"""
        task = Task(
            id="task-2",
            description="第二步",
            dependencies=["task-1", "task-0"]
        )
        assert task.is_ready({"task-1", "task-0"}) is True
        assert task.is_ready({"task-1"}) is False
        assert task.is_ready(set()) is False

    def test_execution_plan_topological_sort(self):
        """测试执行计划拓扑排序"""
        task1 = Task(id="t1", description="任务1", dependencies=[])
        task2 = Task(id="t2", description="任务2", dependencies=["t1"])
        task3 = Task(id="t3", description="任务3", dependencies=["t1"])
        task4 = Task(id="t4", description="任务4", dependencies=["t2", "t3"])
        
        plan = ExecutionPlan(
            id="plan-1",
            level=ComplexityLevel.L2,
            tasks=[task4, task2, task1, task3]  # 乱序
        )
        
        sorted_tasks = plan.topological_sort()
        sorted_ids = [t.id for t in sorted_tasks]
        
        # t1 应该在 t2, t3 之前
        assert sorted_ids.index("t1") < sorted_ids.index("t2")
        assert sorted_ids.index("t1") < sorted_ids.index("t3")
        # t2, t3 应该在 t4 之前
        assert sorted_ids.index("t2") < sorted_ids.index("t4")
        assert sorted_ids.index("t3") < sorted_ids.index("t4")

    def test_execution_plan_get_task(self):
        """测试获取任务"""
        task1 = Task(id="t1", description="任务1")
        plan = ExecutionPlan(
            id="plan-1",
            level=ComplexityLevel.L1,
            tasks=[task1]
        )
        
        assert plan.get_task("t1") == task1
        assert plan.get_task("nonexistent") is None

    def test_review_result_properties(self):
        """测试审核结果属性"""
        issues = [
            Issue(type="issue1", severity="critical"),
            Issue(type="issue2", severity="high"),
            Issue(type="issue3", severity="medium"),
        ]
        
        result = ReviewResult(
            approved=False,
            issues=issues,
            requires_redo=True
        )
        
        assert len(result.critical_issues) == 1
        assert len(result.high_issues) == 1
        assert result.get_rejection_reasons()[0] == "[critical] issue1"

    def test_forbidden_actions_list(self):
        """测试危险操作列表"""
        assert "rm -rf" in FORBIDDEN_ACTIONS
        assert "DROP TABLE" in FORBIDDEN_ACTIONS
        assert "git push --force" in FORBIDDEN_ACTIONS

    def test_route_result_to_dict(self):
        """测试路由结果序列化"""
        result = RouteResult(
            level=ComplexityLevel.L2,
            reasoning="中权重规则触发",
            confidence=0.85,
            method="rule_based",
            estimated_tasks=5
        )
        
        d = result.to_dict()
        assert d["level"] == "L2"
        assert d["confidence"] == 0.85
        assert d["estimated_tasks"] == 5


class TestRouter:
    """测试路由功能"""

    def test_route_simple_l1_single_fix(self):
        """测试简单修复路由到 L1"""
        result = route_simple("帮我修复这个bug")
        assert result.level == ComplexityLevel.L1
        assert result.method == "rule_based"

    def test_route_simple_l1_single_file(self):
        """测试单文件任务路由到 L1"""
        result = route_simple("修改 config.py 中的配置")
        assert result.level == ComplexityLevel.L1

    def test_route_simple_l2_frontend_backend(self):
        """测试前后端任务路由到 L2"""
        result = route_simple("同时更新前端和后端API")
        assert result.level == ComplexityLevel.L2

    def test_route_simple_l2_multiple(self):
        """测试多步骤任务路由到 L2"""
        result = route_simple("分别处理这三个文件的改动")
        assert result.level == ComplexityLevel.L2

    def test_route_simple_l3_delete(self):
        """测试删除操作路由到 L3"""
        result = route_simple("清空这个目录")
        assert result.level == ComplexityLevel.L3

    def test_route_simple_l3_refactor(self):
        """测试重构任务路由到 L3"""
        result = route_simple("重构整个数据库层")
        assert result.level == ComplexityLevel.L3

    def test_route_simple_l3_architecture(self):
        """测试架构设计任务路由到 L3"""
        result = route_simple("设计微服务架构")
        assert result.level == ComplexityLevel.L3

    def test_route_simple_l3_production(self):
        """测试生产环境任务路由到 L3"""
        result = route_simple("发布到生产环境")
        assert result.level == ComplexityLevel.L3

    def test_route_simple_confidence(self):
        """测试路由置信度"""
        # 高权重规则应该有高置信度
        result = route_simple("删除所有测试文件")
        assert result.confidence >= 0.9
        
        # 低权重规则应该有低置信度
        result = route_simple("hello world")
        assert result.confidence < 0.9

    def test_hybrid_router_init(self):
        """测试混合路由器初始化"""
        router = HybridRouter()
        assert router.llm_client is None
        
        mock_client = MagicMock()
        router = HybridRouter(mock_client)
        assert router.llm_client == mock_client

    def test_hybrid_router_rule_based_high_confidence(self):
        """测试高置信度规则判断"""
        router = HybridRouter()
        result = router._rule_based_route("删除用户数据")
        
        assert result.confidence == 0.95
        assert result.level == ComplexityLevel.L3
        assert result.method == "rule_based"

    def test_hybrid_router_llm_fallback(self):
        """测试 LLM 辅助判断回退"""
        router = HybridRouter()  # 没有 LLM 客户端
        
        result = asyncio.run(router.route("做一些复杂的事情"))
        
        # 没有 LLM 客户端时回退到规则判断
        assert result.method == "rule_based"


class TestDecomposer:
    """测试任务分解器"""

    @pytest.mark.asyncio
    async def test_l2_decomposer_without_llm(self):
        """测试 L2 分解器（无 LLM）"""
        decomposer = L2Decomposer()
        
        task = Task(
            id="task-1",
            description="实现登录功能",
            target_files=["src/auth.py", "src/login.py"]
        )
        
        plan = await decomposer.decompose(task)
        
        assert plan.level == ComplexityLevel.L2
        assert len(plan.tasks) >= 1
        assert plan.tasks[0].constraints is not None

    @pytest.mark.asyncio
    async def test_l2_decomposer_constraints(self):
        """测试 L2 分解器生成的约束"""
        decomposer = L2Decomposer()
        
        task = Task(
            id="task-1",
            description="实现登录功能",
            target_files=["src/auth.py"]
        )
        
        plan = await decomposer.decompose(task)
        
        # 检查约束类型
        constraint_types = [c.type for c in plan.tasks[0].constraints]
        assert ConstraintType.FILE_SCOPE in constraint_types
        assert ConstraintType.ROLLBACK_REQUIRED in constraint_types
        assert ConstraintType.FORBIDDEN in constraint_types

    @pytest.mark.asyncio
    async def test_l2_decomposer_with_llm_mock(self):
        """测试 L2 分解器（带 LLM Mock）"""
        mock_client = AsyncMock()
        mock_client.complete.return_value = '{"subtasks": [{"description": "子任务1", "target_files": ["a.py"], "estimated_steps": 2, "dependencies": []}]}'
        
        decomposer = L2Decomposer(mock_client)
        
        task = Task(
            id="task-1",
            description="实现登录功能"
        )
        
        plan = await decomposer.decompose(task)
        
        # 应该调用 LLM
        mock_client.complete.assert_called_once()

    def test_create_constraints_file_scope(self):
        """测试文件边界约束创建"""
        decomposer = L2Decomposer()
        
        subtask = Task(
            id="st1",
            description="修改文件",
            target_files=["a.py", "b.py"]
        )
        
        constraints = decomposer.create_constraints(subtask)
        
        file_scope = next(c for c in constraints if c.type == ConstraintType.FILE_SCOPE)
        assert file_scope.files == ["a.py", "b.py"]

    def test_create_constraints_dependencies(self):
        """测试依赖约束创建"""
        decomposer = L2Decomposer()
        
        subtask = Task(
            id="st1",
            description="第二步",
            dependencies=["st0"]
        )
        
        constraints = decomposer.create_constraints(subtask)
        
        depends = next(c for c in constraints if c.type == ConstraintType.DEPENDS_ON)
        assert depends.tasks == ["st0"]

    @pytest.mark.asyncio
    async def test_l3_top_decomposer(self):
        """测试 L3 顶级分解器"""
        decomposer = L3TopDecomposer()
        
        task = Task(
            id="task-1",
            description="实现完整系统"
        )
        
        plan = await decomposer.decompose(task)
        
        assert isinstance(plan, L3Plan)
        assert len(plan.subdomains) >= 1
        assert plan.global_constraints is not None

    @pytest.mark.asyncio
    async def test_l3_sub_decomposer(self):
        """测试 L3 子域分解器"""
        subdomain_plan = SubdomainPlan(
            subdomain_id="frontend",
            tasks=[
                Task(id="t1", description="任务1"),
                Task(id="t2", description="任务2", dependencies=["t1"])
            ],
            local_constraints=[],
            provides=["API定义"],
            depends_on=[]
        )
        
        decomposer = L3SubDecomposer(subdomain_plan)
        execution_plan = await decomposer.decompose()
        
        # 拓扑排序后 t1 应该在 t2 之前
        sorted_ids = [t.id for t in execution_plan.tasks]
        assert sorted_ids.index("t1") < sorted_ids.index("t2")

    @pytest.mark.asyncio
    async def test_l2_decomposer_llm_split_decision(self):
        """测试 LLM 拆分决策"""
        mock_client = AsyncMock()
        mock_client.complete.return_value = json.dumps({
            "reasoning": "这是一个简单任务，不需要拆分",
            "should_split": False,
            "subtasks": []
        })

        decomposer = L2Decomposer(mock_client)

        task = Task(
            id="task-1",
            description="修复这个bug",
            target_files=["a.py"]
        )

        should_split, subtasks = await decomposer._analyze_and_split(task)

        assert should_split is False
        assert len(subtasks) == 1
        assert subtasks[0].id == "task-1"

    @pytest.mark.asyncio
    async def test_l2_decomposer_llm_split_multiple(self):
        """测试 LLM 拆分为多个任务"""
        mock_client = AsyncMock()
        mock_client.complete.return_value = json.dumps({
            "reasoning": "这个任务可以拆分为两个独立子任务",
            "should_split": True,
            "subtasks": [
                {
                    "id": "step_1",
                    "description": "修改前端代码",
                    "target_files": ["frontend.py"],
                    "estimated_steps": 2,
                    "depends_on": []
                },
                {
                    "id": "step_2",
                    "description": "修改后端代码",
                    "target_files": ["backend.py"],
                    "estimated_steps": 2,
                    "depends_on": []
                }
            ]
        })

        decomposer = L2Decomposer(mock_client)

        task = Task(
            id="task-1",
            description="实现前后端功能"
        )

        should_split, subtasks = await decomposer._analyze_and_split(task)

        assert should_split is True
        assert len(subtasks) == 2
        assert subtasks[0].description == "修改前端代码"
        assert subtasks[1].description == "修改后端代码"

    def test_parse_split_response(self):
        """测试解析拆分响应"""
        decomposer = L2Decomposer()

        response = json.dumps({
            "reasoning": "test",
            "should_split": True,
            "subtasks": [{"id": "s1", "description": "test"}]
        })

        data = decomposer._parse_split_response(response)

        assert data["should_split"] is True
        assert len(data["subtasks"]) == 1


class TestReviewer:
    """测试审核 Agent"""

    @pytest.mark.asyncio
    async def test_l2_reviewer_approve_clean_plan(self):
        """测试 L2 审核器通过干净的计划"""
        reviewer = L2Reviewer()
        
        task1 = Task(
            id="t1",
            description="实现功能A",
            target_files=["a.py"],
            has_rollback_plan=True
        )
        
        plan = ExecutionPlan(
            id="plan-1",
            level=ComplexityLevel.L2,
            tasks=[task1]
        )
        
        result = await reviewer.approve(plan)
        
        assert result.approved is True
        assert len(result.issues) == 0

    @pytest.mark.asyncio
    async def test_l2_reviewer_detect_file_conflict(self):
        """测试 L2 审核器检测文件冲突"""
        reviewer = L2Reviewer()
        
        task1 = Task(
            id="t1",
            description="修改文件A",
            target_files=["shared.py"],
            has_rollback_plan=True
        )
        task2 = Task(
            id="t2",
            description="也修改文件A",
            target_files=["shared.py"],
            has_rollback_plan=True
        )
        
        plan = ExecutionPlan(
            id="plan-1",
            level=ComplexityLevel.L2,
            tasks=[task1, task2]
        )
        
        result = await reviewer.approve(plan)
        
        assert result.approved is False
        conflict_issues = [i for i in result.issues if i.type == "file_conflict"]
        assert len(conflict_issues) == 1

    @pytest.mark.asyncio
    async def test_l2_reviewer_detect_missing_dependency(self):
        """测试 L2 审核器检测缺失依赖"""
        reviewer = L2Reviewer()
        
        task1 = Task(
            id="t1",
            description="第二步",
            dependencies=["nonexistent-task"],
            has_rollback_plan=True
        )
        
        plan = ExecutionPlan(
            id="plan-1",
            level=ComplexityLevel.L2,
            tasks=[task1]
        )
        
        result = await reviewer.approve(plan)
        
        assert result.approved is False
        dep_issues = [i for i in result.issues if i.type == "missing_dependency"]
        assert len(dep_issues) == 1

    @pytest.mark.asyncio
    async def test_l2_reviewer_detect_dangerous_operation(self):
        """测试 L2 审核器检测危险操作"""
        reviewer = L2Reviewer()
        
        task1 = Task(
            id="t1",
            description="执行 rm -rf /tmp/test",
            has_rollback_plan=True
        )
        
        plan = ExecutionPlan(
            id="plan-1",
            level=ComplexityLevel.L2,
            tasks=[task1]
        )
        
        result = await reviewer.approve(plan)
        
        assert result.approved is False
        dangerous_issues = [i for i in result.issues if i.type == "dangerous_operation"]
        assert len(dangerous_issues) >= 1

    @pytest.mark.asyncio
    async def test_l2_reviewer_detect_no_rollback_plan(self):
        """测试 L2 审核器检测缺失回滚计划"""
        reviewer = L2Reviewer()
        
        task1 = Task(
            id="t1",
            description="危险操作",
            has_rollback_plan=False
        )
        
        plan = ExecutionPlan(
            id="plan-1",
            level=ComplexityLevel.L2,
            tasks=[task1]
        )
        
        result = await reviewer.approve(plan)
        
        assert result.approved is False
        rollback_issues = [i for i in result.issues if i.type == "no_rollback_plan"]
        assert len(rollback_issues) == 1

    @pytest.mark.asyncio
    async def test_l2_final_approve_success(self):
        """测试 L2 最终审核成功"""
        reviewer = L2Reviewer()
        
        summary = "所有任务完成，没有失败"
        
        result = await reviewer.final_approve(summary)
        
        assert result.approved is True

    @pytest.mark.asyncio
    async def test_l2_final_approve_failure(self):
        """测试 L2 最终审核失败"""
        reviewer = L2Reviewer()
        
        summary = "任务1 failed，任务2 成功"
        
        result = await reviewer.final_approve(summary)
        
        assert result.approved is False

    @pytest.mark.asyncio
    async def test_l3_reviewer_approve_global(self):
        """测试 L3 全局审核"""
        reviewer = L3Reviewer()
        
        subdomain1 = SubdomainPlan(
            subdomain_id="frontend",
            tasks=[],
            local_constraints=[],
            provides=[],
            depends_on=[],
            allowed_files=["src/frontend/**"]
        )
        subdomain2 = SubdomainPlan(
            subdomain_id="backend",
            tasks=[],
            local_constraints=[],
            provides=[],
            depends_on=[],
            allowed_files=["src/backend/**"]
        )
        
        plan = L3Plan(
            subdomains=[subdomain1, subdomain2],
            cross_domain_dependencies=[],
            global_review_criteria=[],
            global_constraints=[]
        )
        
        result = await reviewer.approve_global(plan)
        
        # 没有重叠，没有循环依赖，应该通过
        assert result.approved is True

    @pytest.mark.asyncio
    async def test_l3_reviewer_detect_circular_dependency(self):
        """测试 L3 审核器检测循环依赖"""
        reviewer = L3Reviewer()
        
        deps = [
            CrossDomainDep(source_subdomain="a", target_subdomain="b"),
            CrossDomainDep(source_subdomain="b", target_subdomain="c"),
            CrossDomainDep(source_subdomain="c", target_subdomain="a"),  # 循环！
        ]
        
        result = reviewer._has_circular_dependency(deps)
        
        assert result is True

    @pytest.mark.asyncio
    async def test_l3_reviewer_detect_subdomain_overlap(self):
        """测试 L3 审核器检测子域重叠"""
        reviewer = L3Reviewer()
        
        subdomain1 = SubdomainPlan(
            subdomain_id="frontend",
            tasks=[],
            local_constraints=[],
            provides=[],
            depends_on=[],
            allowed_files=["src/shared/"]
        )
        subdomain2 = SubdomainPlan(
            subdomain_id="backend",
            tasks=[],
            local_constraints=[],
            provides=[],
            depends_on=[],
            allowed_files=["src/shared/"]  # 重叠！
        )
        
        plan = L3Plan(
            subdomains=[subdomain1, subdomain2],
            cross_domain_dependencies=[],
            global_review_criteria=[],
            global_constraints=[]
        )
        
        result = await reviewer.approve_global(plan)
        
        assert result.approved is False
        overlap_issues = [i for i in result.issues if i.type == "subdomain_overlap"]
        assert len(overlap_issues) == 1

    @pytest.mark.asyncio
    async def test_l3_reviewer_approve_subdomain(self):
        """测试 L3 子域审核"""
        reviewer = L3Reviewer()
        
        result = SubdomainResult(
            subdomain_id="frontend",
            status=TaskStatus.COMPLETED,
            completed=True,
            has_rollback_capability=True
        )
        
        review_result = await reviewer.approve_subdomain(result)
        
        assert review_result.approved is True

    @pytest.mark.asyncio
    async def test_l3_reviewer_approve_final(self):
        """测试 L3 最终审核"""
        reviewer = L3Reviewer()
        
        results = [
            SubdomainResult(
                subdomain_id="frontend",
                status=TaskStatus.COMPLETED,
                completed=True,
                has_rollback_capability=True
            ),
            SubdomainResult(
                subdomain_id="backend",
                status=TaskStatus.COMPLETED,
                completed=True,
                has_rollback_capability=True
            )
        ]
        
        result = await reviewer.approve_final(results)
        
        assert result.approved is True

    @pytest.mark.asyncio
    async def test_l3_reviewer_approve_final_incomplete(self):
        """测试 L3 最终审核失败（子域未完成）"""
        reviewer = L3Reviewer()
        
        results = [
            SubdomainResult(
                subdomain_id="frontend",
                status=TaskStatus.COMPLETED,
                completed=True,
                has_rollback_capability=True
            ),
            SubdomainResult(
                subdomain_id="backend",
                status=TaskStatus.IN_PROGRESS,
                completed=False,
                has_rollback_capability=True
            )
        ]
        
        result = await reviewer.approve_final(results)
        
        assert result.approved is False


class TestExecutor:
    """测试执行 Agent"""

    @pytest.mark.asyncio
    async def test_l2_executor_execute_success(self):
        """测试 L2 执行器成功执行"""
        executor = L2Executor()
        
        task = Task(
            id="t1",
            description="实现功能",
            has_rollback_plan=True
        )
        
        result = await executor.execute(task)
        
        assert result.status == "completed"
        assert result.task_id == "t1"

    @pytest.mark.asyncio
    async def test_l2_executor_with_llm_mock(self):
        """测试 L2 执行器（带 LLM Mock）"""
        mock_client = AsyncMock()
        mock_client.complete.return_value = "执行完成"
        
        executor = L2Executor(mock_client)
        
        task = Task(
            id="t1",
            description="实现功能",
            has_rollback_plan=True
        )
        
        result = await executor.execute(task)
        
        assert result.status == "completed"
        mock_client.complete.assert_called_once()

    def test_l2_executor_format_constraints(self):
        """测试约束格式化"""
        executor = L2Executor()
        
        constraints = [
            Constraint(
                type=ConstraintType.FILE_SCOPE,
                description="文件边界",
                files=["a.py", "b.py"]
            ),
            Constraint(
                type=ConstraintType.FORBIDDEN,
                description="禁止操作",
                actions=["rm -rf"]
            )
        ]
        
        formatted = executor._format_constraints(constraints)
        
        assert "文件边界" in formatted
        assert "a.py" in formatted
        assert "rm -rf" in formatted

    @pytest.mark.asyncio
    async def test_l3_executor_register_subdomain_output(self):
        """测试 L3 执行器注册子域输出"""
        executor = L3Executor()
        
        executor.register_subdomain_output("frontend", {"html": "content"})
        
        assert "frontend" in executor.subdomain_outputs
        assert executor.subdomain_outputs["frontend"]["html"] == "content"

    def test_l3_executor_is_subdomain_output_ready(self):
        """测试检查子域输出是否就绪"""
        executor = L3Executor()
        
        assert executor._is_subdomain_output_ready("nonexistent") is True
        assert executor._is_subdomain_output_ready("subdomain:frontend") is False
        
        executor.register_subdomain_output("frontend", {})
        assert executor._is_subdomain_output_ready("subdomain:frontend") is True

    def test_group_by_dependencies_no_dependencies(self):
        """测试无依赖任务分组"""
        executor = L2Executor()

        tasks = [
            Task(id="t1", description="任务1"),
            Task(id="t2", description="任务2"),
            Task(id="t3", description="任务3"),
        ]

        batches = executor._group_by_dependencies(tasks)

        # 所有任务应该在同一批次（可并行）
        assert len(batches) == 1
        assert len(batches[0]) == 3

    def test_group_by_dependencies_with_dependencies(self):
        """测试有依赖任务分组"""
        executor = L2Executor()

        tasks = [
            Task(id="t1", description="任务1", dependencies=[]),
            Task(id="t2", description="任务2", dependencies=["t1"]),
            Task(id="t3", description="任务3", dependencies=["t1"]),
            Task(id="t4", description="任务4", dependencies=["t2", "t3"]),
        ]

        batches = executor._group_by_dependencies(tasks)

        # 应该有三批：第一批 t1，第二批 t2/t3，第三批 t4
        assert len(batches) == 3
        assert [t.id for t in batches[0]] == ["t1"]
        assert set(t.id for t in batches[1]) == {"t2", "t3"}
        assert [t.id for t in batches[2]] == ["t4"]

    def test_group_by_dependencies_circular(self):
        """测试循环依赖处理"""
        executor = L2Executor()

        # 创建有循环依赖的任务（t1 -> t2 -> t3 -> t1）
        tasks = [
            Task(id="t1", description="任务1", dependencies=["t3"]),
            Task(id="t2", description="任务2", dependencies=["t1"]),
            Task(id="t3", description="任务3", dependencies=["t2"]),
        ]

        batches = executor._group_by_dependencies(tasks)

        # 循环依赖情况下，所有任务应该被合并到一批
        assert len(batches) == 1
        assert len(batches[0]) == 3

    @pytest.mark.asyncio
    async def test_execute_parallel_all_success(self):
        """测试并行执行全部成功"""
        executor = L2Executor()

        tasks = [
            Task(id="t1", description="任务1", dependencies=[]),
            Task(id="t2", description="任务2", dependencies=[]),
        ]

        results = await executor.execute_parallel(tasks)

        assert len(results) == 2
        assert all(r.status == "completed" for r in results)

    @pytest.mark.asyncio
    async def test_execute_parallel_with_dependencies(self):
        """测试有依赖的并行执行"""
        executor = L2Executor()

        tasks = [
            Task(id="t1", description="任务1", dependencies=[]),
            Task(id="t2", description="任务2", dependencies=["t1"]),
            Task(id="t3", description="任务3", dependencies=["t1"]),
        ]

        results = await executor.execute_parallel(tasks)

        assert len(results) == 3
        assert all(r.status == "completed" for r in results)

    @pytest.mark.asyncio
    async def test_l3_executor_execute_subdomain_parallel(self):
        """测试 L3 执行器子域并行执行"""
        executor = L3Executor()

        subdomain_plan = MagicMock()
        subdomain_plan.subdomain_id = "test_subdomain"

        tasks = [
            Task(id="t1", description="任务1", dependencies=[]),
            Task(id="t2", description="任务2", dependencies=[]),
        ]

        result = await executor.execute_subdomain_parallel(subdomain_plan, tasks)

        assert result.completed is True
        assert result.status == TaskStatus.COMPLETED
        assert len(result.completed_tasks) == 2
        assert len(result.failed_tasks) == 0


class TestSession:
    """测试 Session 管理"""

    def test_layer_session_creation(self):
        """测试 LayerSession 创建"""
        session = LayerSession(
            session_id="session-1",
            level=1
        )
        
        assert session.session_id == "session-1"
        assert session.level == 1
        assert len(session.messages) == 0

    def test_layer_session_add_message(self):
        """测试添加消息"""
        session = LayerSession(
            session_id="session-1",
            level=1
        )
        
        session.add_message("user", "你好")
        session.add_message("assistant", "你好，我是助手")
        
        assert len(session.messages) == 2
        assert session.messages[0]["role"] == "user"
        assert session.messages[1]["role"] == "assistant"

    def test_layer_session_get_summary(self):
        """测试获取摘要"""
        session = LayerSession(
            session_id="session-1",
            level=2,
            metadata={"total_tokens": 1000}
        )
        session.add_message("user", "测试")
        
        summary = session.get_summary()
        
        assert "session-1" in summary
        assert "L2" in summary

    def test_layer_context_manager_build_context_l1(self):
        """测试 L1 上下文构建"""
        manager = LayerContextManager()
        
        context = manager.build_layer_context(
            level=1,
            task=MagicMock(original_request="测试请求", children_summaries=[])
        )
        
        assert "original_request" in context

    def test_layer_context_manager_build_context_l2(self):
        """测试 L2 上下文构建"""
        manager = LayerContextManager()
        
        context = manager.build_layer_context(
            level=2,
            task=MagicMock(goal="子域目标", shared_constraints=[], provides_to_others=[])
        )
        
        assert "subdomain_goal" in context

    def test_layer_context_manager_build_context_l3(self):
        """测试 L3 上下文构建"""
        manager = LayerContextManager()
        
        context = manager.build_layer_context(
            level=3,
            task=MagicMock(description="任务描述", constraints=[], parent_summary="父摘要")
        )
        
        assert "task" in context
        assert "constraints" in context

    def test_layer_context_manager_should_compact(self):
        """测试是否需要压缩"""
        manager = LayerContextManager(max_tokens_per_layer=1000)
        
        session = LayerSession(
            session_id="s1",
            level=1,
            metadata={"total_tokens": 500}
        )
        
        assert manager.should_compact(session) is False
        
        session.metadata["total_tokens"] = 1500
        assert manager.should_compact(session) is True

    def test_multi_agent_session_manager_create_top_session(self):
        """测试创建顶层 Session"""
        manager = MultiAgentSessionManager()
        
        session = manager.create_top_session("用户请求")
        
        assert session.level == 1
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "user"

    def test_multi_agent_session_manager_create_layer2_session(self):
        """测试创建 L2 Session"""
        manager = MultiAgentSessionManager()
        top_session = manager.create_top_session("请求")
        
        l2_session = manager.create_layer2_session(
            top_session.session_id,
            "task-1"
        )
        
        assert l2_session.level == 2
        assert l2_session.parent_session_id == top_session.session_id
        assert l2_session.metadata["task_id"] == "task-1"

    def test_multi_agent_session_manager_create_layer3_session(self):
        """测试创建 L3 Session"""
        manager = MultiAgentSessionManager()
        top_session = manager.create_top_session("请求")
        
        l3_session = manager.create_layer3_session(
            top_session.session_id,
            "frontend"
        )
        
        assert l3_session.level == 3
        assert l3_session.subdomain_id == "frontend"

    def test_multi_agent_session_manager_get_session(self):
        """测试获取 Session"""
        manager = MultiAgentSessionManager()
        session = manager.create_top_session("请求")
        
        retrieved = manager.get_session(session.session_id)
        
        assert retrieved == session
        assert manager.get_session("nonexistent") is None

    def test_multi_agent_session_manager_get_child_sessions(self):
        """测试获取子 Session"""
        manager = MultiAgentSessionManager()
        top = manager.create_top_session("请求")
        child = manager.create_layer2_session(top.session_id, "task-1")
        
        children = manager.get_child_sessions(top.session_id)
        
        assert len(children) == 1
        assert children[0].session_id == child.session_id

    def test_multi_agent_session_manager_compact_session(self):
        """测试压缩 Session"""
        manager = MultiAgentSessionManager()
        session = manager.create_top_session("请求")
        session.add_message("assistant", "响应1")
        session.add_message("assistant", "响应2")
        
        result = manager.compact_session(session.session_id)
        
        assert result is True
        compacted = manager.get_session(session.session_id)
        assert len(compacted.messages) == 1
        assert "[已压缩历史消息]" in compacted.messages[0]["content"]


class TestExecuteIntegration:
    """测试端到端集成"""

    @pytest.mark.asyncio
    async def test_execute_simple_l1(self):
        """测试简单执行"""
        result = await execute_simple("修复这个bug")
        
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_simple_l2(self):
        """测试 L2 执行"""
        result = await execute_simple("同时更新前端和后端")
        
        assert result.status in ["completed", "rejected", "failed"]

    @pytest.mark.asyncio
    async def test_execute_simple_l3(self):
        """测试 L3 执行"""
        result = await execute_simple("重构整个系统架构")
        
        assert result.status in ["completed", "rejected", "failed"]

    @pytest.mark.asyncio
    async def test_multi_agent_executor_init(self):
        """测试 MultiAgentExecutor 初始化"""
        executor = MultiAgentExecutor()
        
        assert executor.router is not None
        assert executor.session_manager is not None
        assert executor.l2_decomposer is not None
        assert executor.l2_reviewer is not None
        assert executor.l2_executor is not None
        assert executor.l3_top_decomposer is not None
        assert executor.l3_reviewer is not None
        assert executor.l3_executor is not None

    @pytest.mark.asyncio
    async def test_multi_agent_executor_l1_flow(self):
        """测试 L1 执行流程"""
        executor = MultiAgentExecutor()
        
        result = await executor.execute("帮我修复这个bug")
        
        assert result.status in ["completed", "failed"]

    @pytest.mark.asyncio
    async def test_multi_agent_executor_l2_flow(self):
        """测试 L2 执行流程"""
        executor = MultiAgentExecutor()
        
        result = await executor.execute("分别处理前端和后端的更新")
        
        # 应该路由到 L2
        # 执行结果可能是 completed, rejected, failed
        assert result is not None

    @pytest.mark.asyncio
    async def test_multi_agent_executor_l3_flow(self):
        """测试 L3 执行流程"""
        executor = MultiAgentExecutor()
        
        result = await executor.execute("重构整个系统为微服务架构")
        
        # 应该路由到 L3
        assert result is not None


class TestConstraints:
    """测试约束系统"""

    def test_constraint_to_dict(self):
        """测试约束序列化"""
        constraint = Constraint(
            type=ConstraintType.WAIT_FOR_EXTERNAL,
            description="等待外部输入",
            source="subdomain:backend"
        )
        
        d = constraint.to_dict()
        
        assert d["type"] == "wait_for_external"
        assert d["source"] == "subdomain:backend"

    def test_all_constraint_types_export(self):
        """测试所有约束类型都已导出"""
        from scripts.multi_agent.constraints import (
            Constraint,
            ConstraintType,
            TaskStatus,
            FORBIDDEN_ACTIONS
        )
        
        assert len(ConstraintType) >= 10


class TestResultSummarization:
    """测试结果摘要功能"""

    def test_summarize_results_empty(self):
        """测试空结果摘要"""
        from scripts.multi_agent.execute import _summarize_results

        result = _summarize_results([])

        assert "无任务执行" in result

    def test_summarize_results_all_completed(self):
        """测试全部成功的结果摘要"""
        from scripts.multi_agent.execute import _summarize_results

        results = [
            TaskResult(task_id="t1", status="completed", summary="任务1完成"),
            TaskResult(task_id="t2", status="completed", summary="任务2完成"),
        ]

        result = _summarize_results(results)

        assert "共 2 个任务" in result
        assert "完成: 2" in result
        assert "任务1完成" in result

    def test_summarize_results_with_failures(self):
        """测试有失败的结果摘要"""
        from scripts.multi_agent.execute import _summarize_results

        results = [
            TaskResult(task_id="t1", status="completed", summary="任务1完成"),
            TaskResult(task_id="t2", status="failed", error="任务2失败"),
        ]

        result = _summarize_results(results)

        assert "完成: 1" in result
        assert "失败: 1" in result
        assert "任务2失败" in result

    def test_summarize_results_with_cancelled(self):
        """测试有取消的结果摘要"""
        from scripts.multi_agent.execute import _summarize_results

        results = [
            TaskResult(task_id="t1", status="completed"),
            TaskResult(task_id="t2", status="cancelled", error="前置任务失败"),
        ]

        result = _summarize_results(results)

        assert "取消: 1" in result

    def test_summarize_subdomain_results_empty(self):
        """测试空子域结果摘要"""
        from scripts.multi_agent.execute import _summarize_subdomain_results

        result = _summarize_subdomain_results([])

        assert "无子域执行" in result

    def test_summarize_subdomain_results_all_completed(self):
        """测试全部成功的子域结果摘要"""
        from scripts.multi_agent.execute import _summarize_subdomain_results

        results = [
            SubdomainResult(
                subdomain_id="frontend",
                status=TaskStatus.COMPLETED,
                completed=True
            ),
            SubdomainResult(
                subdomain_id="backend",
                status=TaskStatus.COMPLETED,
                completed=True
            ),
        ]

        result = _summarize_subdomain_results(results)

        assert "共 2 个子域" in result
        assert "完成: 2" in result

    def test_summarize_subdomain_results_with_failures(self):
        """测试有失败的子域结果摘要"""
        from scripts.multi_agent.execute import _summarize_subdomain_results

        results = [
            SubdomainResult(
                subdomain_id="frontend",
                status=TaskStatus.COMPLETED,
                completed=True
            ),
            SubdomainResult(
                subdomain_id="backend",
                status=TaskStatus.FAILED,
                completed=False,
                failed_tasks=[MagicMock()]
            ),
        ]

        result = _summarize_subdomain_results(results)

        assert "完成: 1" in result
        assert "失败: 1" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
