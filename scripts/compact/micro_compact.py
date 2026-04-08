"""
Micro-Compact - 微压缩模块

目的: 利用 API 原生特性清除旧工具结果，在不依赖 LLM 摘要的情况下减少 token 消耗。
通过识别关键上下文（用户消息）来保留有意义的内容。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class MicroCompactor:
    """
    微压缩器 - 清除旧工具结果，保留关键上下文

    策略：
    1. 找到最后一个有意义的用户消息索引
    2. 保留该用户消息及其之后的所有内容
    3. 删除该用户消息之前的工具结果
    """

    # 最小保留的 token 数
    MIN_TOKENS_TO_PRESERVE = 500

    def __init__(self, min_tokens_to_preserve: int = MIN_TOKENS_TO_PRESERVE):
        """
        初始化微压缩器

        Args:
            min_tokens_to_preserve: 最小保留 token 数
        """
        self.min_tokens_to_preserve = min_tokens_to_preserve

    def find_last_useful_message(self, messages: list[dict]) -> int:
        """
        找到最后一个有意义的用户消息索引

        有意义的用户消息指：
        1. 包含实际用户请求的文本
        2. 不是系统生成的消息

        Args:
            messages: 消息列表

        Returns:
            最后一个有意义的用户消息的索引
        """
        if not messages:
            return -1

        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user" and content and len(content.strip()) > 10:
                return i

        return -1

    def compact(self, messages: list[dict]) -> list[dict]:
        """
        清除旧工具结果，保留关键上下文

        策略：
        1. 找到最后一个有意义的用户消息
        2. 保留该消息及其之后的所有消息
        3. 如果工具结果在目标保留范围之外，也一并清除

        Args:
            messages: 消息列表

        Returns:
            压缩后的消息列表
        """
        if not messages:
            return messages

        # 找到最后一个有意义的用户消息
        last_useful_idx = self.find_last_useful_message(messages)

        if last_useful_idx < 0:
            # 没有找到有意义的用户消息，保留所有
            logger.debug("Micro-Compact: 未找到有意义的用户消息")
            return messages

        # 如果最后一个有用消息已经接近末尾，不需要压缩
        if last_useful_idx >= len(messages) - 3:
            logger.debug(f"Micro-Compact: 最后有用消息在位置 {last_useful_idx}，接近末尾，无需压缩")
            return messages

        # 保留从最后一个有用用户消息开始的所有内容
        compacted = messages[last_useful_idx:]

        removed_count = len(messages) - len(compacted)
        if removed_count > 0:
            logger.info(f"Micro-Compact: 移除了 {removed_count} 条早期消息")

        return compacted

    def compact_with_tool_pruning(self, messages: list[dict]) -> list[dict]:
        """
        压缩并修剪工具结果

        策略：
        1. 保留最后一个用户消息及其之后的内容
        2. 对工具结果进行简化（缩短长输出）

        Args:
            messages: 消息列表

        Returns:
            压缩后的消息列表
        """
        if not messages:
            return messages

        # 先执行基本压缩
        compacted = self.compact(messages)

        # 简化过长的工具结果
        from .token_counter import count_tokens

        MAX_TOOL_CONTENT = 500

        simplified = []
        for msg in compacted:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "tool" and content:
                tokens = count_tokens(content)
                if tokens > MAX_TOOL_CONTENT:
                    # 截断工具结果
                    simplified_content = content[:MAX_TOOL_CONTENT * 4] + "\n... [已简化]"
                    simplified.append({**msg, "content": simplified_content})
                else:
                    simplified.append(msg)
            else:
                simplified.append(msg)

        return simplified


# 便捷函数
def micro_compact(messages: list[dict]) -> list[dict]:
    """对消息列表执行微压缩"""
    compactor = MicroCompactor()
    return compactor.compact(messages)
