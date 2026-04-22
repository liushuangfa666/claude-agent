"""
自我优化模块 - Phase 4 实现

提供执行效率统计、拆分策略优化、审核规则自适应功能。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

_stats_file = Path(__file__).parent / "execution_stats.json"


@dataclass
class ExecutionStats:
    """单次执行统计"""
    level: str
    duration: float
    task_count: int
    success: bool
    token_count: int = 0
    timestamp: float = field(default_factory=time.time)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "duration": self.duration,
            "task_count": self.task_count,
            "success": self.success,
            "token_count": self.token_count,
            "timestamp": self.timestamp,
            "error_message": self.error_message,
        }


class ExecutionStatsCollector:
    """执行效率统计收集器"""

    def __init__(self, stats_file: Path | None = None):
        self.stats_file = stats_file or _stats_file
        self._stats: list[ExecutionStats] = []
        self._load_stats()

    def _load_stats(self) -> None:
        """从文件加载统计"""
        if self.stats_file.exists():
            try:
                with open(self.stats_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        self._stats.append(ExecutionStats(**item))
            except (json.JSONDecodeError, IOError, TypeError):
                self._stats = []

    def _save_stats(self) -> None:
        """保存统计到文件"""
        try:
            with open(self.stats_file, "w", encoding="utf-8") as f:
                json.dump([s.to_dict() for s in self._stats[-200:]], f, ensure_ascii=False)
        except IOError:
            pass

    def record_execution(
        self,
        level: str,
        duration: float,
        task_count: int,
        success: bool,
        token_count: int = 0,
        error_message: str | None = None,
    ) -> None:
        """记录一次执行"""
        stats = ExecutionStats(
            level=level,
            duration=duration,
            task_count=task_count,
            success=success,
            token_count=token_count,
            error_message=error_message,
        )
        self._stats.append(stats)
        self._save_stats()

    def get_stats(self, limit: int = 50) -> list[ExecutionStats]:
        """获取最近的统计"""
        return self._stats[-limit:]

    def get_average_duration(self, level: str | None = None) -> float:
        """获取平均执行时间"""
        filtered = self._stats if level is None else [s for s in self._stats if s.level == level]
        if not filtered:
            return 0.0
        return sum(s.duration for s in filtered) / len(filtered)

    def get_success_rate(self, level: str | None = None) -> float:
        """获取成功率"""
        filtered = self._stats if level is None else [s for s in self._stats if s.level == level]
        if not filtered:
            return 0.0
        return sum(1 for s in filtered if s.success) / len(filtered)

    def get_summary(self) -> dict[str, Any]:
        """获取统计摘要"""
        total = len(self._stats)
        if total == 0:
            return {
                "total_executions": 0,
                "overall_success_rate": 0.0,
                "avg_duration": 0.0,
                "by_level": {},
            }

        total_success = sum(1 for s in self._stats if s.success)
        by_level = {}
        for level in ["L1", "L2", "L3"]:
            level_stats = [s for s in self._stats if s.level == level]
            if level_stats:
                by_level[level] = {
                    "count": len(level_stats),
                    "success_rate": sum(1 for s in level_stats if s.success) / len(level_stats),
                    "avg_duration": sum(s.duration for s in level_stats) / len(level_stats),
                    "avg_task_count": sum(s.task_count for s in level_stats) / len(level_stats),
                }

        return {
            "total_executions": total,
            "overall_success_rate": total_success / total,
            "avg_duration": sum(s.duration for s in self._stats) / total,
            "by_level": by_level,
        }


class SplitStrategyAnalyzer:
    """拆分策略分析器"""

    def __init__(self, stats_collector: ExecutionStatsCollector | None = None):
        self.stats_collector = stats_collector or ExecutionStatsCollector()

    def analyze_split_effectiveness(self) -> dict[str, Any]:
        """分析拆分策略效果，返回优化建议"""
        suggestions = []

        stats = self.stats_collector._stats
        if len(stats) < 5:
            return {
                "suggestions": ["数据不足，需要至少5次执行记录才能进行分析"],
                "analyzed_count": len(stats),
            }

        for level in ["L2", "L3"]:
            level_stats = [s for s in stats if s.level == level]
            if not level_stats:
                continue

            success_rate = sum(1 for s in level_stats if s.success) / len(level_stats)
            avg_tasks = sum(s.task_count for s in level_stats) / len(level_stats)
            avg_duration = sum(s.duration for s in level_stats) / len(level_stats)

            if success_rate < 0.7 and avg_tasks > 5:
                suggestions.append(
                    f"{level} 级任务平均 {avg_tasks:.1f} 个子任务，成功率仅 {success_rate:.1%}。"
                    "建议减少子任务数量，或考虑是否应该升级到更高复杂度级别。"
                )

            if success_rate < 0.5:
                suggestions.append(
                    f"{level} 级任务成功率过低 ({success_rate:.1%})。"
                    "可能需要重新评估 LLM 拆分策略。"
                )

            if avg_duration > 120 and avg_tasks < 3:
                suggestions.append(
                    f"{level} 级任务平均耗时 {avg_duration:.1f}秒，但子任务较少。"
                    "可能是 LLM 响应慢或执行中有阻塞。"
                )

        if not suggestions:
            suggestions.append("当前拆分策略运行良好，未检测到明显问题。")

        return {
            "suggestions": suggestions,
            "analyzed_count": len(stats),
            "timestamp": time.time(),
        }

    def get_task_count_trend(self) -> dict[str, Any]:
        """获取子任务数量趋势"""
        stats = self.stats_collector._stats
        recent = stats[-20:] if len(stats) > 20 else stats

        by_level = {}
        for level in ["L2", "L3"]:
            level_tasks = [s.task_count for s in recent if s.level == level]
            if level_tasks:
                by_level[level] = {
                    "recent_avg": sum(level_tasks) / len(level_tasks),
                    "count": len(level_tasks),
                }

        return {
            "by_level": by_level,
            "total_analyzed": len(recent),
        }


class AdaptiveReviewerRules:
    """自适应审核规则"""

    def __init__(self):
        self._rejected_patterns: dict[str, int] = {}
        self._suggested_rules: list[str] = []

    def record_rejection(self, pattern: str) -> None:
        """记录一次审核拒绝"""
        self._rejected_patterns[pattern] = self._rejected_patterns.get(pattern, 0) + 1

    def suggest_rules(self, min_frequency: int = 3) -> list[str]:
        """基于执行历史建议新规则

        Args:
            min_frequency: 最小出现频率才建议

        Returns:
            建议的规则列表
        """
        suggestions = []

        for pattern, count in self._rejected_patterns.items():
            if count >= min_frequency:
                suggestions.append(
                    f"频繁被拒绝的模式 '{pattern}' (出现 {count} 次)，"
                    "建议在 Router 阶段直接路由到更高复杂度级别。"
                )

        if not suggestions:
            suggestions.append("未检测到需要自适应规则调整的模式。")

        return suggestions

    def get_top_rejected_patterns(self, limit: int = 5) -> list[dict[str, Any]]:
        """获取最频繁被拒绝的模式"""
        sorted_patterns = sorted(
            self._rejected_patterns.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return [
            {"pattern": p, "count": c}
            for p, c in sorted_patterns[:limit]
        ]

    def clear(self) -> None:
        """清空记录"""
        self._rejected_patterns.clear()
        self._suggested_rules.clear()


# ============================================================================
# 全局单例
# ============================================================================

_stats_collector: ExecutionStatsCollector | None = None
_split_analyzer: SplitStrategyAnalyzer | None = None
_reviewer_rules: AdaptiveReviewerRules | None = None


def get_stats_collector() -> ExecutionStatsCollector:
    """获取统计收集器单例"""
    global _stats_collector
    if _stats_collector is None:
        _stats_collector = ExecutionStatsCollector()
    return _stats_collector


def get_split_analyzer() -> SplitStrategyAnalyzer:
    """获取拆分策略分析器单例"""
    global _split_analyzer
    if _split_analyzer is None:
        _split_analyzer = SplitStrategyAnalyzer()
    return _split_analyzer


def get_adaptive_reviewer_rules() -> AdaptiveReviewerRules:
    """获取自适应审核规则单例"""
    global _reviewer_rules
    if _reviewer_rules is None:
        _reviewer_rules = AdaptiveReviewerRules()
    return _reviewer_rules


def reset_self_optimization_services() -> None:
    """重置所有自我优化服务（用于测试）"""
    global _stats_collector, _split_analyzer, _reviewer_rules
    _stats_collector = None
    _split_analyzer = None
    _reviewer_rules = None
