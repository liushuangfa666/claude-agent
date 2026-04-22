"""
Snip-Compact - 裁剪压缩模块

目的: 删除冗余的工具输出内容（如超长的命令输出）
在 LLM 摘要生成之前执行，先裁剪超长内容以减少 token 消耗
"""
from __future__ import annotations

import logging

from .token_counter import count_tokens

logger = logging.getLogger(__name__)


class SnipCompactor:
    """裁剪压缩器 - 截断超长工具输出"""

    # 工具输出最大 tokens（保留前缀+后缀）
    MAX_TOOL_OUTPUT_TOKENS = 2000

    # 保留前缀比例
    HEAD_RATIO = 0.4

    # 保留后缀比例
    TAIL_RATIO = 0.4

    # 中间省略标记
    SNIP_MARKER = "\n... [内容已裁剪] ...\n"

    def __init__(self, max_tool_output_tokens: int = MAX_TOOL_OUTPUT_TOKENS):
        """
        初始化裁剪压缩器

        Args:
            max_tool_output_tokens: 单个工具输出的最大 token 数
        """
        self.max_tool_output_tokens = max_tool_output_tokens

    def compact(self, messages: list[dict]) -> list[dict]:
        """
        裁剪超长工具输出

        Args:
            messages: 消息列表

        Returns:
            裁剪后的消息列表
        """
        if not messages:
            return messages

        compacted = []
        snipped_count = 0

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "tool" and content:
                tokens = count_tokens(content)
                if tokens > self.max_tool_output_tokens:
                    # 需要裁剪
                    compacted_content = self._snip_content(content)
                    new_msg = dict(msg)
                    new_msg["content"] = compacted_content
                    compacted.append(new_msg)
                    snipped_count += 1
                else:
                    compacted.append(msg)
            else:
                compacted.append(msg)

        if snipped_count > 0:
            logger.info(f"Snip-Compact: 裁剪了 {snipped_count} 条超长工具输出")

        return compacted

    def _snip_content(self, content: str) -> str:
        """
        裁剪单个超长内容

        策略: 保留前 40% + 省略标记 + 后 40%
        """
        tokens = count_tokens(content)

        if tokens <= self.max_tool_output_tokens:
            return content

        # 计算目标 token 数（减去标记的 token）
        marker_tokens = count_tokens(self.SNIP_MARKER)
        target_tokens = self.max_tool_output_tokens - marker_tokens

        # 按比例分配给 head 和 tail
        head_tokens = int(target_tokens * self.HEAD_RATIO)
        tail_tokens = int(target_tokens * self.TAIL_RATIO)

        # 从内容中提取 head 和 tail
        head = self._extract_n_tokens(content, head_tokens, from_end=False)
        tail = self._extract_n_tokens(content, tail_tokens, from_end=True)

        return head + self.SNIP_MARKER + tail

    def _extract_n_tokens(self, text: str, target_tokens: int, from_end: bool = False) -> str:
        """
        从文本中提取约 n 个 token 的内容

        Args:
            text: 源文本
            target_tokens: 目标 token 数
            from_end: True=从末尾提取（tail），False=从开头提取（head）
        """
        if target_tokens <= 0:
            return ""

        # 粗略估算: 4 字符 ≈ 1 token
        char_count = target_tokens * 4

        if from_end:
            # 从末尾提取
            if len(text) <= char_count:
                return text
            return text[-char_count:]
        else:
            # 从开头提取
            if len(text) <= char_count:
                return text
            return text[:char_count]

    def compact_api_messages(self, messages: list[dict]) -> list[dict]:
        """
        裁剪 API 格式消息中的超长工具输出

        API 格式中 tool 消息有 tool_call_id 字段
        """
        if not messages:
            return messages

        compacted = []
        snipped_count = 0

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "tool" and content:
                tokens = count_tokens(content)
                if tokens > self.max_tool_output_tokens:
                    compacted_content = self._snip_content(content)
                    new_msg = dict(msg)
                    new_msg["content"] = compacted_content
                    compacted.append(new_msg)
                    snipped_count += 1
                else:
                    compacted.append(msg)
            else:
                compacted.append(msg)

        if snipped_count > 0:
            logger.debug(f"Snip-Compact: 裁剪了 {snipped_count} 条工具输出")

        return compacted


# 便捷函数
def snip_compact(messages: list[dict]) -> list[dict]:
    """对消息列表执行裁剪压缩"""
    compactor = SnipCompactor()
    return compactor.compact(messages)
