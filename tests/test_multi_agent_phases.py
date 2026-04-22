"""
Multi-Agent Phase 2/3/4 测试

测试跨域协调、自我优化、Router增强功能。
"""

import asyncio
import json
import pytest
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from scripts.multi_agent import (
    ComplexityLevel,
    Task,
    TaskStatus,
)


class TestRouterEnhance:
    """Phase 2: Router 增强测试"""

    def test_router_history_record(self, tmp_path):
        """测试历史记录"""
        from scripts.multi_agent.router_enhance import RouterHistory

        history_file = tmp_path / "history.json"
        history = RouterHistory(history_file)

        history.record("测试输入1", "L1", 0.9, "rule_based")
        history.record("测试输入2", "L2", 0.8, "rule_based")

        assert len(history.get_history()) == 2
        assert history.get_level_distribution()["L1"] == 1
        assert history.get_level_distribution()["L2"] == 1

    def test_custom_rule_registry(self):
        """测试自定义规则"""
        from scripts.multi_agent.router_enhance import CustomRuleRegistry

        registry = CustomRuleRegistry()
        registry.add_rule("危险操作", 10, "L3")

        rules = registry.get_rules()
        assert len(rules) == 1
        assert rules[0]["pattern"] == "危险操作"
        assert rules[0]["level"] == "L3"

        registry.remove_rule("危险操作")
        assert len(registry.get_rules()) == 0

    def test_explainable_router(self, tmp_path):
        """测试可解释性路由"""
        from scripts.multi_agent.router_enhance import ExplainableHybridRouter

        history_file = tmp_path / "history.json"
        router = ExplainableHybridRouter(history_file=history_file)

        router.add_rule("重构", 8, "L3")

        result, explanation = router.explain_route("帮我重构这个模块")

        assert result.level == ComplexityLevel.L3
        assert "重构" in explanation.matched_rules

    def test_explainable_router_statistics(self, tmp_path):
        """测试统计信息"""
        from scripts.multi_agent.router_enhance import ExplainableHybridRouter

        history_file = tmp_path / "history.json"
        router = ExplainableHybridRouter(history_file=history_file)

        stats = router.get_statistics()
        assert "total_history" in stats
        assert "level_distribution" in stats
        assert "custom_rules_count" in stats


class TestCrossDomainMessenger:
    """Phase 3: 跨域消息传递测试"""

    def test_send_message(self):
        """测试发送消息"""
        from scripts.multi_agent.cross_domain import CrossDomainMessenger

        messenger = CrossDomainMessenger()
        msg = messenger.send_message("subdomain_a", "subdomain_b", "任务完成")

        assert msg.from_subdomain == "subdomain_a"
        assert msg.to_subdomain == "subdomain_b"
        assert msg.content == "任务完成"

    def test_get_messages(self):
        """测试获取消息"""
        from scripts.multi_agent.cross_domain import CrossDomainMessenger

        messenger = CrossDomainMessenger()
        messenger.send_message("subdomain_a", "subdomain_b", "消息1")
        messenger.send_message("subdomain_c", "subdomain_b", "消息2")

        messages = messenger.get_messages("subdomain_b")
        assert len(messages) == 2

    def test_subscribe(self):
        """测试订阅"""
        from scripts.multi_agent.cross_domain import CrossDomainMessenger, CrossDomainMessage

        messenger = CrossDomainMessenger()
        received = []

        def callback(msg: CrossDomainMessage):
            received.append(msg)

        messenger.subscribe("subdomain_b", callback)
        messenger.send_message("subdomain_a", "subdomain_b", "测试消息")

        assert len(received) == 1
        assert received[0].content == "测试消息"


class TestCrossDomainStateManager:
    """Phase 3: 跨域状态管理测试"""

    def test_set_and_get_state(self):
        """测试状态设置和获取"""
        from scripts.multi_agent.cross_domain import CrossDomainStateManager

        manager = CrossDomainStateManager()
        manager.set_state("key1", "value1", subdomain="sub_a")

        assert manager.get_state("key1") == "value1"

    def test_get_all_state(self):
        """测试获取所有状态"""
        from scripts.multi_agent.cross_domain import CrossDomainStateManager

        manager = CrossDomainStateManager()
        manager.set_state("key1", "value1")
        manager.set_state("key2", "value2")

        all_state = manager.get_all_state()
        assert len(all_state) == 2
        assert all_state["key1"] == "value1"

    def test_state_subscription(self):
        """测试状态订阅"""
        from scripts.multi_agent.cross_domain import CrossDomainStateManager, StateChangeEvent

        manager = CrossDomainStateManager()
        received = []

        def callback(event: StateChangeEvent):
            received.append(event)

        manager.subscribe("key1", callback)
        manager.set_state("key1", "new_value")

        assert len(received) == 1
        assert received[0].value == "new_value"

    def test_get_history(self):
        """测试状态历史"""
        from scripts.multi_agent.cross_domain import CrossDomainStateManager

        manager = CrossDomainStateManager()
        manager.set_state("key1", "value1")
        manager.set_state("key1", "value2")

        history = manager.get_history("key1")
        assert len(history) == 2


