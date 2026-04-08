"""
Multi-Agent 系统 - 基于复杂度的多层Agent编排

架构：
- L1: 单Agent直接执行
- L2: Decomposer + 审核 → Executor集群
- L3: 三层 + 逐级审核 + 回滚

设计原则：
- 约束前置：在规划阶段消除冲突
- 双重保证：Prompt约束 + 审核Agent验证
- 逐级审核：每层完成后上级审核，不达标则回滚重做

参考文档：docs/MULTI_AGENT_DESIGN.md
"""

from .decomposer import L2Decomposer, L3SubDecomposer, L3TopDecomposer
from .execute import (
    MultiAgentExecutor,
    execute_simple,
    StreamEvent,
)
from .executor import L2Executor, L3Executor, TaskResult
from .models import (
    FORBIDDEN_ACTIONS,
    # 枚举
    ComplexityLevel,
    # 模型
    Constraint,
    ConstraintType,
    CrossDomainDep,
    ExecutionPlan,
    ExecutionResult,
    Issue,
    L3Plan,
    ReviewResult,
    RollbackPlan,
    RouteResult,
    SubdomainPlan,
    SubdomainResult,
    Task,
    TaskStatus,
)
from .reviewer import L2Reviewer, L3Reviewer
from .router import HybridRouter, route_simple
from .session import LayerContextManager, LayerSession, MultiAgentSessionManager

from .cross_domain import (
    get_cross_domain_messenger,
    get_cross_domain_state_manager,
    get_distributed_rollback_manager,
    CrossDomainMessenger,
    CrossDomainMessage,
    CrossDomainStateManager,
    StateChangeEvent,
    DistributedRollbackManager,
    RollbackInfo,
)
from .self_optimization import (
    get_stats_collector,
    get_split_analyzer,
    get_adaptive_reviewer_rules,
    ExecutionStatsCollector,
    SplitStrategyAnalyzer,
    AdaptiveReviewerRules,
)
from .router_enhance import (
    ExplainableHybridRouter,
    RouterHistory,
    CustomRuleRegistry,
    RouteExplanation,
    create_explainable_router,
)

__all__ = [
    # 枚举
    "ComplexityLevel",
    "TaskStatus",
    "ConstraintType",
    # 模型
    "Constraint",
    "Issue",
    "ReviewResult",
    "RollbackPlan",
    "Task",
    "ExecutionPlan",
    "CrossDomainDep",
    "SubdomainPlan",
    "SubdomainResult",
    "L3Plan",
    "ExecutionResult",
    "RouteResult",
    "FORBIDDEN_ACTIONS",
    # 路由
    "HybridRouter",
    "route_simple",
    # Decomposer
    "L2Decomposer",
    "L3TopDecomposer",
    "L3SubDecomposer",
    # Reviewer
    "L2Reviewer",
    "L3Reviewer",
    # Executor
    "L2Executor",
    "L3Executor",
    "TaskResult",
    # Session
    "LayerSession",
    "LayerContextManager",
    "MultiAgentSessionManager",
    # Execute
    "MultiAgentExecutor",
    "execute_simple",
    "StreamEvent",
    # Cross Domain (Phase 3)
    "get_cross_domain_messenger",
    "get_cross_domain_state_manager",
    "get_distributed_rollback_manager",
    "CrossDomainMessenger",
    "CrossDomainMessage",
    "CrossDomainStateManager",
    "StateChangeEvent",
    "DistributedRollbackManager",
    "RollbackInfo",
    # Self Optimization (Phase 4)
    "get_stats_collector",
    "get_split_analyzer",
    "get_adaptive_reviewer_rules",
    "ExecutionStatsCollector",
    "SplitStrategyAnalyzer",
    "AdaptiveReviewerRules",
    # Router Enhance (Phase 2)
    "ExplainableHybridRouter",
    "RouterHistory",
    "CustomRuleRegistry",
    "RouteExplanation",
    "create_explainable_router",
]
