"""
Router 增强模块 - Phase 2 实现

提供 Router 学习历史、自定义规则注入、决策可解释性功能。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import ComplexityLevel, RouteResult

_history_file = Path(__file__).parent / "router_history.json"


class RouterHistory:
    """Router 历史决策存储"""

    def __init__(self, history_file: Path | None = None):
        self.history_file = history_file or _history_file
        self._history: list[dict[str, Any]] = []
        self._load_history()

    def _load_history(self) -> None:
        """从文件加载历史"""
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self._history = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._history = []

    def _save_history(self) -> None:
        """保存历史到文件"""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self._history[-100:], f, ensure_ascii=False)
        except IOError:
            pass

    def record(self, user_input: str, level: str, confidence: float, method: str) -> None:
        """记录一次路由决策"""
        self._history.append({
            "input": user_input[:100],
            "level": level,
            "confidence": confidence,
            "method": method,
            "timestamp": time.time(),
        })
        self._save_history()

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """获取最近的历史记录"""
        return self._history[-limit:]

    def get_level_distribution(self) -> dict[str, int]:
        """获取历史中各level的分布"""
        dist = {"L1": 0, "L2": 0, "L3": 0}
        for record in self._history:
            dist[record["level"]] = dist.get(record["level"], 0) + 1
        return dist

    def find_similar_patterns(self, user_input: str) -> list[dict[str, Any]]:
        """查找相似的历史输入"""
        keywords = set(user_input.lower().split()[:5])
        similar = []
        for record in self._history[-50:]:
            record_keywords = set(record["input"].lower().split()[:5])
            overlap = len(keywords & record_keywords)
            if overlap >= 2:
                similar.append(record)
        return similar[:5]


class CustomRuleRegistry:
    """自定义规则注册表"""

    def __init__(self):
        self._rules: list[dict[str, Any]] = []

    def add_rule(self, pattern: str, score: int, level: str) -> None:
        """添加自定义规则

        Args:
            pattern: 匹配模式（正则表达式）
            score: 分值
            level: 触发的复杂度级别 "L1"/"L2"/"L3"
        """
        self._rules.append({
            "pattern": pattern,
            "score": score,
            "level": level,
        })

    def remove_rule(self, pattern: str) -> bool:
        """移除规则"""
        for i, rule in enumerate(self._rules):
            if rule["pattern"] == pattern:
                self._rules.pop(i)
                return True
        return False

    def get_rules(self) -> list[dict[str, Any]]:
        """获取所有规则"""
        return self._rules.copy()

    def clear(self) -> None:
        """清空所有自定义规则"""
        self._rules.clear()


@dataclass
class RouteExplanation:
    """路由决策可解释性输出"""
    matched_rules: list[str] = field(default_factory=list)
    rule_details: list[dict[str, Any]] = field(default_factory=list)
    historical_similar: list[dict[str, Any]] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched_rules": self.matched_rules,
            "rule_details": self.rule_details,
            "historical_similar": self.historical_similar,
            "suggestions": self.suggestions,
        }


class ExplainableHybridRouter:
    """支持可解释性的 Router"""

    def __init__(
        self,
        llm_client: object | None = None,
        history_file: Path | None = None,
    ):
        self.llm_client = llm_client
        self.history = RouterHistory(history_file)
        self.custom_rules = CustomRuleRegistry()

    def add_rule(self, pattern: str, score: int, level: str) -> None:
        """添加自定义规则（简洁API）"""
        self.custom_rules.add_rule(pattern, score, level)

    def explain_route(self, user_input: str) -> tuple[RouteResult, RouteExplanation]:
        """获取路由决策及其可解释性

        Returns:
            (RouteResult, RouteExplanation)
        """
        from .router import COMPLEXITY_RULES

        explanation = RouteExplanation()

        all_rules = list(COMPLEXITY_RULES) + [
            (r["pattern"], r["score"], ComplexityLevel(r["level"]))
            for r in self.custom_rules.get_rules()
        ]

        matched = []
        total_score = 0
        for pattern, weight, level in all_rules:
            if re.search(pattern, user_input, re.IGNORECASE):
                matched.append({
                    "pattern": pattern,
                    "weight": weight,
                    "level": level.value,
                })
                explanation.matched_rules.append(pattern)
                total_score += weight

        explanation.rule_details = matched

        similar = self.history.find_similar_patterns(user_input)
        explanation.historical_similar = similar

        if not matched and similar:
            explanation.suggestions.append(
                f"根据历史，有 {len(similar)} 个类似输入被判定为不同级别"
            )

        if total_score >= 8:
            result = RouteResult(
                level=ComplexityLevel.L3,
                reasoning=f"高权重规则触发: {[r['pattern'] for r in matched]}",
                confidence=0.95,
                method="explainable_rule_based",
            )
        elif total_score >= 3:
            result = RouteResult(
                level=ComplexityLevel.L2,
                reasoning=f"中权重规则触发: {[r['pattern'] for r in matched]}",
                confidence=0.85,
                method="explainable_rule_based",
            )
        else:
            result = RouteResult(
                level=ComplexityLevel.L1,
                reasoning="未命中明确规则",
                confidence=0.5,
                method="explainable_rule_based",
            )

        return result, explanation

    def get_statistics(self) -> dict[str, Any]:
        """获取路由统计信息"""
        return {
            "total_history": len(self.history._history),
            "level_distribution": self.history.get_level_distribution(),
            "custom_rules_count": len(self.custom_rules.get_rules()),
        }


def create_explainable_router(llm_client: object | None = None) -> ExplainableHybridRouter:
    """创建可解释性 Router"""
    return ExplainableHybridRouter(llm_client=llm_client)
