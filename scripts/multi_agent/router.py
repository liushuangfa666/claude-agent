"""
复杂度路由 - HybridRouter 实现

根据用户输入的复杂度自动选择 L1/L2/L3 执行架构。
"""

from __future__ import annotations

import re

from .models import ComplexityLevel, RouteResult

# 复杂度评估规则
COMPLEXITY_RULES = [
    # 高权重规则（直接触发L3）
    (r"(删除|清空|drop|truncate)", 10, ComplexityLevel.L3),
    (r"(重构|重写|迁移|迁移数据库)", 8, ComplexityLevel.L3),
    (r"(架构|设计模式|微服务|分布式系统)", 8, ComplexityLevel.L3),
    (r"(生产环境|线上|发布版本)", 8, ComplexityLevel.L3),  # 提升到L3

    # 中等权重规则（触发L2）
    (r"(多个|分别|同时|并行)", 3, ComplexityLevel.L2),
    (r"(前端|后端|数据库|API)", 3, ComplexityLevel.L2),
    (r"(探索|研究|分析|调查)", 2, ComplexityLevel.L2),

    # 低权重规则（触发L1）
    (r"(修复|解决|排查|单文件)", 1, ComplexityLevel.L1),
]


class HybridRouter:
    """
    混合路由器：规则 + LLM 辅助

    快速规则评估 (< 10ms) 优先，命中高权重规则直接返回结果。
    对于边界情况，使用 LLM 辅助判断。
    """

    def __init__(self, llm_client: object | None = None):
        """
        初始化路由器

        Args:
            llm_client: 可选的 LLM 客户端，用于边界情况的 LLM 辅助判断
        """
        self.llm_client = llm_client

    async def route(self, user_input: str) -> RouteResult:
        """
        执行路由决策

        Args:
            user_input: 用户输入

        Returns:
            RouteResult: 路由结果
        """
        # L1: 规则快速判断
        fast_result = self._rule_based_route(user_input)
        if fast_result.confidence >= 0.9:
            return fast_result

        # L2: 如果配置了 LLM 客户端，使用 LLM 辅助判断
        if self.llm_client:
            return await self._llm_assisted_route(user_input)

        # 如果没有 LLM 客户端，返回规则判断结果（低置信度）
        return fast_result

    def _rule_based_route(self, user_input: str) -> RouteResult:
        """
        快速规则判断 - 毫秒级

        Args:
            user_input: 用户输入

        Returns:
            RouteResult: 基于规则判断的路由结果
        """
        score = 0
        matched_rules = []

        for pattern, weight, level in COMPLEXITY_RULES:
            if re.search(pattern, user_input, re.IGNORECASE):
                score += weight
                matched_rules.append((pattern, level))

        if score >= 8:
            return RouteResult(
                level=ComplexityLevel.L3,
                reasoning=f"高权重规则触发: {[r[0] for r in matched_rules]}",
                confidence=0.95,
                method="rule_based",
            )
        elif score >= 3:
            return RouteResult(
                level=ComplexityLevel.L2,
                reasoning=f"中权重规则触发: {[r[0] for r in matched_rules]}",
                confidence=0.85,
                method="rule_based",
            )
        else:
            return RouteResult(
                level=ComplexityLevel.L1,
                reasoning="未命中明确规则",
                confidence=0.5,  # 低置信度，需要LLM辅助
                method="rule_based",
            )

    async def _llm_assisted_route(self, user_input: str) -> RouteResult:
        """
        LLM 辅助判断 - 用于边界情况

        Args:
            user_input: 用户输入

        Returns:
            RouteResult: 基于 LLM 判断的路由结果
        """
        prompt = self._build_llm_prompt(user_input)

        try:
            response = await self.llm_client.complete(prompt)
            return self._parse_llm_response(response)
        except Exception:
            # LLM 判断失败时，回退到规则判断
            return self._rule_based_route(user_input)

    def _build_llm_prompt(self, user_input: str) -> str:
        """
        构建 LLM 提示

        Args:
            user_input: 用户输入

        Returns:
            str: 提示文本
        """
        return f"""分析以下需求的复杂度：

需求：{user_input}

判断标准：
- L1: 单文件、单步骤、明确指令
- L2: 多文件、多步骤、需理解上下文
- L3: 多模块、风险操作、需验证、架构设计

返回JSON格式：
{{
    "level": "L1|L2|L3",
    "reasoning": "判断理由",
    "estimated_tasks": 预估任务数
}}
"""

    def _parse_llm_response(self, response: str) -> RouteResult:
        """
        解析 LLM 响应

        Args:
            response: LLM 响应文本

        Returns:
            RouteResult: 解析后的路由结果
        """
        import json

        try:
            data = json.loads(response)
            level_str = data.get("level", "L1").upper()
            if level_str not in ["L1", "L2", "L3"]:
                level_str = "L1"

            return RouteResult(
                level=ComplexityLevel(level_str),
                reasoning=data.get("reasoning", ""),
                confidence=0.8,
                method="llm_assisted",
                estimated_tasks=data.get("estimated_tasks"),
            )
        except (json.JSONDecodeError, ValueError):
            # 解析失败时，返回默认 L1 结果
            return RouteResult(
                level=ComplexityLevel.L1,
                reasoning="LLM响应解析失败，默认L1",
                confidence=0.3,
                method="llm_assisted",
            )


def route_simple(user_input: str) -> RouteResult:
    """
    简单的同步路由函数（仅使用规则判断）

    Args:
        user_input: 用户输入

    Returns:
        RouteResult: 路由结果
    """
    router = HybridRouter()
    return router._rule_based_route(user_input)
