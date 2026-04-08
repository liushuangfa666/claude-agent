"""
传输层基类定义

提供 Transport 抽象接口和 TransportMessage 数据结构。
参考 Claude Code 的 StructuredIO 设计。
"""
from __future__ import annotations

import uuid
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TransportMessage:
    """
    传输消息封装

    用于在不同传输层之间传递消息。
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = "message"
    data: dict[str, Any] = field(default_factory=dict)
    sequence: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        result = {
            "id": self.id,
            "type": self.type,
            **self.data,
        }
        if self.sequence is not None:
            result["sequence"] = self.sequence
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TransportMessage:
        """从字典创建"""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            type=data.get("type", "message"),
            data=data,
            sequence=data.get("sequence"),
        )


class Transport(ABC):
    """
    传输层抽象接口

    定义所有传输层必须实现的方法。
    支持回调机制用于连接状态变化通知。
    """

    def __init__(self) -> None:
        self._on_connect: Callable[[], None] | None = None
        self._on_disconnect: Callable[[], None] | None = None
        self._on_error: Callable[[Exception], None] | None = None

    @abstractmethod
    async def connect(self) -> None:
        """建立连接"""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接"""
        pass

    @abstractmethod
    async def write(self, message: TransportMessage) -> None:
        """发送消息"""
        pass

    @abstractmethod
    def read(self) -> AsyncGenerator[TransportMessage, None]:
        """读取消息流"""
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """连接状态"""
        pass

    def set_on_connect(self, callback: Callable[[], None]) -> None:
        """设置连接成功回调"""
        self._on_connect = callback

    def set_on_disconnect(self, callback: Callable[[], None]) -> None:
        """设置断开连接回调"""
        self._on_disconnect = callback

    def set_on_error(self, callback: Callable[[Exception], None]) -> None:
        """设置错误回调"""
        self._on_error = callback

    def _trigger_connect(self) -> None:
        """触发连接回调"""
        if self._on_connect:
            try:
                self._on_connect()
            except Exception as e:
                logger.error(f"Error in connect callback: {e}")

    def _trigger_disconnect(self) -> None:
        """触发断开回调"""
        if self._on_disconnect:
            try:
                self._on_disconnect()
            except Exception as e:
                logger.error(f"Error in disconnect callback: {e}")

    def _trigger_error(self, error: Exception) -> None:
        """触发错误回调"""
        if self._on_error:
            try:
                self._on_error(error)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")
