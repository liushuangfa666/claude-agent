"""
Session - 会话和会话管理器
"""
from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@dataclass
class Message:
    """消息记录"""
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)
    tokens: int = 0


@dataclass
class UsageStats:
    """使用统计"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    request_count: int = 0


class Session:
    """
    聊天会话

    Attributes:
        id: 会话唯一 ID
        messages: 消息历史
        created_at: 创建时间戳
        last_active: 最后活跃时间戳
        usage: Token 使用统计
    """

    def __init__(self, session_id: str | None = None) -> None:
        """
        初始化会话

        Args:
            session_id: 指定会话 ID，为空则自动生成
        """
        self.id: str = session_id or str(uuid.uuid4())
        self.messages: deque[Message] = deque(maxlen=1000)
        self.created_at: float = time.time()
        self.last_active: float = time.time()
        self.usage: UsageStats = UsageStats()

    async def process_message(self, message: str) -> str:
        """
        处理消息（非流式）

        Args:
            message: 用户输入消息

        Returns:
            Assistant 回复文本
        """
        self.messages.append(Message(role="user", content=message))
        self.last_active = time.time()

        # TODO: 调用 Agent 处理
        response = f"Echo: {message}"
        self.messages.append(Message(role="assistant", content=response))

        # 更新统计
        self.usage.input_tokens += len(message) // 4
        self.usage.output_tokens += len(response) // 4
        self.usage.total_tokens = (
            self.usage.input_tokens + self.usage.output_tokens
        )
        self.usage.request_count += 1

        return response

    async def stream_message(
        self, message: str
    ) -> "AsyncGenerator[dict[str, Any], None]":
        """
        流式处理消息

        Args:
            message: 用户输入消息

        Yields:
            事件字典，包含 type, content 等字段
        """
        self.messages.append(Message(role="user", content=message))
        self.last_active = time.time()

        # TODO: 调用 Agent 流式处理
        yield {"type": "thinking", "content": "Processing..."}
        yield {"type": "text", "content": f"Echo: {message}"}
        yield {"type": "done", "content": ""}

        # 更新统计
        self.usage.input_tokens += len(message) // 4
        self.usage.request_count += 1

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        获取对话历史

        Args:
            limit: 返回消息数量上限，默认 50

        Returns:
            消息列表
        """
        return [
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp,
            }
            for m in list(self.messages)[-limit:]
        ]

    def get_usage(self) -> dict[str, Any]:
        """
        获取使用统计

        Returns:
            统计信息字典
        """
        return {
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "total_tokens": self.usage.total_tokens,
            "request_count": self.usage.request_count,
        }

    def to_dict(self) -> dict[str, Any]:
        """
        转换为字典

        Returns:
            会话信息字典
        """
        return {
            "id": self.id,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "message_count": len(self.messages),
        }


class SessionManager:
    """
    会话管理器

    管理所有活跃会话，提供创建/获取/删除/列表等功能
    """

    def __init__(self) -> None:
        """初始化会话管理器"""
        self._sessions: dict[str, Session] = {}
        self._global_usage: UsageStats = UsageStats()

    def create(self) -> Session:
        """
        创建新会话

        Returns:
            新创建的 Session 实例
        """
        session = Session()
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> "Session | None":
        """
        获取指定会话

        Args:
            session_id: 会话 ID

        Returns:
            Session 实例或 None
        """
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str) -> Session:
        """
        获取或创建会话

        Args:
            session_id: 会话 ID，为空则创建新会话

        Returns:
            Session 实例
        """
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        return self.create()

    def delete(self, session_id: str) -> bool:
        """
        删除会话

        Args:
            session_id: 会话 ID

        Returns:
            是否成功删除
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def list(self) -> list[dict[str, Any]]:
        """
        列出所有会话

        Returns:
            会话信息列表
        """
        return [s.to_dict() for s in self._sessions.values()]

    def count(self) -> int:
        """
        获取会话数量

        Returns:
            会话数量
        """
        return len(self._sessions)

    def get_stats(self) -> dict[str, Any]:
        """
        获取全局统计

        Returns:
            统计信息字典
        """
        return {
            "session_count": len(self._sessions),
            "total_usage": {
                "input_tokens": self._global_usage.input_tokens,
                "output_tokens": self._global_usage.output_tokens,
                "total_tokens": self._global_usage.total_tokens,
                "request_count": self._global_usage.request_count,
            },
        }

    def get_usage(self) -> dict[str, Any]:
        """
        获取全局使用统计

        Returns:
            使用统计字典
        """
        return self.get_stats()["total_usage"]
