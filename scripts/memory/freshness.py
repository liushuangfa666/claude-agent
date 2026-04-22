"""
记忆新鲜度检查器
"""

from .types import FreshnessStatus, MemoryHeader


class FreshnessChecker:
    """记忆新鲜度检查器"""

    FRESH_THRESHOLD_DAYS = 7
    STALE_THRESHOLD_DAYS = 30

    @classmethod
    def check(cls, header: MemoryHeader) -> FreshnessStatus:
        """检查记忆新鲜度"""
        return header.get_freshness()

    @classmethod
    def get_warning(cls, header: MemoryHeader) -> str | None:
        """获取新鲜度警告信息"""
        freshness = cls.check(header)

        if freshness == FreshnessStatus.FRESH:
            return None
        elif freshness == FreshnessStatus.STALE:
            return f"⚠️ This memory is {header.age_days:.0f} days old. Consider updating it."
        else:
            return f"🔴 This memory is {header.age_days:.0f} days old. It may be outdated."

    @classmethod
    def format_freshness(cls, header: MemoryHeader) -> str:
        """格式化新鲜度信息"""
        freshness = cls.check(header)
        emoji = {
            FreshnessStatus.FRESH: "🟢",
            FreshnessStatus.STALE: "🟡",
            FreshnessStatus.OUTDATED: "🔴",
        }.get(freshness, "⚪")

        return f"{emoji} {freshness.value.upper()} ({header.age_days:.0f} days old)"

    @classmethod
    def filter_stale(cls, headers: list[MemoryHeader]) -> list[tuple[MemoryHeader, str]]:
        """过滤出过期的记忆，返回 (header, warning) 元组列表"""
        result = []
        for header in headers:
            freshness = cls.check(header)
            if freshness != FreshnessStatus.FRESH:
                warning = cls.get_warning(header)
                if warning:
                    result.append((header, warning))
        return result
