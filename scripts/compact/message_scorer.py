"""
Message Importance Scorer - 消息重要性评分

根据消息类型和内容智能评分，决定压缩时保留哪些消息
"""
from __future__ import annotations


def score_message_importance(msg: dict) -> float:
    """
    根据消息类型和内容评分 (0.0 - 1.0)

    评分规则:
    - user message: 高优先级 (0.8-1.0)
    - assistant 包含决策/代码: 高优先级 (0.7-1.0)
    - tool result: 低优先级 (0.1-0.4)
    - 重复的工具结果: 更低 (0.1)

    Args:
        msg: 消息字典，包含 role, content 等字段

    Returns:
        重要性分数 (0.0 - 1.0)
    """
    role = msg.get("role", "")
    content = msg.get("content", "") or ""

    if role == "system":
        # System 消息最高优先级
        return 1.0

    elif role == "user":
        # 用户消息通常是任务定义或指令，高优先级
        if len(content) > 500:
            # 长消息可能包含详细需求
            return 0.9
        return 0.8

    elif role == "assistant":
        # Assistant 消息评分取决于内容
        score = 0.5

        # 包含代码的消息更重要
        if any(marker in content for marker in ["```", "def ", "class ", "import ", "function "]):
            score = max(score, 0.8)

        # 包含决策/结论的消息重要
        if any(marker in content for marker in ["决定", "选择", "结论", "因此", "所以", "结论是"]):
            score = max(score, 0.85)

        # 工具调用结果说明 assistant 在工作
        if msg.get("tool_calls"):
            score = max(score, 0.7)

        # 长文本回复通常是详细解释
        if len(content) > 1000:
            score = max(score, 0.75)

        return score

    elif role == "tool":
        # Tool 消息通常是执行结果，可压缩
        score = 0.3

        # 检查是否是错误结果（更重要）
        if any(err in content.lower() for err in ["error", "错误", "failed", "失败", "exception"]):
            score = 0.5

        # 检查是否包含重要输出（如创建的文件）
        if any(marker in content for marker in ["created", "created file", "written", "已创建", "已写入"]):
            score = 0.6

        # 简短的确认消息不太重要
        if len(content) < 50:
            score = 0.2

        return score

    return 0.5  # 默认分数


def get_important_messages(
    messages: list[dict],
    min_score: float = 0.6,
    preserve_system: bool = True,
) -> list[tuple[int, dict, float]]:
    """
    获取重要消息及其分数

    Args:
        messages: 消息列表
        min_score: 最低分数阈值
        preserve_system: 是否始终保留 system 消息

    Returns:
        [(index, message, score), ...] 重要消息列表
    """
    important = []

    for i, msg in enumerate(messages):
        # System 消息始终保留
        if preserve_system and msg.get("role") == "system":
            important.append((i, msg, 1.0))
            continue

        score = score_message_importance(msg)
        if score >= min_score:
            important.append((i, msg, score))

    return important


def get_compactable_messages(
    messages: list[dict],
    min_score: float = 0.5,
    preserve_recent: int = 5,
) -> tuple[list[dict], list[dict]]:
    """
    分离可压缩和应保留的消息

    Args:
        messages: 消息列表
        min_score: 最低分数阈值，低于此分数可压缩
        preserve_recent: 保留最近 N 条消息对

    Returns:
        (compactable, preserved) 元组
    """
    if not messages:
        return [], []

    # 分离 system 消息
    system_messages = [m for m in messages if m.get("role") == "system"]
    non_system = [m for m in messages if m.get("role") != "system"]

    # 保留最近的对话对
    recent = non_system[-preserve_recent:] if len(non_system) > preserve_recent else non_system
    middle = non_system[:-preserve_recent] if len(non_system) > preserve_recent else []

    # 从中间消息中分离可压缩的
    compactable = []
    preserved = list(recent)  # 最近的始终保留

    for msg in middle:
        score = score_message_importance(msg)
        if score < min_score:
            compactable.append(msg)
        else:
            preserved.append(msg)

    return compactable, system_messages + preserved


def build_importance_index(messages: list[dict]) -> dict[int, float]:
    """
    构建消息重要性索引

    Args:
        messages: 消息列表

    Returns:
        {index: score} 字典
    """
    return {i: score_message_importance(msg) for i, msg in enumerate(messages)}


def find_key_decisions(messages: list[dict]) -> list[dict]:
    """
    查找包含关键决策的消息

    Args:
        messages: 消息列表

    Returns:
        包含关键决策的消息列表
    """
    decision_markers = [
        "决定", "选择", "结论", "因此", "所以",
        "decided", "conclusion", "therefore", "choosing",
        "implementing", "will use", "going to",
    ]

    key_messages = []
    for msg in messages:
        content = msg.get("content", "") or ""
        role = msg.get("role", "")

        # Assistant 或 user 的长回复中提到决策
        if role in ("assistant", "user") and len(content) > 100:
            for marker in decision_markers:
                if marker.lower() in content.lower():
                    key_messages.append(msg)
                    break

    return key_messages
