"""
Context Collapse - 上下文折叠模块

目的: 细粒度折叠消息，不依赖 LLM 摘要
通过将一组消息替换为"折叠标记"来减少上下文长度，
同时保留折叠内容的摘要以便后续展开。
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CollapseRecord:
    """折叠记录"""
    collapse_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    message_ids: list[str] = field(default_factory=list)
    summary: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)


class CollapseStore:
    """
    折叠存储 - 管理消息折叠状态

    提供存根实现，支持：
    1. stage: 准备折叠（创建折叠记录）
    2. commit: 提交折叠（实际替换消息）
    3. expand: 展开折叠（恢复原始消息）
    """

    def __init__(self):
        self._staged: dict[str, CollapseRecord] = {}  # 待提交的折叠
        self._committed: dict[str, CollapseRecord] = {}  # 已提交的折叠
        self._collapsed_messages: dict[str, list[dict]] = {}  # 折叠后的消息内容

    def stage(self, message_ids: list[str], summary: str = "", metadata: dict | None = None) -> str:
        """
        准备折叠

        Args:
            message_ids: 要折叠的消息 ID 列表
            summary: 折叠摘要（可选）
            metadata: 额外元数据（可选）

        Returns:
            collapse_id: 折叠 ID
        """
        collapse_id = str(uuid.uuid4())
        record = CollapseRecord(
            collapse_id=collapse_id,
            message_ids=message_ids,
            summary=summary,
            metadata=metadata or {},
        )
        self._staged[collapse_id] = record
        logger.debug(f"Staged collapse: {collapse_id} with {len(message_ids)} messages")
        return collapse_id

    def commit(self, collapse_id: str, collapsed_content: list[dict]) -> bool:
        """
        提交折叠

        Args:
            collapse_id: 折叠 ID
            collapsed_content: 折叠后的消息内容

        Returns:
            是否提交成功
        """
        if collapse_id not in self._staged:
            logger.warning(f"Collapse {collapse_id} not staged")
            return False

        record = self._staged.pop(collapse_id)
        self._committed[collapse_id] = record
        self._collapsed_messages[collapse_id] = collapsed_content
        logger.info(f"Committed collapse: {collapse_id}")
        return True

    def expand(self, collapse_id: str) -> list[dict] | None:
        """
        展开折叠

        Args:
            collapse_id: 折叠 ID

        Returns:
            原始消息内容，或 None 如果折叠不存在
        """
        if collapse_id not in self._committed:
            logger.warning(f"Collapse {collapse_id} not found")
            return None

        return self._collapsed_messages.get(collapse_id)

    def get_record(self, collapse_id: str) -> CollapseRecord | None:
        """
        获取折叠记录

        Args:
            collapse_id: 折叠 ID

        Returns:
            折叠记录或 None
        """
        return self._committed.get(collapse_id)

    def cancel(self, collapse_id: str) -> bool:
        """
        取消待提交的折叠

        Args:
            collapse_id: 折叠 ID

        Returns:
            是否取消成功
        """
        if collapse_id in self._staged:
            del self._staged[collapse_id]
            return True
        return False

    def list_committed(self) -> list[CollapseRecord]:
        """列出所有已提交的折叠"""
        return list(self._committed.values())


class ContextCollapser:
    """
    上下文折叠器

    使用折叠存储来管理消息折叠，
    提供高级 API 来执行折叠操作。
    """

    def __init__(self, store: CollapseStore | None = None):
        self._store = store or CollapseStore()

    @property
    def store(self) -> CollapseStore:
        return self._store

    def prepare_collapse(
        self,
        messages: list[dict],
        start_idx: int,
        end_idx: int,
        summary: str = "",
    ) -> str:
        """
        准备折叠一段消息

        Args:
            messages: 消息列表
            start_idx: 起始索引（包含）
            end_idx: 结束索引（包含）
            summary: 折叠摘要

        Returns:
            collapse_id: 折叠 ID
        """
        message_ids = [messages[i].get("id", f"msg_{i}") for i in range(start_idx, end_idx + 1)]
        return self._store.stage(message_ids, summary)

    def apply_collapse(
        self,
        messages: list[dict],
        collapse_id: str,
        start_idx: int,
        end_idx: int,
    ) -> list[dict]:
        """
        应用折叠到消息列表

        Args:
            messages: 原始消息列表
            collapse_id: 折叠 ID
            start_idx: 起始索引（包含）
            end_idx: 结束索引（包含）

        Returns:
            折叠后的消息列表
        """
        # 获取被折叠的消息内容
        collapsed_content = messages[start_idx:end_idx + 1]

        # 提交折叠
        self._store.commit(collapse_id, collapsed_content)

        # 创建折叠标记消息
        collapse_marker = {
            "role": "system",
            "content": f"[折叠的消息，共 {end_idx - start_idx + 1} 条，ID: {collapse_id}]",
            "collapse_id": collapse_id,
        }

        # 重建消息列表
        result = messages[:start_idx] + [collapse_marker] + messages[end_idx + 1:]
        return result

    def expand_collapse(
        self,
        messages: list[dict],
        collapse_id: str,
        marker_idx: int,
    ) -> list[dict]:
        """
        展开折叠

        Args:
            messages: 包含折叠标记的消息列表
            collapse_id: 折叠 ID
            marker_idx: 折叠标记的索引

        Returns:
            展开后的消息列表
        """
        original = self._store.expand(collapse_id)
        if original is None:
            logger.warning(f"Cannot expand {collapse_id}")
            return messages

        # 重建消息列表
        result = messages[:marker_idx] + original + messages[marker_idx + 1:]
        return result

    def auto_collapse(
        self,
        messages: list[dict],
        max_messages: int = 50,
        summary_generator: callable | None = None,
    ) -> list[dict]:
        """
        自动折叠早期消息

        Args:
            messages: 消息列表
            max_messages: 保留的最大消息数
            summary_generator: 可选的摘要生成函数

        Returns:
            处理后的消息列表
        """
        if len(messages) <= max_messages:
            return messages

        # 计算需要折叠的消息数量
        to_collapse = len(messages) - max_messages
        start_idx = 1  # 跳过 system 消息

        # 生成摘要
        summary = ""
        if summary_generator:
            try:
                messages_to_summarize = messages[start_idx:start_idx + to_collapse]
                summary = summary_generator(messages_to_summarize)
            except Exception as e:
                logger.error(f"Summary generation failed: {e}")

        # 准备折叠
        collapse_id = self.prepare_collapse(
            messages, start_idx, start_idx + to_collapse - 1, summary
        )

        # 应用折叠
        return self.apply_collapse(messages, collapse_id, start_idx, start_idx + to_collapse - 1)


# 便捷函数
def create_collapser() -> ContextCollapser:
    """创建上下文折叠器"""
    return ContextCollapser()
