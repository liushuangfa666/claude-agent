"""
Decomposer - 任务分解器

L2Decomposer: 任务分解与约束生成
L3TopDecomposer: 顶级分解器（全局规划）
L3SubDecomposer: 子域分解器

待增强功能：
- LLM 智能任务拆分：根据任务复杂度，LLM 判断是否拆分以及如何拆分
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from .models import (
    FORBIDDEN_ACTIONS,
    ComplexityLevel,
    Constraint,
    ConstraintType,
    CrossDomainDep,
    ExecutionPlan,
    L3Plan,
    SubdomainPlan,
    SubTask,
    Task,
)


class L2Decomposer:
    """
    L2 Decomposer: 任务分解与规划

    负责：
    1. 理解任务需求
    2. 拆分可并行的子任务
    3. 制定约束
    4. 输出执行计划
    """

    def __init__(self, llm_client: object | None = None):
        """
        初始化 Decomposer

        Args:
            llm_client: 可选的 LLM 客户端
        """
        self.llm_client = llm_client

    async def decompose(self, task: Task) -> ExecutionPlan:
        """
        分解任务，输出带约束的执行计划

        Args:
            task: 输入任务

        Returns:
            ExecutionPlan: 执行计划
        """
        plan = ExecutionPlan(
            id=str(uuid.uuid4()),
            level=ComplexityLevel.L2,
            metadata={
                "level": "L2",
                "parent_task": task.id,
            }
        )

        # 如果配置了 LLM 客户端，使用 LLM 辅助分解
        if self.llm_client:
            return await self._llm_assisted_decompose(task, plan)

        # 否则使用简单的启发式分解
        return self._heuristic_decompose(task, plan)

    async def _llm_assisted_decompose(self, task: Task, plan: ExecutionPlan) -> ExecutionPlan:
        """
        使用 LLM 辅助的任务分解

        Args:
            task: 输入任务
            plan: 执行计划

        Returns:
            ExecutionPlan: 分解后的执行计划
        """
        prompt = self._build_decompose_prompt(task)
        try:
            response = await self.llm_client.complete(prompt)
            subtasks = self._parse_decompose_response(response)

            for subtask_data in subtasks:
                subtask = Task(
                    id=str(uuid.uuid4()),
                    description=subtask_data.get("description", ""),
                    target_files=subtask_data.get("target_files", []),
                    estimated_steps=subtask_data.get("estimated_steps", 1),
                    dependencies=subtask_data.get("dependencies", []),
                )
                subtask.constraints = self.create_constraints(subtask)
                plan.tasks.append(subtask)
        except Exception:
            # LLM 分解失败时，使用启发式分解
            plan = self._heuristic_decompose(task, plan)

        return plan

    async def _analyze_and_split(self, task: Task) -> tuple[bool, list[Task]]:
        """
        LLM 分析并决定是否拆分任务

        根据任务复杂度，LLM 判断是否需要拆分以及如何拆分。

        Args:
            task: 输入任务

        Returns:
            Tuple[bool, List[Task]]: (是否需要拆分, 子任务列表)
        """
        prompt = self._build_split_decision_prompt(task)

        try:
            response = await self.llm_client.complete(prompt)
            data = self._parse_split_response(response)

            should_split = data.get("should_split", False)
            subtasks_data = data.get("subtasks", [])

            if not should_split or not subtasks_data:
                return False, [task]

            # 转换为 Task 对象
            subtasks = []
            for st in subtasks_data:
                subtask = Task(
                    id=st.get("id", str(uuid.uuid4())),
                    description=st["description"],
                    target_files=st.get("target_files", []),
                    estimated_steps=st.get("estimated_steps", 1),
                    dependencies=st.get("depends_on", []),
                )
                subtask.constraints = self.create_constraints(subtask)
                subtasks.append(subtask)

            return True, subtasks

        except Exception:
            # LLM 分析失败时，不拆分
            return False, [task]

    def _build_split_decision_prompt(self, task: Task) -> str:
        """
        构建拆分决策提示

        Args:
            task: 输入任务

        Returns:
            str: 提示文本
        """
        return f"""分析以下任务，判断最佳执行方式：

