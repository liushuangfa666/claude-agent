"""
Compact Manager - 压缩管理器
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .context_collapse import ContextCollapser, create_collapser
from .message_scorer import get_compactable_messages, score_message_importance
from .snip_compact import SnipCompactor
from .token_budget import calculate_budget_info, should_trigger_compaction
from .token_counter import count_messages_tokens, count_tokens

logger = logging.getLogger(__name__)


@dataclass
class CompactConfig:
    """压缩配置"""
    warning_buffer: int = 40000
    auto_compact_buffer: int = 20000
    blocking_buffer: int = 5000
    max_consecutive_failures: int = 3
    summary_model: str = "sonnet"
    preserve_recent_turns: int = 5
    preserve_important_threshold: float = 0.6  # 重要性阈值，高于此分数的消息不被压缩
    use_importance_scoring: bool = True  # 是否使用重要性评分


@dataclass
class CompactionResult:
    """压缩结果"""
    success: bool
    original_tokens: int = 0
    compacted_tokens: int = 0
    messages_removed: int = 0
    summary: str = ""
    error: str = ""


class CompactManager:
    """上下文压缩管理器"""

    def __init__(self, config: CompactConfig | None = None):
        self.config = config or CompactConfig()
        self._consecutive_failures = 0
        self._last_compact_tokens = 0
        self._snip_compactor = SnipCompactor()
        self._collapser: ContextCollapser | None = None

    @property
    def collapser(self) -> ContextCollapser:
        """获取或创建上下文折叠器"""
        if self._collapser is None:
            self._collapser = create_collapser()
        return self._collapser

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def reset_failures(self) -> None:
        self._consecutive_failures = 0

    def increment_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.config.max_consecutive_failures:
            logger.warning(
                f"Max consecutive compact failures reached: {self._consecutive_failures}"
            )

    def should_warn(self, tokens: int) -> bool:
        """检查是否应该发出警告"""
        return tokens >= self.config.warning_buffer

    def should_auto_compact(self, tokens: int) -> bool:
        """检查是否应该自动压缩（基于 budget 系统）"""
        if self._consecutive_failures >= self.config.max_consecutive_failures:
            return False
        return tokens >= self.config.auto_compact_buffer

    def should_auto_compact_with_budget(
        self,
        max_context_tokens: int,
        current_tokens: int,
    ) -> tuple[bool, str]:
        """
        使用 budget 系统检查是否应该自动压缩

        Args:
            max_context_tokens: 最大上下文 token 数
            current_tokens: 当前已用 token 数

        Returns:
            (should_compact, reason) 元组
        """
        if self._consecutive_failures >= self.config.max_consecutive_failures:
            return False, "连续失败次数过多"

        budget_info = calculate_budget_info(
            max_context_tokens,
            current_tokens,
            self.config.warning_buffer,
        )
        return should_trigger_compaction(budget_info)

    def should_block(self, tokens: int) -> bool:
        """检查是否应该阻塞"""
        return tokens >= (self.config.auto_compact_buffer + self.config.blocking_buffer)

    async def compact_conversation(self, messages: list[dict]) -> CompactionResult:
        """
        执行 LLM 摘要压缩

        将中间的对话消息压缩为摘要，保留系统消息和最近的消息。
        在生成摘要之前，先执行 Snip-Compact 裁剪超长工具输出。
        """
        if not messages:
            return CompactionResult(success=True)

        original_tokens = count_messages_tokens(messages)

        # Step 1: Snip-Compact - 先裁剪超长工具输出
        messages = self._snip_messages(messages)

        # 识别需要压缩的消息
        compactable, preserved = self._identify_compactable(messages)

        if not compactable:
            return CompactionResult(success=True, original_tokens=original_tokens)

        # 生成摘要
        summary = await self._generate_summary(compactable)

        if not summary:
            return CompactionResult(
                success=False,
                original_tokens=original_tokens,
                error="Failed to generate summary"
            )

        self._consecutive_failures = 0
        compacted_tokens = count_tokens(summary)

        return CompactionResult(
            success=True,
            original_tokens=original_tokens,
            compacted_tokens=compacted_tokens,
            messages_removed=len(compactable),
            summary=summary,
        )

    def _snip_messages(self, messages: list[dict]) -> list[dict]:
        """
        对消息列表执行 Snip-Compact 裁剪超长工具输出
        """
        return self._snip_compactor.compact_api_messages(messages)

    def _identify_compactable(
        self, messages: list[dict]
    ) -> tuple[list[dict], list[dict]]:
        """识别可以压缩的消息和需要保留的消息"""
        system_messages = [m for m in messages if m.get("role") == "system"]

        recent_count = self.config.preserve_recent_turns * 2
        recent_messages = messages[-recent_count:] if len(messages) > recent_count else messages

        # 使用重要性评分
        if self.config.use_importance_scoring:
            compactable, preserved = get_compactable_messages(
                messages,
                min_score=self.config.preserve_important_threshold,
                preserve_recent=self.config.preserve_recent_turns,
            )
            return compactable, preserved

        # 回退到原有的基于位置的策略
        # compactable = 早期对话（去掉 system 和 recent）
        compactable = messages[:-recent_count] if len(messages) > recent_count else []
        compactable = [m for m in compactable if m.get("role") != "system"]

        # preserved = system + recent
        preserved = system_messages + recent_messages

        return compactable, preserved

    async def _generate_summary(self, messages: list[dict]) -> str:
        """使用 LLM 生成摘要"""
        try:
            from ..agent import call_llm
        except ImportError:
            from agent import call_llm

        # 构建摘要提示
        conversation_text = self._format_messages_for_summary(messages)

        prompt = f"""请简洁地总结以下对话，保留关键信息和决策:

