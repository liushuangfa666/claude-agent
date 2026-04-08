"""
Token Budget - 动态计算每轮可用输出 token，指导压缩决策

与 Token Counter 的区别:
- Token Counter: 静态计算 - "这段文本有多少 token"
- Token Budget: 动态规划 - "根据剩余 context，本轮最多能输出多少 token"
"""
from __future__ import annotations


def calculate_token_budget(
    max_context_tokens: int,
    current_tokens: int,
    reserved_buffer: int = 5000,
) -> int:
    """
    计算本轮可用输出 token 数

    Args:
        max_context_tokens: 最大上下文 token 数 (模型限制)
        current_tokens: 当前已用 token 数
        reserved_buffer: 预留 buffer (防止超出)

    Returns:
        本轮可用输出 token 数
    """
    available = max_context_tokens - current_tokens - reserved_buffer
    return max(0, available)


def calculate_budget_info(
    max_context_tokens: int,
    current_tokens: int,
    reserved_buffer: int = 5000,
) -> dict:
    """
    计算详细的 budget 信息

    Args:
        max_context_tokens: 最大上下文 token 数
        current_tokens: 当前已用 token 数
        reserved_buffer: 预留 buffer

    Returns:
        包含详细信息的字典:
        - available: 可用 token 数
        - usage_ratio: 使用比例 (0-1)
        - is_critical: 是否接近上限
        - warning_level: 警告级别 (safe/warning/critical)
    """
    available = calculate_token_budget(max_context_tokens, current_tokens, reserved_buffer)
    usage_ratio = current_tokens / max_context_tokens if max_context_tokens > 0 else 0

    if usage_ratio >= 0.9:
        warning_level = "critical"
    elif usage_ratio >= 0.75:
        warning_level = "warning"
    else:
        warning_level = "safe"

    is_critical = usage_ratio >= 0.85

    return {
        "available": available,
        "usage_ratio": usage_ratio,
        "is_critical": is_critical,
        "warning_level": warning_level,
        "max_context": max_context_tokens,
        "current": current_tokens,
        "reserved": reserved_buffer,
    }


def should_trigger_compaction(
    budget_info: dict,
    warning_threshold: float = 0.75,
    critical_threshold: float = 0.85,
) -> tuple[bool, str]:
    """
    根据 budget 信息判断是否应该触发压缩

    Args:
        budget_info: calculate_budget_info 返回的信息
        warning_threshold: 警告阈值 (usage_ratio)
        critical_threshold: 严重阈值 (usage_ratio)

    Returns:
        (should_compact, reason) 元组
    """
    usage_ratio = budget_info.get("usage_ratio", 0)

    if usage_ratio >= critical_threshold:
        return True, "context 使用率超过 85%，必须压缩"
    elif usage_ratio >= warning_threshold:
        return True, f"context 使用率 {usage_ratio:.1%}，建议压缩"
    else:
        return False, ""


def estimate_response_tokens(
    messages: list[dict],
    max_context_tokens: int = 180000,
    reserved_buffer: int = 5000,
) -> int:
    """
    根据消息列表估算可用响应 token 数

    Args:
        messages: 消息列表
        max_context_tokens: 最大上下文 token 数
        reserved_buffer: 预留 buffer

    Returns:
        可用于 LLM 响应的 token 数
    """
    from .token_counter import count_messages_tokens

    current_tokens = count_messages_tokens(messages)
    return calculate_token_budget(max_context_tokens, current_tokens, reserved_buffer)
