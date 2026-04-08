"""
记忆检索服务

提供记忆的检索、重排和新鲜度警告功能。
"""
import logging

from .freshness import FreshnessChecker
from .memory_store import MemoryStore
from .types import MemoryHeader, RelevantMemory, _get_memory_type_value

logger = logging.getLogger(__name__)


class MemoryRetriever:
    """记忆检索服务"""

    def __init__(self, store: MemoryStore | None = None):
        self._store = store or MemoryStore()
        self._freshness_checker = FreshnessChecker()

    def retrieve(
        self,
        query: str,
        memory_type: str | None = None,
        limit: int = 10,
    ) -> list[RelevantMemory]:
        """
        检索相关记忆
        
        Args:
            query: 用户查询
            memory_type: 可选的记忆类型过滤
            limit: 返回结果数量限制
        
        Returns:
            相关记忆列表
        """
        headers = self._store.scan_memory_files()

        if memory_type:
            headers = [h for h in headers if _get_memory_type_value(h.memory_type) == memory_type]

        if not headers:
            return []

        scored = self._score_headers(headers, query)
        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, header in scored[:limit]:
            _, content = self._store.read_memory(header)
            freshness_warning = self._freshness_checker.get_warning(header)

            results.append(RelevantMemory(
                header=header,
                content=content,
                score=score,
                reason=freshness_warning,
            ))

        return results

    def _score_headers(
        self,
        headers: list[MemoryHeader],
        query: str,
    ) -> list[tuple[float, MemoryHeader]]:
        """对记忆头进行评分"""
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []

        for header in headers:
            score = 0.0

            if header.name:
                name_words = set(header.name.lower().split())
                overlap = query_words & name_words
                score += len(overlap) * 3

            if header.description:
                desc_lower = header.description.lower()
                if query_lower in desc_lower:
                    score += 5
                desc_words = set(desc_lower.split())
                overlap = query_words & desc_words
                score += len(overlap) * 1

            if header.memory_type:
                if _get_memory_type_value(header.memory_type) in query_lower:
                    score += 2

            recency_score = max(0, 1 - (header.age_days / 90))
            score += recency_score * 2

            if score > 0:
                scored.append((score, header))

        return scored

    def retrieve_with_freshness_warnings(
        self,
        query: str,
        memory_type: str | None = None,
    ) -> tuple[list[RelevantMemory], list[str]]:
        """
        检索记忆并返回新鲜度警告
        
        Returns:
            (相关记忆列表, 新鲜度警告列表)
        """
        results = self.retrieve(query, memory_type)

        warnings = []
        stale_memories = FreshnessChecker.filter_stale([r.header for r in results])

        for header, warning in stale_memories:
            warnings.append(warning)

        return results, warnings

    def get_all_memories_by_type(
        self,
        memory_type: str,
    ) -> list[tuple[MemoryHeader, str]]:
        """获取指定类型的所有记忆"""
        headers = self._store.scan_memory_files()
        headers = [h for h in headers if _get_memory_type_value(h.memory_type) == memory_type]

        results = []
        for header in headers:
            _, content = self._store.read_memory(header)
            results.append((header, content))

        return results

    def get_freshness_report(self) -> dict[str, dict]:
        """获取新鲜度报告"""
        headers = self._store.scan_memory_files()

        report = {
            "total": len(headers),
            "fresh": 0,
            "stale": 0,
            "outdated": 0,
            "by_type": {},
        }

        for header in headers:
            freshness = self._freshness_checker.check(header)
            report[freshness.value] = report.get(freshness.value, 0) + 1

            mem_type = _get_memory_type_value(header.memory_type)
            if mem_type not in report["by_type"]:
                report["by_type"][mem_type] = {"fresh": 0, "stale": 0, "outdated": 0}
            report["by_type"][mem_type][freshness.value] += 1

        return report
