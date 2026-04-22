"""
层级Session管理 - Multi-Agent Session

支持 L1/L2/L3 各层的独立 Session 管理，防止 token 爆炸。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


def _get_session_manager():
    """获取SessionManager类"""
    try:
        from ..session.manager import SessionManager
        return SessionManager
    except ImportError:
        return None


@dataclass
class LayerSession:
    """层级Session"""
    session_id: str
    parent_session_id: str | None = None
    level: int = 1  # 1, 2, or 3
    subdomain_id: str | None = None  # L3 子域ID
    created_at: datetime = field(default_factory=datetime.now)
    messages: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str) -> None:
        """添加消息"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })

    def get_summary(self) -> str:
        """获取摘要"""
        total_tokens = self.metadata.get("total_tokens", 0)
        return f"""
Session: {self.session_id}
Level: L{self.level}
Messages: {len(self.messages)}
Tokens: {total_tokens}
Created: {self.created_at.isoformat()}
"""

    def summarize_for_parent(self, child_results: list[Any]) -> str:
        """
        子层结果汇总为摘要，供父层使用

        Args:
            child_results: 子层结果列表

        Returns:
            str: 摘要文本
        """
        summaries = []
        total_tokens = 0

        for result in child_results:
            if hasattr(result, "summary") and result.summary:
                summaries.append(result.summary)
            if hasattr(result, "token_count"):
                total_tokens += result.token_count

        return f"""
        共完成 {len(child_results)} 个任务，消耗 {total_tokens} tokens
        摘要:
        {chr(10).join(summaries)}
        """


class LayerContextManager:
    """
    每层上下文管理器：防止 token 爆炸
    """

    def __init__(self, max_tokens_per_layer: int = 100000):
        """
        初始化上下文管理器

        Args:
            max_tokens_per_layer: 每层最大 token 数
        """
        self.max_tokens_per_layer = max_tokens_per_layer

    def build_layer_context(
        self,
        level: int,
        task: Any,
    ) -> dict[str, Any]:
        """
        根据层级构建精简上下文

        Args:
            level: 层级
            task: 任务

        Returns:
            Dict[str, Any]: 上下文
        """
        if level == 3:
            return {
                "task": task.description if hasattr(task, "description") else str(task),
                "constraints": task.constraints if hasattr(task, "constraints") else [],
                "inputs_summary": self._get_inputs_summary(task),
                "parent_expectation": (
                    task.parent_summary if hasattr(task, "parent_summary") else ""
                ),
            }
        elif level == 2:
            return {
                "subdomain_goal": task.goal if hasattr(task, "goal") else str(task),
                "shared_constraints": (
                    task.shared_constraints if hasattr(task, "shared_constraints") else []
                ),
                "outputs_for_siblings": (
                    task.provides_to_others if hasattr(task, "provides_to_others") else []
                ),
            }
        else:  # level 1
            return {
                "original_request": (
                    task.original_request if hasattr(task, "original_request") else str(task)
                ),
                "all_subdomain_results": (
                    task.children_summaries if hasattr(task, "children_summaries") else []
                ),
            }

    def _get_inputs_summary(self, task: Any) -> str:
        """
        获取输入摘要

        Args:
            task: 任务

        Returns:
            str: 输入摘要
        """
        if hasattr(task, "inputs"):
            inputs = task.inputs
            if isinstance(inputs, list):
                return f"{len(inputs)} 个输入项"
            return str(inputs)
        return "无外部输入"

    def should_compact(self, session: LayerSession) -> bool:
        """
        检查是否需要压缩

        Args:
            session: Session

        Returns:
            bool: 是否需要压缩
        """
        total_tokens = session.metadata.get("total_tokens", 0)
        return total_tokens > self.max_tokens_per_layer


class MultiAgentSessionManager:
    """
    多层Agent Session管理器

    管理顶层Session以及各层级的子Session。
    """

    def __init__(self, base_session_manager: Any | None = None):
        """
        初始化 Session 管理器

        Args:
            base_session_manager: 基础 Session 管理器
        """
        session_manager_class = _get_session_manager()
        self.base_manager = base_session_manager or (session_manager_class() if session_manager_class else None)
        self.layer_sessions: dict[str, LayerSession] = {}
        self.context_manager = LayerContextManager()

    def create_top_session(self, user_input: str) -> LayerSession:
        """
        创建顶层Session

        Args:
            user_input: 用户输入

        Returns:
            LayerSession: 顶层Session
        """
        session = LayerSession(
            session_id=str(uuid.uuid4()),
            level=1,
        )
        session.add_message("user", user_input)
        self.layer_sessions[session.session_id] = session

        return session

    def create_layer2_session(
        self,
        parent_session_id: str,
        task_id: str,
    ) -> LayerSession:
        """
        创建 L2 Session

        Args:
            parent_session_id: 父Session ID
            task_id: 任务ID

        Returns:
            LayerSession: L2 Session
        """
        session = LayerSession(
            session_id=str(uuid.uuid4()),
            parent_session_id=parent_session_id,
            level=2,
            metadata={"task_id": task_id},
        )
        self.layer_sessions[session.session_id] = session

        return session

    def create_layer3_session(
        self,
        parent_session_id: str,
        subdomain_id: str,
    ) -> LayerSession:
        """
        创建 L3 Session

        Args:
            parent_session_id: 父Session ID
            subdomain_id: 子域ID

        Returns:
            LayerSession: L3 Session
        """
        session = LayerSession(
            session_id=str(uuid.uuid4()),
            parent_session_id=parent_session_id,
            level=3,
            subdomain_id=subdomain_id,
        )
        self.layer_sessions[session.session_id] = session

        return session

    def get_session(self, session_id: str) -> LayerSession | None:
        """
        获取 Session

        Args:
            session_id: Session ID

        Returns:
            Optional[LayerSession]: Session
        """
        return self.layer_sessions.get(session_id)

    def get_child_sessions(self, parent_session_id: str) -> list[LayerSession]:
        """
        获取子Session列表

        Args:
            parent_session_id: 父Session ID

        Returns:
            List[LayerSession]: 子Session列表
        """
        return [
            s for s in self.layer_sessions.values()
            if s.parent_session_id == parent_session_id
        ]

    def compact_session(self, session_id: str) -> bool:
        """
        压缩 Session

        Args:
            session_id: Session ID

        Returns:
            bool: 是否成功压缩
        """
        session = self.layer_sessions.get(session_id)
        if not session:
            return False

        # 生成摘要
        summary = self._generate_summary(session)

        # 清空消息并保留摘要
        session.messages = [{
            "role": "system",
            "content": f"[已压缩历史消息]\n{summary}",
            "timestamp": datetime.now().isoformat(),
        }]

        return True

    def _generate_summary(self, session: LayerSession) -> str:
        """
        生成 Session 摘要

        Args:
            session: Session

        Returns:
            str: 摘要
        """
        return f"""
历史消息摘要：
- 消息数量: {len(session.messages)}
- 层级: L{session.level}
- 子域: {session.subdomain_id or 'N/A'}
- 创建时间: {session.created_at.isoformat()}
"""