{conversation_text}

摘要要求:
1. 保留重要的技术细节和代码片段
2. 记录已完成的步骤和结果
3. 保留关键的错误和解决方案
4. 简洁明了，用中文回复

摘要:"""

        try:
            response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: call_llm(
                        [{"role": "user", "content": prompt}],
                        model=self.config.summary_model,
                    )
                ),
                timeout=30.0
            )

            # 提取摘要内容
            if hasattr(response, 'content'):
                return response.content
            return str(response)

        except asyncio.TimeoutError:
            logger.error("Summary generation timed out")
            return ""
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return ""

    def _format_messages_for_summary(self, messages: list[dict]) -> str:
        """格式化消息用于摘要"""
        lines = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if content:
                lines.append(f"[{role.upper()}]: {content[:500]}")
        return "\n".join(lines)

    async def auto_compact_if_needed(self, messages: list[dict]) -> bool:
        """检查并执行自动压缩"""
        tokens = count_messages_tokens(messages)

        if not self.should_auto_compact(tokens):
            return False

        result = await self.compact_conversation(messages)

        if result.success:
            self._last_compact_tokens = result.compacted_tokens
            return True
        else:
            self.increment_failure()
            return False

    def get_token_count(self, messages: list[dict]) -> int:
        """获取当前 token 数"""
        return count_messages_tokens(messages)

    def apply_collapses(self, messages: list[dict], max_messages: int = 50) -> list[dict]:
        """
        应用上下文折叠

        Args:
            messages: 消息列表
            max_messages: 保留的最大消息数

        Returns:
            处理后的消息列表
        """
        return self.collapser.auto_collapse(messages, max_messages)

    def expand_collapse(self, messages: list[dict], collapse_id: str, marker_idx: int) -> list[dict]:
        """
        展开折叠

        Args:
            messages: 包含折叠标记的消息列表
            collapse_id: 折叠 ID
            marker_idx: 折叠标记的索引

        Returns:
            展开后的消息列表
        """
        return self.collapser.expand_collapse(messages, collapse_id, marker_idx)