任务：{task.description}
目标文件：{', '.join(task.target_files) if task.target_files else '未指定'}
预估步数：{task.estimated_steps}

请返回 JSON：
{{
    "reasoning": "分析过程",
    "should_split": true/false,
    "subtasks": [
        {{
            "id": "step_1",
            "description": "具体做什么",
            "target_files": ["文件路径"],
            "estimated_steps": 1,
            "depends_on": []
        }}
    ]
}}

拆分原则：
- 步骤明确、能独立执行、无交叉依赖 → 不拆分
- 多模块、多文件、需要理解不同上下文 → 拆分为 2-4 个子任务
- 子任务必须有明确的描述和目标文件
- 子任务之间如果存在依赖关系，需要在 depends_on 中指定
"""

    def _parse_split_response(self, response: str) -> dict[str, Any]:
        """
        解析拆分决策响应

        Args:
            response: LLM 响应

        Returns:
            Dict: 解析后的数据
        """
        try:
            data = json.loads(response)
            return data
        except json.JSONDecodeError:
            return {}

    def _heuristic_decompose(self, task: Task, plan: ExecutionPlan) -> ExecutionPlan:
        """
        启发式任务分解

        当没有 LLM 客户端时，使用简单的启发式规则进行分解。

        Args:
            task: 输入任务
            plan: 执行计划

        Returns:
            ExecutionPlan: 分解后的执行计划
        """
        # 简单策略：将单个任务作为一个子任务
        subtask = Task(
            id=str(uuid.uuid4()),
            description=task.description,
            target_files=task.target_files,
            estimated_steps=task.estimated_steps,
        )
        subtask.constraints = self.create_constraints(subtask)
        plan.tasks.append(subtask)

        return plan

    def create_constraints(self, task: SubTask) -> list[Constraint]:
        """
        为子任务创建约束

        Args:
            task: 子任务

        Returns:
            List[Constraint]: 约束列表
        """
        constraints = []

        # 文件边界约束
        if task.target_files:
            constraints.append(Constraint(
                type=ConstraintType.FILE_SCOPE,
                files=task.target_files,
                description=f"只允许修改: {task.target_files}"
            ))

        # 依赖约束
        if task.dependencies:
            constraints.append(Constraint(
                type=ConstraintType.DEPENDS_ON,
                tasks=task.dependencies,
                description=f"等待完成: {task.dependencies}"
            ))

        # 回滚约束
        constraints.append(Constraint(
            type=ConstraintType.ROLLBACK_REQUIRED,
            method="git_branch",
            description="每个变更前创建backup branch"
        ))

        # 禁止危险操作
        constraints.append(Constraint(
            type=ConstraintType.FORBIDDEN,
            actions=FORBIDDEN_ACTIONS,
            description="禁止危险操作"
        ))

        return constraints

    def _build_decompose_prompt(self, task: Task) -> str:
        """
        构建分解提示

        Args:
            task: 输入任务

        Returns:
            str: 提示文本
        """
        return f"""分析以下任务并分解为可并行的子任务：

任务：{task.description}
目标文件：{task.target_files}

