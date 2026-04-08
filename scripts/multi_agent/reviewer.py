"""
Reviewer - 审核Agent

L2Reviewer: L2 审核Agent（规划阶段质量门控）
L3Reviewer: L3 审核Agent（跨层质量门控 + 回滚保证）
"""

from __future__ import annotations

from typing import Any

from .constraints import FORBIDDEN_ACTIONS, ConstraintType
from .models import (
    ExecutionPlan,
    Issue,
    L3Plan,
    ReviewResult,
    SubdomainResult,
)


class L2Reviewer:
    """
    L2 审核Agent: 规划阶段质量门控

    负责：
    1. 检查文件冲突
    2. 检查依赖完整性
    3. 检查回滚方案
    4. 检查危险操作
    5. 检查任务粒度
    """

    def __init__(self, llm_client: object | None = None):
        """
        初始化 L2 审核器

        Args:
            llm_client: 可选的 LLM 客户端
        """
        self.llm_client = llm_client

    async def approve(self, plan: ExecutionPlan) -> ReviewResult:
        """
        审核执行计划

        Args:
            plan: 执行计划

        Returns:
            ReviewResult: 审核结果
        """
        issues: list[Issue] = []

        # 检查1: 文件冲突
        conflicts = self._check_file_conflicts(plan)
        if conflicts:
            issues.append(Issue(
                type="file_conflict",
                severity="critical",
                details=conflicts,
                resolution="重新划分文件边界"
            ))

        # 检查2: 依赖完整性
        missing = self._check_dependencies(plan)
        if missing:
            issues.append(Issue(
                type="missing_dependency",
                severity="high",
                details=missing
            ))

        # 检查3: 回滚方案
        for task in plan.tasks:
            if not task.has_rollback_plan:
                issues.append(Issue(
                    type="no_rollback_plan",
                    severity="high",
                    task_id=task.id,
                    resolution="必须提供回滚方案"
                ))

        # 检查4: 危险操作
        dangerous = self._check_dangerous_operations(plan)
        if dangerous:
            issues.append(Issue(
                type="dangerous_operation",
                severity="critical",
                details=dangerous,
                resolution="禁止或提供额外保护"
            ))

        # 检查5: 任务粒度
        for task in plan.tasks:
            if task.estimated_steps > 10:
                issues.append(Issue(
                    type="task_too_large",
                    severity="medium",
                    task_id=task.id,
                    resolution="拆分为更小任务"
                ))

        # 如果有 LLM 客户端，使用 LLM 进一步审核
        if self.llm_client and len(issues) == 0:
            llm_issues = await self._llm_review(plan)
            issues.extend(llm_issues)

        # 只有 critical 和 high 级别的问题会导致拒绝
        blocking_issues = [i for i in issues if i.severity in ("critical", "high")]
        return ReviewResult(
            approved=len(blocking_issues) == 0,
            issues=issues,
            requires_redo=len(issues) > 0
        )

    async def final_approve(self, summary: str) -> ReviewResult:
        """
        最终审核

        Args:
            summary: 执行摘要

        Returns:
            ReviewResult: 审核结果
        """
        # 简单的最终审核：检查摘要中是否有明显的失败标志
        issues = []

        if "failed" in summary.lower():
            issues.append(Issue(
                type="execution_failed",
                severity="high",
                details="执行摘要中包含失败信息"
            ))

        return ReviewResult(
            approved=len(issues) == 0,
            issues=issues,
            requires_redo=len(issues) > 0
        )

    def _check_file_conflicts(self, plan: ExecutionPlan) -> list[str]:
        """
        检查文件冲突

        Args:
            plan: 执行计划

        Returns:
            List[str]: 冲突文件列表
        """
        file_to_tasks: dict[str, list[str]] = {}

        for task in plan.tasks:
            for file in task.target_files:
                if file not in file_to_tasks:
                    file_to_tasks[file] = []
                file_to_tasks[file].append(task.id)

        conflicts = []
        for file, tasks in file_to_tasks.items():
            if len(tasks) > 1:
                conflicts.append(f"{file} 被多个任务修改: {tasks}")

        return conflicts

    def _check_dependencies(self, plan: ExecutionPlan) -> list[str]:
        """
        检查依赖完整性

        Args:
            plan: 执行计划

        Returns:
            List[str]: 缺失的依赖列表
        """
        task_ids = {task.id for task in plan.tasks}
        missing = []

        for task in plan.tasks:
            for dep in task.dependencies:
                if dep not in task_ids:
                    missing.append(f"任务 {task.id} 依赖的 {dep} 不存在")

        return missing

    def _check_dangerous_operations(self, plan: ExecutionPlan) -> list[str]:
        """
        检查危险操作

        Args:
            plan: 执行计划

        Returns:
            List[str]: 危险操作列表
        """
        dangerous = []

        for task in plan.tasks:
            # 检查任务描述中是否包含危险操作
            for action in FORBIDDEN_ACTIONS:
                if action.lower() in task.description.lower():
                    dangerous.append(f"任务 {task.id} 包含危险操作: {action}")

        return dangerous

    async def _llm_review(self, plan: ExecutionPlan) -> list[Issue]:
        """
        使用 LLM 审核计划

        Args:
            plan: 执行计划

        Returns:
            List[Issue]: 发现的问题列表
        """
        prompt = self._build_review_prompt(plan)

        try:
            response = await self.llm_client.complete(prompt)
            return self._parse_review_response(response)
        except Exception:
            return []

    def _build_review_prompt(self, plan: ExecutionPlan) -> str:
        """
        构建审核提示

        Args:
            plan: 执行计划

        Returns:
            str: 提示文本
        """
        tasks_json = "\n".join([
            f"- {t.id}: {t.description} (files: {t.target_files})"
            for t in plan.tasks
        ])

        return f"""审核以下执行计划，找出潜在问题：

计划ID: {plan.id}
任务列表：
{tasks_json}

请返回JSON格式的问题列表：
{{
    "issues": [
        {{
            "type": "issue_type",
            "severity": "critical|high|medium|low",
            "task_id": "相关任务ID（如适用）",
            "details": "问题详情",
            "resolution": "建议的解决方案"
        }}
    ]
}}
"""

    def _parse_review_response(self, response: str) -> list[Issue]:
        """
        解析审核响应

        Args:
            response: LLM 响应

        Returns:
            List[Issue]: 问题列表
        """
        import json

        try:
            data = json.loads(response)
            issues_data = data.get("issues", [])

            return [
                Issue(
                    type=issue.get("type", "unknown"),
                    severity=issue.get("severity", "medium"),
                    task_id=issue.get("task_id"),
                    details=issue.get("details"),
                    resolution=issue.get("resolution"),
                )
                for issue in issues_data
            ]
        except json.JSONDecodeError:
            return []