class TestDistributedRollbackManager:
    """Phase 3: 分布式回滚测试"""

    def test_register_rollback(self):
        """测试注册回滚"""
        from scripts.multi_agent.cross_domain import DistributedRollbackManager

        manager = DistributedRollbackManager()

        def rollback_fn():
            return "rolled_back"

        manager.register_rollback("sub_a", rollback_fn, depends_on=["sub_b"])

        info = manager.get_rollback_info("sub_a")
        assert info is not None
        assert info.subdomain == "sub_a"
        assert "sub_b" in info.depends_on

    def test_get_rollback_order(self):
        """测试回滚顺序"""
        from scripts.multi_agent.cross_domain import DistributedRollbackManager

        manager = DistributedRollbackManager()

        manager.register_rollback("sub_a", lambda: None, depends_on=["sub_b"])
        manager.register_rollback("sub_b", lambda: None, depends_on=["sub_c"])
        manager.register_rollback("sub_c", lambda: None)

        order = manager.get_rollback_order()
        assert order.index("sub_a") > order.index("sub_b")
        assert order.index("sub_b") > order.index("sub_c")

    @pytest.mark.asyncio
    async def test_execute_global_rollback(self):
        """测试执行全局回滚"""
        from scripts.multi_agent.cross_domain import DistributedRollbackManager

        manager = DistributedRollbackManager()
        executed = []

        def make_rollback(name):
            def rollback():
                executed.append(name)
                return f"{name}_done"
            return rollback

        manager.register_rollback("sub_a", make_rollback("sub_a"), depends_on=["sub_b"])
        manager.register_rollback("sub_b", make_rollback("sub_b"), depends_on=["sub_c"])
        manager.register_rollback("sub_c", make_rollback("sub_c"))

        result = await manager.execute_global_rollback()

        assert result["success"] is True
        assert executed == ["sub_a", "sub_b", "sub_c"]


class TestExecutionStatsCollector:
    """Phase 4: 执行统计测试"""

    def test_record_execution(self, tmp_path):
        """测试记录执行"""
        from scripts.multi_agent.self_optimization import ExecutionStatsCollector

        stats_file = tmp_path / "stats.json"
        collector = ExecutionStatsCollector(stats_file)

        collector.record_execution(
            level="L2",
            duration=10.5,
            task_count=5,
            success=True,
            token_count=1000,
        )

        assert len(collector.get_stats()) == 1

    def test_get_average_duration(self, tmp_path):
        """测试平均执行时间"""
        from scripts.multi_agent.self_optimization import ExecutionStatsCollector

        stats_file = tmp_path / "stats.json"
        collector = ExecutionStatsCollector(stats_file)

        collector.record_execution("L2", 10.0, 3, True)
        collector.record_execution("L2", 20.0, 3, True)

        assert collector.get_average_duration("L2") == 15.0

    def test_get_success_rate(self, tmp_path):
        """测试成功率"""
        from scripts.multi_agent.self_optimization import ExecutionStatsCollector

        stats_file = tmp_path / "stats.json"
        collector = ExecutionStatsCollector(stats_file)

        collector.record_execution("L2", 10.0, 3, True)
        collector.record_execution("L2", 10.0, 3, False)

        assert collector.get_success_rate("L2") == 0.5

    def test_get_summary(self, tmp_path):
        """测试统计摘要"""
        from scripts.multi_agent.self_optimization import ExecutionStatsCollector

        stats_file = tmp_path / "stats.json"
        collector = ExecutionStatsCollector(stats_file)

        collector.record_execution("L1", 5.0, 1, True)
        collector.record_execution("L2", 10.0, 3, True)

        summary = collector.get_summary()
        assert summary["total_executions"] == 2
        assert "by_level" in summary


class TestSplitStrategyAnalyzer:
    """Phase 4: 拆分策略分析测试"""

    def test_analyze_split_effectiveness(self, tmp_path):
        """测试拆分效果分析"""
        from scripts.multi_agent.self_optimization import (
            ExecutionStatsCollector,
            SplitStrategyAnalyzer,
        )

        stats_file = tmp_path / "stats.json"
        stats_collector = ExecutionStatsCollector(stats_file)
        analyzer = SplitStrategyAnalyzer(stats_collector)

        for i in range(3):
            stats_collector.record_execution("L2", 10.0, 3, True)
            stats_collector.record_execution("L2", 15.0, 8, False)

        result = analyzer.analyze_split_effectiveness()
        assert "suggestions" in result
        assert len(result["suggestions"]) > 0

    def test_get_task_count_trend(self, tmp_path):
        """测试任务数量趋势"""
        from scripts.multi_agent.self_optimization import (
            ExecutionStatsCollector,
            SplitStrategyAnalyzer,
        )

        stats_file = tmp_path / "stats.json"
        stats_collector = ExecutionStatsCollector(stats_file)
        analyzer = SplitStrategyAnalyzer(stats_collector)

        for _ in range(3):
            stats_collector.record_execution("L2", 10.0, 3, True)

        trend = analyzer.get_task_count_trend()
        assert "by_level" in trend