请返回JSON格式的子任务列表：
{{
    "subtasks": [
        {{
            "description": "子任务描述",
            "target_files": ["文件1", "文件2"],
            "estimated_steps": 3,
            "dependencies": []
        }}
    ]
}}
"""

    def _parse_decompose_response(self, response: str) -> list[dict[str, Any]]:
        """
        解析 LLM 分解响应

        Args:
            response: LLM 响应

        Returns:
            List[Dict]: 子任务列表
        """
        try:
            data = json.loads(response)
            return data.get("subtasks", [])
        except json.JSONDecodeError:
            return []

    def summarize(self, results: list[Any]) -> str:
        """
        汇总执行结果

        Args:
            results: 执行结果列表

        Returns:
            str: 摘要文本
        """
        total_tokens = 0
        summaries = []

        for result in results:
            if hasattr(result, "summary"):
                summaries.append(result.summary)
            if hasattr(result, "token_count"):
                total_tokens += result.token_count

        return f"""
        共完成 {len(results)} 个任务
        摘要:
        {chr(10).join(summaries)}
        """


class L3TopDecomposer:
    """
    顶级 Decomposer: 跨子域的全局规划

    负责：
    1. 识别子域边界
    2. 识别跨子域依赖
    3. 制定全局约束
    4. 为每个子域分配专属约束
    """

    def __init__(self, llm_client: object | None = None):
        self.llm_client = llm_client

    async def decompose(self, task: Task) -> L3Plan:
        """
        全局分解：识别子域、跨域依赖、统一约束

        Args:
            task: 输入任务

        Returns:
            L3Plan: L3 执行计划
        """
        # 识别子域
        subdomains = self._identify_subdomains(task)

        # 识别跨子域依赖
        cross_domain_deps = self._analyze_cross_dependencies(subdomains)

        # 制定全局约束
        global_constraints = self._create_global_constraints(task)

        # 为每个子域分配专属约束
        subdomain_plans = []
        for sd in subdomains:
            depends_on_list = [
                dep["target"] for dep in cross_domain_deps
                if dep["target"] == sd["id"]
            ]
            subdomain_plans.append(SubdomainPlan(
                subdomain_id=sd["id"],
                tasks=sd["tasks"],
                local_constraints=[
                    *global_constraints,
                    *sd.get("local_constraints", [])
                ],
                depends_on=depends_on_list,
                provides=sd.get("provides", []),
                allowed_files=sd.get("allowed_files", []),
                outputs_interface=sd.get("provides", []),
            ))

        return L3Plan(
            subdomains=subdomain_plans,
            cross_domain_dependencies=[
                CrossDomainDep(
                    source_subdomain=dep["source"],
                    target_subdomain=dep["target"],
                    interface_files=dep.get("interface_files", []),
                    description=dep.get("description", "")
                )
                for dep in cross_domain_deps
            ],
            global_review_criteria=self._create_review_criteria(),
            global_constraints=global_constraints,
        )

    def _identify_subdomains(self, task: Task) -> list[dict[str, Any]]:
        """
        识别子域

        Args:
            task: 输入任务

        Returns:
            List[Dict]: 子域列表
        """
        # 如果有 LLM 客户端，使用 LLM 辅助识别
        if self.llm_client:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                return loop.run_until_complete(self._llm_identify_subdomains(task))
            except RuntimeError:
                # 如果没有事件循环，创建一个简单的子域
                return self._simple_identify_subdomains(task)

        return self._simple_identify_subdomains(task)

    async def _llm_identify_subdomains(self, task: Task) -> list[dict[str, Any]]:
        """使用 LLM 识别子域"""
        prompt = f"""分析以下任务的子域划分：

任务：{task.description}