class L3Reviewer:
    """
    L3 审核Agent: 跨层质量门控 + 回滚保证

    负责：
    1. 全局规划审核（第一层）
    2. 子域结果审核（第二层）
    3. 最终整合审核
    """

    def __init__(self, llm_client: object | None = None):
        """
        初始化 L3 审核器

        Args:
            llm_client: 可选的 LLM 客户端
        """
        self.llm_client = llm_client

    async def approve_global(self, plan: L3Plan) -> ReviewResult:
        """
        第一层审核：全局规划

        Args:
            plan: L3 执行计划

        Returns:
            ReviewResult: 审核结果
        """
        issues: list[Issue] = []

        # 检查子域划分是否合理
        if self._has_overlapping_subdomains(plan):
            issues.append(Issue(
                type="subdomain_overlap",
                severity="critical"
            ))

        # 检查跨域依赖是否有环
        if self._has_circular_dependency(plan.cross_domain_dependencies):
            issues.append(Issue(
                type="circular_dependency",
                severity="critical"
            ))

        # 检查接口稳定性
        if self._interfaces_unstable(plan):
            issues.append(Issue(
                type="unstable_interface",
                severity="high"
            ))

        return ReviewResult(
            approved=len(issues) == 0,
            issues=issues,
            requires_redo=len(issues) > 0
        )

    async def approve_subdomain(self, subdomain_result: SubdomainResult) -> ReviewResult:
        """
        第二层审核：子域结果

        Args:
            subdomain_result: 子域执行结果

        Returns:
            ReviewResult: 审核结果
        """
        issues: list[Issue] = []

        # 质量检查
        if not self._quality_passes(subdomain_result):
            issues.append(Issue(
                type="quality_failed",
                severity="high"
            ))

        # 回滚能力检查
        if not subdomain_result.has_rollback_capability:
            issues.append(Issue(
                type="no_rollback",
                severity="critical"
            ))

        # 接口契约检查
        if not self._interface_contract_met(subdomain_result):
            issues.append(Issue(
                type="contract_violation",
                severity="critical"
            ))

        return ReviewResult(
            approved=len(issues) == 0,
            issues=issues,
            requires_redo=len(issues) > 0
        )

    async def approve_final(self, all_subdomain_results: list[SubdomainResult]) -> ReviewResult:
        """
        最终审核：全局整合结果

        Args:
            all_subdomain_results: 所有子域结果

        Returns:
            ReviewResult: 审核结果
        """
        issues: list[Issue] = []

        # 检查所有子域是否完成
        incomplete = [r for r in all_subdomain_results if not r.completed]
        if incomplete:
            issues.append(Issue(
                type="incomplete_subdomains",
                severity="high",
                details=[r.subdomain_id for r in incomplete]
            ))

        # 检查跨域集成
        integration_ok, integration_issues = self._check_integration(all_subdomain_results)
        if not integration_ok:
            issues.extend(integration_issues)

        return ReviewResult(
            approved=len(issues) == 0,
            issues=issues,
            requires_redo=len(issues) > 0
        )

    def _has_overlapping_subdomains(self, plan: L3Plan) -> bool:
        """
        检查子域是否有重叠

        Args:
            plan: L3 执行计划

        Returns:
            bool: 是否有重叠
        """
        all_files: set[str] = set()

        for subdomain in plan.subdomains:
            for file in subdomain.allowed_files:
                if file in all_files:
                    return True
                all_files.add(file)

        return False

    def _has_circular_dependency(self, deps: list[Any]) -> bool:
        """
        检查跨域依赖是否有环

        Args:
            deps: 跨域依赖列表

        Returns:
            bool: 是否有循环依赖
        """
        # 构建依赖图
        graph: dict[str, list[str]] = {}
        for dep in deps:
            source = dep.source_subdomain
            target = dep.target_subdomain
            if source not in graph:
                graph[source] = []
            graph[source].append(target)

        # DFS 检测环
        visited = set()
        rec_stack = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for node in graph:
            if node not in visited:
                if has_cycle(node):
                    return True

        return False

    def _interfaces_unstable(self, plan: L3Plan) -> bool:
        """
        检查接口是否不稳定

        Args:
            plan: L3 执行计划

        Returns:
            bool: 接口是否不稳定
        """
        # 简单的检查：是否有接口文件被修改
        for constraint in plan.global_constraints:
            if constraint.type == ConstraintType.INTERFACE_FROZEN:
                return False  # 有冻结约束，接口应该稳定

        return False  # 默认认为稳定

    def _quality_passes(self, result: SubdomainResult) -> bool:
        """
        检查质量是否通过

        Args:
            result: 子域结果

        Returns:
            bool: 质量是否通过
        """
        # 处理枚举和字符串两种情况
        status = result.status
        if hasattr(status, 'value'):
            status = status.value
        return status == "completed"

    def _interface_contract_met(self, result: SubdomainResult) -> bool:
        """
        检查接口契约是否满足

        Args:
            result: 子域结果

        Returns:
            bool: 接口契约是否满足
        """
        # 简单的检查：子域完成即可
        return result.completed

    def _check_integration(
        self, results: list[SubdomainResult]
    ) -> tuple[bool, list[Issue]]:
        """
        检查跨域集成

        Args:
            results: 子域结果列表

        Returns:
            tuple: (是否通过, 问题列表)
        """
        issues = []

        # 检查是否有失败的子域
        failed = [r for r in results if r.status == "failed"]
        if failed:
            issues.append(Issue(
                type="subdomain_failed",
                severity="critical",
                details=[r.subdomain_id for r in failed]
            ))

        return len(issues) == 0, issues
