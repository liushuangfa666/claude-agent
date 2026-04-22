"""
Memory 类型定义
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class MemoryType(str, Enum):
    """记忆类型枚举"""
    USER = "user"           # 用户偏好、知识背景
    FEEDBACK = "feedback"   # 用户反馈纠正
    PROJECT = "project"     # 项目上下文
    REFERENCE = "reference" # 外部系统指针


class FreshnessStatus(str, Enum):
    """新鲜度状态"""
    FRESH = "fresh"       # < 7天
    STALE = "stale"       # 7-30天
    OUTDATED = "outdated" # > 30天


@dataclass
class MemoryHeader:
    """记忆文件头部信息"""
    filename: str
    file_path: Path
    mtime: datetime
    description: str | None = None
    memory_type: MemoryType | None = None
    name: str | None = None
    created: datetime | None = None

    @property
    def age_days(self) -> float:
        """获取文件年龄（天）"""
        delta = datetime.now() - self.mtime
        return delta.total_seconds() / 86400

    def get_freshness(self) -> FreshnessStatus:
        """获取新鲜度状态"""
        age = self.age_days
        if age < 7:
            return FreshnessStatus.FRESH
        elif age < 30:
            return FreshnessStatus.STALE
        else:
            return FreshnessStatus.OUTDATED


@dataclass
class RelevantMemory:
    """检索返回的相关记忆"""
    header: MemoryHeader
    content: str
    score: float = 0.0
    reason: str | None = None


@dataclass
class FrontmatterMetadata:
    """Frontmatter 元数据"""
    name: str | None = None
    description: str | None = None
    type: str | None = None
    created: str | None = None
    updated: str | None = None
    tags: list[str] = field(default_factory=list)
    custom: dict = field(default_factory=dict)

    @classmethod
    def parse(cls, frontmatter_text: str) -> FrontmatterMetadata:
        """解析 frontmatter 文本"""
        metadata = cls()

        lines = frontmatter_text.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()

                if key == 'name':
                    metadata.name = value
                elif key == 'description':
                    metadata.description = value
                elif key == 'type':
                    metadata.type = value
                elif key == 'created':
                    metadata.created = value
                elif key == 'updated':
                    metadata.updated = value
                elif key == 'tags':
                    metadata.tags = [t.strip() for t in value.split(',')]
                else:
                    metadata.custom[key] = value

        return metadata

    def to_frontmatter(self) -> str:
        """转换为 frontmatter 格式"""
        lines = ["---"]
        if self.name:
            lines.append(f"name: {self.name}")
        if self.description:
            lines.append(f"description: {self.description}")
        if self.type:
            lines.append(f"type: {self.type}")
        if self.created:
            lines.append(f"created: {self.created}")
        if self.updated:
            lines.append(f"updated: {self.updated}")
        if self.tags:
            lines.append(f"tags: {', '.join(self.tags)}")
        for key, value in self.custom.items():
            lines.append(f"{key}: {value}")
        lines.append("---")
        return '\n'.join(lines)


@dataclass
class MemoryIndex:
    """记忆索引（MEMORY.md 内容）"""
    memories: list[MemoryHeader] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)

    def to_markdown(self) -> str:
        """转换为 Markdown 格式"""
        lines = ["# Memory Index", "", f"Last updated: {self.last_updated.isoformat()}", ""]

        by_type: dict[str, list[MemoryHeader]] = {}
        for mem in self.memories:
            type_name = _get_memory_type_value(mem.memory_type)
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append(mem)

        for type_name, memories in by_type.items():
            lines.append(f"## {type_name.upper()}")
            for mem in memories:
                freshness = mem.get_freshness()
                freshness_emoji = {
                    FreshnessStatus.FRESH: "🟢",
                    FreshnessStatus.STALE: "🟡",
                    FreshnessStatus.OUTDATED: "🔴",
                }.get(freshness, "⚪")

                desc = mem.description or "No description"
                lines.append(f"- {freshness_emoji} **{mem.name or mem.filename}**: {desc}")
            lines.append("")

        return '\n'.join(lines)


def _get_memory_type_value(memory_type) -> str:
    """安全获取 memory_type 的字符串值"""
    if memory_type is None:
        return "unknown"
    elif isinstance(memory_type, str):
        return memory_type
    else:
        return memory_type.value
