"""
Auto Compact - 自动压缩逻辑
"""
from __future__ import annotations

import logging

from .compact_manager import CompactConfig, CompactionResult, CompactManager
from .token_counter import count_messages_tokens

logger = logging.getLogger(__name__)


AUTOCOMPACT_BUFFER_TOKENS = 13_000
WARNING_THRESHOLD_BUFFER_TOKENS = 20_000
MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3


async def try_auto_compact(
    messages: list[dict],
    config: CompactConfig,
    compact_manager: CompactManager | None = None,
) -> CompactionResult:
    """
    尝试自动压缩
    
    当上下文接近限制时自动压缩历史消息。
    """
    if not messages:
        return CompactionResult(success=True)

    manager = compact_manager or CompactManager(config)
    tokens = count_messages_tokens(messages)

    if not manager.should_auto_compact(tokens):
        return CompactionResult(success=True, original_tokens=tokens)

    logger.info(f"Auto-compacting: {tokens} tokens")

    result = await manager.compact_conversation(messages)

    if result.success:
        logger.info(
            f"Compact successful: {result.original_tokens} -> {result.compacted_tokens} tokens, "
            f"removed {result.messages_removed} messages"
        )
    else:
        logger.warning(f"Compact failed: {result.error}")
        manager.increment_failure()

    return result


async def check_and_compact(
    messages: list[dict],
    config: CompactConfig,
) -> tuple[bool, CompactionResult]:
    """
    检查并压缩
    
    Returns:
        (是否执行了压缩, 压缩结果)
    """
    manager = CompactManager(config)
    tokens = count_messages_tokens(messages)

    if not manager.should_auto_compact(tokens):
        return False, CompactionResult(success=True, original_tokens=tokens)

    result = await manager.compact_conversation(messages)
    return True, result
