"""
跨域协调模块 - Phase 3 实现

提供子域间消息传递、跨域状态同步、分布式回滚功能。
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

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
        from .models import ComplexityLevel
        self.llm_client = llm_client
        self.history = RouterHistory(history_file)
        self.custom_rules = CustomRuleRegistry()
        self.ComplexityLevel = ComplexityLevel

    def add_rule(self, pattern: str, score: int, level: str) -> None:
        """添加自定义规则（简洁API）"""
        self.custom_rules.add_rule(pattern, score, level)

    def explain_route(self, user_input: str) -> tuple[Any, RouteExplanation]:
        """获取路由决策及其可解释性

        Returns:
            (RouteResult, RouteExplanation)
        """
        from .router import COMPLEXITY_RULES
        import re

        explanation = RouteExplanation()

        all_rules = list(COMPLEXITY_RULES) + [
            (r["pattern"], r["score"], self.ComplexityLevel(r["level"]))
            for r in self.custom_rules.get_rules()
        ]

        matched = []
        for pattern, weight, level in all_rules:
            if re.search(pattern, user_input, re.IGNORECASE):
                matched.append({
                    "pattern": pattern,
                    "weight": weight,
                    "level": level.value,
                })
                explanation.matched_rules.append(pattern)

        explanation.rule_details = matched

        similar = self.history.find_similar_patterns(user_input)
        explanation.historical_similar = similar

        if not matched and similar:
            explanation.suggestions.append(
                f"根据历史，有 {len(similar)} 个类似输入被判定为不同级别"
            )

        from .router import route_simple
        result = route_simple(user_input)
        return result, explanation

    def get_statistics(self) -> dict[str, Any]:
        """获取路由统计信息"""
        return {
            "total_history": len(self.history._history),
            "level_distribution": self.history.get_level_distribution(),
            "custom_rules_count": len(self.custom_rules.get_rules()),
        }


# ============================================================================
# Phase 2: 导出便捷函数
# ============================================================================

def create_explainable_router(llm_client: object | None = None) -> ExplainableHybridRouter:
    """创建可解释性 Router"""
    return ExplainableHybridRouter(llm_client=llm_client)


# ============================================================================
# Phase 3: 跨域协调
# ============================================================================


@dataclass
class CrossDomainMessage:
    """跨域消息"""
    from_subdomain: str
    to_subdomain: str
    content: str
    timestamp: float = field(default_factory=time.time)
    message_type: str = "default"

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_subdomain,
            "to": self.to_subdomain,
            "content": self.content,
            "timestamp": self.timestamp,
            "type": self.message_type,
        }


class CrossDomainMessenger:
    """子域间消息传递"""

    def __init__(self):
        self._messages: list[CrossDomainMessage] = []
        self._subscriptions: dict[str, list[Callable[[CrossDomainMessage], None]]] = {}

    def send_message(
        self,
        from_subdomain: str,
        to_subdomain: str,
        content: str,
        message_type: str = "default",
    ) -> CrossDomainMessage:
        """发送消息到目标子域"""
        msg = CrossDomainMessage(
            from_subdomain=from_subdomain,
            to_subdomain=to_subdomain,
            content=content,
            message_type=message_type,
        )
        self._messages.append(msg)

        self._notify_subscribers(msg)
        return msg

    def get_messages(self, subdomain: str) -> list[CrossDomainMessage]:
        """获取发给某子域的所有消息"""
        return [m for m in self._messages if m.to_subdomain == subdomain]

    def get_messages_from(self, subdomain: str) -> list[CrossDomainMessage]:
        """获取某子域发出的所有消息"""
        return [m for m in self._messages if m.from_subdomain == subdomain]

    def subscribe(
        self,
        subdomain: str,
        callback: Callable[[CrossDomainMessage], None],
    ) -> None:
        """订阅某子域的消息"""
        if subdomain not in self._subscriptions:
            self._subscriptions[subdomain] = []
        self._subscriptions[subdomain].append(callback)

    def _notify_subscribers(self, msg: CrossDomainMessage) -> None:
        """通知订阅者"""
        callbacks = self._subscriptions.get(msg.to_subdomain, [])
        for callback in callbacks:
            try:
                callback(msg)
            except Exception:
                pass

    def clear(self) -> None:
        """清空所有消息"""
        self._messages.clear()


@dataclass
class StateChangeEvent:
    """状态变更事件"""
    key: str
    value: Any
    subdomain: str | None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "subdomain": self.subdomain,
            "timestamp": self.timestamp,
        }


class CrossDomainStateManager:
    """跨域状态同步"""

    def __init__(self):
        self._state: dict[str, Any] = {}
        self._history: list[StateChangeEvent] = []
        self._subscriptions: dict[str, list[Callable[[StateChangeEvent], None]]] = {}

    def set_state(self, key: str, value: Any, subdomain: str | None = None) -> None:
        """设置全局状态"""
        event = StateChangeEvent(key=key, value=value, subdomain=subdomain)
        self._state[key] = value
        self._history.append(event)
        self._notify_subscribers(event)

    def get_state(self, key: str) -> Any:
        """获取状态值"""
        return self._state.get(key)

    def get_all_state(self) -> dict[str, Any]:
        """获取所有状态"""
        return self._state.copy()

    def subscribe(
        self,
        key: str,
        callback: Callable[[StateChangeEvent], None],
    ) -> None:
        """订阅状态变化"""
        if key not in self._subscriptions:
            self._subscriptions[key] = []
        self._subscriptions[key].append(callback)

    def _notify_subscribers(self, event: StateChangeEvent) -> None:
        """通知订阅者"""
        callbacks = self._subscriptions.get(event.key, [])
        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                pass

    def get_history(self, key: str | None = None) -> list[StateChangeEvent]:
        """获取状态变更历史"""
        if key:
            return [e for e in self._history if e.key == key]
        return self._history.copy()

    def clear(self) -> None:
        """清空所有状态"""
        self._state.clear()
        self._history.clear()


@dataclass
class RollbackInfo:
    """回滚信息"""
    subdomain: str
    rollback_fn: Callable
    depends_on: list[str] = field(default_factory=list)
    registered_at: float = field(default_factory=time.time)

    def execute(self) -> Any:
        """执行回滚"""
        return self.rollback_fn()


class DistributedRollbackManager:
    """分布式回滚管理器"""

    def __init__(self):
        self._rollbacks: dict[str, RollbackInfo] = {}
        self._execution_history: list[dict[str, Any]] = []

    def register_rollback(
        self,
        subdomain: str,
        rollback_fn: Callable,
        depends_on: list[str] | None = None,
    ) -> None:
        """注册回滚函数

        Args:
            subdomain: 子域ID
            rollback_fn: 回滚函数
            depends_on: 依赖的其他子域ID列表
        """
        info = RollbackInfo(
            subdomain=subdomain,
            rollback_fn=rollback_fn,
            depends_on=depends_on or [],
        )
        self._rollbacks[subdomain] = info

    def unregister(self, subdomain: str) -> bool:
        """取消注册"""
        if subdomain in self._rollbacks:
            del self._rollbacks[subdomain]
            return True
        return False

    def get_rollback_order(self) -> list[str]:
        """计算回滚顺序（按依赖反向）"""
        visited = set()
        order: list[str] = []

        def visit(subdomain: str) -> None:
            if subdomain in visited:
                return
            visited.add(subdomain)

            rollback_info = self._rollbacks.get(subdomain)
            if rollback_info:
                for dep in reversed(rollback_info.depends_on):
                    if dep in self._rollbacks:
                        visit(dep)

            order.append(subdomain)

        for subdomain in self._rollbacks:
            visit(subdomain)

        return order

    async def execute_global_rollback(self) -> dict[str, Any]:
        """执行全局回滚（按依赖反向顺序）"""
        order = self.get_rollback_order()
        results = {}
        success = True

        for subdomain in reversed(order):
            rollback_info = self._rollbacks.get(subdomain)
            if rollback_info:
                try:
                    result = rollback_info.execute()
                    results[subdomain] = {"status": "success", "result": result}
                except Exception as e:
                    results[subdomain] = {"status": "error", "error": str(e)}
                    success = False

        self._execution_history.append({
            "order": order,
            "results": results,
            "success": success,
            "timestamp": time.time(),
        })

        return {
            "success": success,
            "executed_order": order,
            "results": results,
        }

    def get_rollback_info(self, subdomain: str) -> RollbackInfo | None:
        """获取回滚信息"""
        return self._rollbacks.get(subdomain)

    def clear(self) -> None:
        """清空所有回滚注册"""
        self._rollbacks.clear()
        self._execution_history.clear()


# ============================================================================
# 全局单例
# ============================================================================

_messenger: CrossDomainMessenger | None = None
_state_manager: CrossDomainStateManager | None = None
_rollback_manager: DistributedRollbackManager | None = None


def get_cross_domain_messenger() -> CrossDomainMessenger:
    """获取跨域消息传递器单例"""
    global _messenger
    if _messenger is None:
        _messenger = CrossDomainMessenger()
    return _messenger


def get_cross_domain_state_manager() -> CrossDomainStateManager:
    """获取跨域状态管理器单例"""
    global _state_manager
    if _state_manager is None:
        _state_manager = CrossDomainStateManager()
    return _state_manager


def get_distributed_rollback_manager() -> DistributedRollbackManager:
    """获取分布式回滚管理器单例"""
    global _rollback_manager
    if _rollback_manager is None:
        _rollback_manager = DistributedRollbackManager()
    return _rollback_manager


def reset_cross_domain_services() -> None:
    """重置所有跨域服务（用于测试）"""
    global _messenger, _state_manager, _rollback_manager
    _messenger = None
    _state_manager = None
    _rollback_manager = None
