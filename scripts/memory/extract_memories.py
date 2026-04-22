"""
自动记忆提取服务

在对话结束后分析对话历史，提取值得持久化的记忆。
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent import Message

from .extract_prompts import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_PROMPT_TEMPLATE
from .memory_store import MemoryStore
from .types import MemoryType

logger = logging.getLogger(__name__)

# 全局状态
_last_extraction_turn = 0
_explicit_save_detected = False


@dataclass
class ExtractionResult:
    """提取结果"""
    memories: list[dict]
    success: bool
    error: str | None = None
    memories_saved: int = 0


def detect_explicit_save(message: str) -> bool:
    """检测用户是否显式要求保存记忆"""
    explicit_patterns = [
        "记住",
        "save this",
        "remember",
        "keep in mind",
        "don't forget",
        "memo",
        "save to memory",
    ]
    message_lower = message.lower()
    return any(pattern in message_lower for pattern in explicit_patterns)


def should_skip_extraction(turn_count: int) -> bool:
    """
    判断是否应该跳过自动提取

    规则：
    - 首轮不提取（需要更多上下文）
    - 如果检测到显式保存，跳过本次自动提取
    """
    global _last_extraction_turn, _explicit_save_detected

    # 首轮不提取
    if turn_count <= 1:
        return True

    # 如果刚检测到显式保存，跳过自动提取
    if _explicit_save_detected:
        _explicit_save_detected = False
        return True

    return False


def mark_explicit_save() -> None:
    """标记检测到显式保存，下次自动提取跳过"""
    global _explicit_save_detected
    _explicit_save_detected = True


def reset_extraction_state() -> None:
    """重置提取状态（新对话开始时调用）"""
    global _last_extraction_turn, _explicit_save_detected
    _last_extraction_turn = 0
    _explicit_save_detected = False


async def extract_memories_from_messages(
    messages: list["Message"],
    store: MemoryStore | None = None,
) -> ExtractionResult:
    """
    从消息历史中提取记忆

    Args:
        messages: 对话消息列表
        store: MemoryStore 实例

    Returns:
        ExtractionResult: 提取结果
    """
    if store is None:
        store = MemoryStore()

    # 构建消息文本
    messages_text = _format_messages_for_extraction(messages)

    if not messages_text.strip():
        return ExtractionResult(memories=[], success=True, memories_saved=0)

    # 调用 LLM 提取
    try:
        extracted = await _call_llm_for_extraction(messages_text)

        if not extracted:
            return ExtractionResult(memories=[], success=True, memories_saved=0)

        # 保存提取的记忆
        saved_count = 0
        for mem_data in extracted:
            try:
                memory_type = MemoryType(mem_data.get("type", "project"))
                store.write_memory(
                    content=mem_data.get("content", ""),
                    memory_type=memory_type,
                    name=mem_data.get("name", ""),
                    description=mem_data.get("description", ""),
                    tags=mem_data.get("tags", []),
                )
                saved_count += 1
            except Exception as e:
                logger.error(f"Failed to save extracted memory: {e}")

        return ExtractionResult(
            memories=extracted,
            success=True,
            memories_saved=saved_count,
        )

    except Exception as e:
        logger.error(f"Memory extraction failed: {e}")
        return ExtractionResult(memories=[], success=False, error=str(e))


def _format_messages_for_extraction(messages: list["Message"]) -> str:
    """将消息格式化为提取用的文本"""
    lines = []
    for msg in messages:
        role = msg.role
        content = msg.content

        # 跳过系统消息和过长的内容
        if role == "system":
            continue
        if len(content) > 2000:
            content = content[:2000] + "..."

        lines.append(f"**{role.upper()}**: {content}")

    return "\n\n".join(lines)


async def _call_llm_for_extraction(messages_text: str) -> list[dict] | None:
    """
    调用 LLM 进行记忆提取

    Returns:
        提取的记忆列表，或 None 如果失败
    """
    try:
        from ..agent import call_llm

        user_prompt = EXTRACTION_USER_PROMPT_TEMPLATE.format(messages=messages_text)

        response = call_llm(
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            model="MiniMax-M2.7",
            api_url="https://api.minimaxi.com/anthropic/v1/messages",
            temperature=0.3,
            timeout=60,
        )

        # 解析响应
        content = None
        if isinstance(response, dict):
            content = response.get("content", "")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        content = block.get("text", "")
                        break
            elif isinstance(content, str):
                pass
            else:
                # MiniMax 格式
                msg_content = response.get("message", {}).get("content", "")
                if isinstance(msg_content, list):
                    for block in msg_content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            content = block.get("text", "")
                            break
                elif isinstance(msg_content, str):
                    content = msg_content

        if not content:
            return None

        # 尝试解析 JSON
        return _parse_extraction_response(content)

    except Exception as e:
        logger.error(f"LLM extraction call failed: {e}")
        return None


def _parse_extraction_response(content: str) -> list[dict] | None:
    """解析 LLM 响应，提取 JSON 数组"""
    # 尝试直接解析
    content = content.strip()

    # 移除可能的 markdown 代码块
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    # 尝试解析为 JSON
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # 尝试在内容中查找 JSON 数组
    import re
    json_array_pattern = r'\[[\s\S]*\]'
    matches = re.findall(json_array_pattern, content)
    for match in matches:
        try:
            data = json.loads(match)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            continue

    return None


class MemoryExtractor:
    """记忆提取器类（面向对象接口）"""

    def __init__(self, store: MemoryStore | None = None):
        self._store = store or MemoryStore()

    async def extract(
        self,
        messages: list["Message"],
        force: bool = False,
    ) -> ExtractionResult:
        """
        从消息中提取记忆

        Args:
            messages: 对话消息列表
            force: 是否强制提取（忽略自动提取规则）

        Returns:
            ExtractionResult
        """
        # 检查是否应该跳过
        if not force and should_skip_extraction(len(messages)):
            return ExtractionResult(
                memories=[],
                success=True,
                error="skipped (first turn or explicit save detected)",
            )

        return await extract_memories_from_messages(messages, self._store)

    def check_for_explicit_save(self, user_message: str) -> bool:
        """检查用户消息是否包含显式保存指令"""
        return detect_explicit_save(user_message)
