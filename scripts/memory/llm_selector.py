"""
LLM 记忆选择器

使用 LLM 来选择相关的记忆。
"""
import logging

from .types import MemoryHeader, RelevantMemory, _get_memory_type_value

logger = logging.getLogger(__name__)


class LLMSelector:
    """LLM 记忆选择器"""

    def __init__(self, llm_client: object | None = None):
        """
        初始化选择器
        
        Args:
            llm_client: LLM 客户端，如果为 None 则使用关键词匹配
        """
        self._llm_client = llm_client

    async def select_relevant(
        self,
        headers: list[MemoryHeader],
        query: str,
        top_k: int = 5,
    ) -> list[RelevantMemory]:
        """
        选择与查询相关的记忆
        
        Args:
            headers: 记忆头列表
            query: 用户查询
            top_k: 返回前 k 个结果
        
        Returns:
            按相关性排序的记忆列表
        """
        if not headers:
            return []

        if self._llm_client is None:
            return self._keyword_match(headers, query, top_k)

        return await self._llm_select(headers, query, top_k)

    def _keyword_match(
        self,
        headers: list[MemoryHeader],
        query: str,
        top_k: int = 5,
    ) -> list[RelevantMemory]:
        """基于关键词匹配选择记忆"""
        query_words = set(query.lower().split())
        scored = []

        for header in headers:
            score = 0.0
            reasons = []

            if header.name:
                name_words = set(header.name.lower().split())
                overlap = query_words & name_words
                if overlap:
                    score += len(overlap) * 2
                    reasons.append(f"name match: {overlap}")

            if header.description:
                desc_words = set(header.description.lower().split())
                overlap = query_words & desc_words
                if overlap:
                    score += len(overlap)
                    reasons.append(f"description match: {overlap}")

            if header.memory_type:
                if _get_memory_type_value(header.memory_type) in query.lower():
                    score += 1
                    reasons.append(f"type match: {header.memory_type.value}")

            if score > 0:
                scored.append((score, header, ", ".join(reasons)))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            RelevantMemory(header=h, content="", score=s, reason=r)
            for s, h, r in scored[:top_k]
        ]

    async def _llm_select(
        self,
        headers: list[MemoryHeader],
        query: str,
        top_k: int = 5,
    ) -> list[RelevantMemory]:
        """使用 LLM 选择相关记忆"""
        if not headers:
            return []

        memory_summaries = []
        for i, header in enumerate(headers):
            desc = header.description or "No description"
            name = header.name or header.filename
            mem_type = header.memory_type.value if header.memory_type else "unknown"
            age = f"{header.age_days:.0f} days old"

            memory_summaries.append(
                f"{i}. [{mem_type}] {name} ({age}): {desc}"
            )

        prompt = f"""Given the user's query: "{query}"

Select the top {top_k} most relevant memories from this list:

{chr(10).join(memory_summaries)}

Respond with the indices of the selected memories, one per line.
Only respond with numbers, no other text."""

        try:
            response = await self._llm_client.complete(prompt)
            lines = response.strip().split('\n')

            selected = []
            for line in lines:
                line = line.strip()
                if line.isdigit():
                    idx = int(line)
                    if 0 <= idx < len(headers):
                        selected.append(idx)

            result = []
            for idx in selected[:top_k]:
                header = headers[idx]
                result.append(RelevantMemory(
                    header=header,
                    content="",
                    score=1.0,
                    reason="LLM selected",
                ))

            return result
        except Exception as e:
            logger.error(f"LLM selection failed: {e}, falling back to keyword match")
            return self._keyword_match(headers, query, top_k)
