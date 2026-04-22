"""
Token Counter - 精确token计数
"""
from __future__ import annotations

try:
    import tiktoken
    _HAS_TIKTOKEN = True
except ImportError:
    _HAS_TIKTOKEN = False


def count_tokens(text: str) -> int:
    """计算文本的token数量"""
    if not text:
        return 0

    if _HAS_TIKTOKEN:
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            pass

    # Fallback: rough estimation (1 token ≈ 4 characters)
    return len(text) // 4


def count_messages_tokens(messages: list[dict]) -> int:
    """
    计算消息列表的总token数
    
    按 Anthropic API 规则计算:
    - 每条消息有额外 overhead
    - tool_calls 和 tool_use 块有额外开销
    """
    total = 0

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        # 基本 overhead
        if role == "system":
            total += 12  # system overhead
        elif role == "user":
            total += 6   # user overhead
        elif role == "assistant":
            total += 6   # assistant overhead
        elif role == "tool":
            total += 5   # tool overhead

        # 内容
        if content:
            total += count_tokens(content)

        # tool_calls
        tool_calls = msg.get("tool_calls", [])
        for tc in tool_calls:
            total += count_tokens(str(tc))

        # tool_call_id (tool 消息)
        if msg.get("tool_call_id"):
            total += 3

    # 对话模型有额外的 overhead
    total += 10

    return total


def estimate_available_tokens(model: str = "cl100k_base") -> int:
    """估算可用token数"""
    # claude-3 上下文 200k
    # 其他模型通常 128k 或更少
    MAX_CONTEXT = 200000

    # 预留 buffer
    RESERVED = 5000

    return MAX_CONTEXT - RESERVED
