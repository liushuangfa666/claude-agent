"""
Reactive Compact - 响应式压缩
"""
from __future__ import annotations

import logging

from .compact_manager import CompactConfig, CompactionResult, CompactManager

logger = logging.getLogger(__name__)


def is_prompt_too_long_error(error: Exception) -> bool:
    """检查错误是否是 prompt-too-long 类型"""
    error_str = str(error).lower()

    patterns = [
        "prompt too long",
        "prompt-too-long",
        "context_length_exceeded",
        "maximum context length",
        "too many tokens",
        "token limit",
        "input too long",
        "exceeds maximum",
    ]

    return any(p in error_str for p in patterns)


async def try_reactive_compact(
    messages: list[dict],
    error: Exception,
    config: CompactConfig,
    compact_manager: CompactManager | None = None,
) -> CompactionResult:
    """
    响应式压缩
    
    当 API 返回 prompt-too-long 错误时尝试压缩。
    """
    if not is_prompt_too_long_error(error):
        return CompactionResult(
            success=False,
            error=f"Not a prompt-too-long error: {error}"
        )

    logger.warning(f"Reactive compact triggered by: {error}")

    manager = compact_manager or CompactManager(config)

    # 尝试压缩
    result = await manager.compact_conversation(messages)

    if result.success:
        manager.reset_failures()
        logger.info(
            f"Reactive compact successful: {result.original_tokens} -> {result.compacted_tokens} tokens"
        )
    else:
        manager.increment_failure()
        logger.error(f"Reactive compact failed: {result.error}")

    return result


async def aggressive_compact(
    messages: list[dict],
    config: CompactConfig,
) -> CompactionResult:
    """
    激进压缩
    
    保留更少的历史，生成更简洁的摘要。
    """
    # 临时修改配置
    original_preserve = config.preserve_recent_turns
    config.preserve_recent_turns = 2

    manager = CompactManager(config)
    result = await manager.compact_conversation(messages)

    # 恢复配置
    config.preserve_recent_turns = original_preserve

    return result