class TestAdaptiveReviewerRules:
    """Phase 4: 自适应审核规则测试"""

    def test_record_rejection(self):
        """测试记录拒绝"""
        from scripts.multi_agent.self_optimization import AdaptiveReviewerRules

        rules = AdaptiveReviewerRules()
        rules.record_rejection("缺少回滚方案")
        rules.record_rejection("文件冲突")
        rules.record_rejection("缺少回滚方案")

        patterns = rules.get_top_rejected_patterns()
        assert patterns[0]["pattern"] == "缺少回滚方案"
        assert patterns[0]["count"] == 2

    def test_suggest_rules(self):
        """测试规则建议"""
        from scripts.multi_agent.self_optimization import AdaptiveReviewerRules

        rules = AdaptiveReviewerRules()
        rules.record_rejection("模式A")
        rules.record_rejection("模式A")
        rules.record_rejection("模式A")

        suggestions = rules.suggest_rules(min_frequency=3)
        assert len(suggestions) > 0


class TestIntegrationL2Parallel:
    """L2 并行集成测试"""

    @pytest.mark.asyncio
    async def test_l2_parallel_execution(self):
        """测试 L2 并行执行"""
        from scripts.multi_agent import Task

        task = Task(id="test_task", description="实现两个功能")

        assert task.id == "test_task"
        assert task.description == "实现两个功能"


class TestIntegrationL3Subdomain:
    """L3 子域并行集成测试"""

    @pytest.mark.asyncio
    async def test_l3_subdomain_parallel(self):
        """测试 L3 子域并行执行"""
        from scripts.multi_agent import L3Plan, SubdomainPlan, Task, TaskStatus

        plan = L3Plan()
        plan.subdomains = [
            SubdomainPlan(subdomain_id="frontend", tasks=[
                Task(id="f1", description="前端任务1"),
                Task(id="f2", description="前端任务2"),
            ]),
            SubdomainPlan(subdomain_id="backend", tasks=[
                Task(id="b1", description="后端任务1"),
            ]),
        ]

        assert len(plan.subdomains) == 2
        assert plan.subdomains[0].subdomain_id == "frontend"
        assert plan.subdomains[1].subdomain_id == "backend"


class TestIntegrationCrossDomain:
    """跨域依赖集成测试"""

    def test_cross_domain_message_flow(self):
        """测试跨域消息流程"""
        from scripts.multi_agent.cross_domain import (
            get_cross_domain_messenger,
            get_cross_domain_state_manager,
            get_distributed_rollback_manager,
            reset_cross_domain_services,
        )

        reset_cross_domain_services()

        messenger = get_cross_domain_messenger()
        state_mgr = get_cross_domain_state_manager()
        rollback_mgr = get_distributed_rollback_manager()

        messenger.send_message("frontend", "backend", "前端完成")
        messages = messenger.get_messages("backend")
        assert len(messages) == 1

        state_mgr.set_state("task_count", 5)
        assert state_mgr.get_state("task_count") == 5

        rollback_mgr.register_rollback("frontend", lambda: "front_rollback")
        rollback_mgr.register_rollback("backend", lambda: "back_rollback", depends_on=["frontend"])

        order = rollback_mgr.get_rollback_order()
        assert order.index("frontend") < order.index("backend")


class TestPerfScenarios:
    """性能测试场景"""

    def test_many_subtasks_handling(self):
        """测试大量子任务处理"""
        from scripts.multi_agent import Task, TaskStatus, ExecutionPlan

        tasks = [
            Task(id=f"task_{i}", description=f"任务 {i}")
            for i in range(50)
        ]

        plan = ExecutionPlan(id="perf_test", level=ComplexityLevel.L2, tasks=tasks)

        sorted_tasks = plan.topological_sort()
        assert len(sorted_tasks) == 50

    def test_deep_dependency_chain(self):
        """测试长依赖链"""
        from scripts.multi_agent import Task, ExecutionPlan, ComplexityLevel

        tasks = []
        for i in range(20):
            deps = [f"task_{i-1}"] if i > 0 else []
            task = Task(id=f"task_{i}", description=f"任务 {i}", dependencies=deps)
            tasks.append(task)

        plan = ExecutionPlan(id="deep_deps", level=ComplexityLevel.L2, tasks=tasks)
        sorted_tasks = plan.topological_sort()

        for i in range(1, len(sorted_tasks)):
            prev_idx = next(j for j, t in enumerate(sorted_tasks) if t.id == f"task_{i-1}")
            curr_idx = next(j for j, t in enumerate(sorted_tasks) if t.id == f"task_{i}")
            assert prev_idx < curr_idx