请返回JSON格式的子域列表：
{{
    "subdomains": [
        {{
            "id": "frontend",
            "description": "前端子域",
            "tasks": [],
            "provides": ["API接口定义"],
            "allowed_files": ["src/frontend/**"]
        }}
    ]
}}
"""
        try:
            response = await self.llm_client.complete(prompt)
            import json
            data = json.loads(response)
            return data.get("subdomains", [])
        except Exception:
            return self._simple_identify_subdomains(task)

    def _simple_identify_subdomains(self, task: Task) -> list[dict[str, Any]]:
        """简单的子域识别策略"""
        return [
            {
                "id": "default",
                "description": "默认子域",
                "tasks": [
                    Task(
                        id=str(uuid.uuid4()),
                        description=task.description,
                        target_files=task.target_files,
                        estimated_steps=task.estimated_steps,
                    )
                ],
                "provides": [],
                "allowed_files": task.target_files,
                "local_constraints": [],
            }
        ]

    def _analyze_cross_dependencies(self, subdomains: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        分析跨子域依赖

        Args:
            subdomains: 子域列表

        Returns:
            List[Dict]: 跨域依赖列表
        """
        # 简单的依赖分析：假设没有跨域依赖
        return []

    def _create_global_constraints(self, task: Task) -> list[Constraint]:
        """
        创建全局约束

        Args:
            task: 输入任务

        Returns:
            List[Constraint]: 全局约束列表
        """
        return [
            Constraint(
                type=ConstraintType.NO_CROSS_DOMAIN_FILES,
                description="子域只能修改自己领域的文件"
            ),
            Constraint(
                type=ConstraintType.INTERFACE_FROZEN,
                files=task.target_files,
                description="跨域接口文件在审核通过前不可修改"
            ),
            Constraint(
                type=ConstraintType.GLOBAL_ROLLBACK,
                method="full_backup",
                description="每个子域开始前创建全局快照"
            ),
        ]

    def _create_review_criteria(self) -> list[str]:
        """
        创建审核标准

        Returns:
            List[str]: 审核标准列表
        """
        return [
            "子域划分合理，无重叠",
            "跨域依赖无环",
            "接口契约完整",
            "回滚方案可行",
        ]


class L3SubDecomposer:
    """
    子 Decomposer: 单个子域的详细规划

    负责：
    1. 按依赖关系排序任务
    2. 添加子域级约束
    3. 处理跨子域依赖等待
    """

    def __init__(self, subdomain_plan: SubdomainPlan):
        """
        初始化子域 Decomposer

        Args:
            subdomain_plan: 子域计划
        """
        self.plan = subdomain_plan

    async def decompose(self) -> ExecutionPlan:
        """
        子域内分解：创建可执行的微任务

        Returns:
            ExecutionPlan: 子域执行计划
        """
        # 按依赖关系排序
        sorted_tasks = self._topological_sort(self.plan.tasks)

        # 创建执行计划
        execution_plan = ExecutionPlan(
            id=str(uuid.uuid4()),
            level=ComplexityLevel.L3,
            metadata={
                "subdomain_id": self.plan.subdomain_id,
            },
        )

        for task in sorted_tasks:
            # 检查是否依赖其他子域
            if task.depends_on_subdomain:
                task.add_constraint(Constraint(
                    type=ConstraintType.WAIT_FOR_EXTERNAL,
                    source=f"subdomain:{task.depends_on_subdomain}",
                    condition="output_ready"
                ))

            execution_plan.tasks.append(task)

        return execution_plan

    def _topological_sort(self, tasks: list[Task]) -> list[Task]:
        """
        拓扑排序

        Args:
            tasks: 任务列表

        Returns:
            List[Task]: 排序后的任务列表
        """
        # 简单的拓扑排序
        sorted_tasks = []
        remaining = tasks.copy()
        completed = set()

        while remaining:
            # 找到所有依赖都已完成的任务
            ready = [
                t for t in remaining
                if all(dep in completed for dep in t.dependencies)
            ]

            if not ready:
                # 如果没有就绪任务但还有剩余任务，说明有循环依赖
                # 将剩余任务添加到结果（按原始顺序）
                sorted_tasks.extend(remaining)
                break

            sorted_tasks.extend(ready)
            for t in ready:
                completed.add(t.id)
                remaining.remove(t)

        return sorted_tasks

    def _create_shared_constraints(self) -> list[Constraint]:
        """
        创建该子域所有执行 Agent 共享的约束

        Returns:
            List[Constraint]: 共享约束列表
        """
        return [
            Constraint(
                type=ConstraintType.SUBDOMAIN_BOUNDARY,
                files=self.plan.allowed_files,
                description=f"本子域({self.plan.subdomain_id})只能修改这些文件"
            ),
            Constraint(
                type=ConstraintType.OUTPUTS_FOR_OTHERS,
                files=self.plan.outputs_interface,
                description="这些是供给其他子域使用的输出，必须按格式生成"
            )
        ]
