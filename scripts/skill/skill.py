"""
Skill 类型定义
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class SkillExecutionMode(str, Enum):
    """技能执行模式"""
    INLINE = "inline"  # prompt 展开到当前对话
    FORK = "fork"      # 子代理独立运行


class SkillPriority(int, Enum):
    """技能优先级（数字越小优先级越高）"""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


@dataclass
class SkillConfig:
    """技能配置"""
    name: str
    description: str
    when_to_use: str = ""
    argument_hint: str = ""
    arguments: list[dict[str, str]] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    model: str | None = None
    context: SkillExecutionMode = SkillExecutionMode.INLINE
    agent: str = "general-purpose"
    effort: str = "medium"
    paths: list[str] = field(default_factory=list)
    content: str = ""
    source_path: Path | None = None

    def __post_init__(self):
        if isinstance(self.context, str):
            self.context = SkillExecutionMode(self.context)

    def expand_content(self, arguments: str, skill_dir: Path | None = None) -> str:
        """
        展开技能内容中的变量
        
        Variables:
            $ARGUMENTS - 用户传入的参数
            ${CRUSH_SKILL_DIR} - 技能目录路径
        """
        content = self.content

        content = content.replace("$ARGUMENTS", arguments)

        if skill_dir:
            content = content.replace("${CRUSH_SKILL_DIR}", str(skill_dir))
        else:
            content = content.replace("${CRUSH_SKILL_DIR}", "")

        return content


@dataclass
class LoadedSkill:
    """加载的技能"""
    config: SkillConfig
    loaded_at: datetime = field(default_factory=datetime.now)
    last_used: datetime | None = None
    use_count: int = 0

    def mark_used(self) -> None:
        """标记技能已被使用"""
        self.last_used = datetime.now()
        self.use_count += 1


@dataclass
class SkillContext:
    """技能执行上下文"""
    skill_name: str
    arguments: str
    working_dir: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    session_id: str | None = None
    user_id: str | None = None


class FrontmatterMetadata:
    """Frontmatter 元数据"""

    def __init__(self):
        self.name: str | None = None
        self.description: str | None = None
        self.when_to_use: str | None = None
        self.argument_hint: str | None = None
        self.arguments: list[dict[str, str]] = []
        self.allowed_tools: list[str] = []
        self.model: str | None = None
        self.context: str | None = None
        self.agent: str | None = None
        self.effort: str | None = None
        self.paths: list[str] = []

    @classmethod
    def parse(cls, text: str) -> tuple[FrontmatterMetadata, str]:
        """解析 frontmatter 和正文"""
        lines = text.split('\n')

        if not lines or lines[0].strip() != '---':
            return cls(), text

        end_idx = None
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == '---':
                end_idx = i
                break

        if end_idx is None:
            return cls(), text

        metadata = cls()
        metadata_lines = lines[1:end_idx]

        for line in metadata_lines:
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
                elif key == 'when_to_use':
                    metadata.when_to_use = value
                elif key == 'argument-hint':
                    metadata.argument_hint = value
                elif key == 'arguments':
                    metadata.arguments = cls._parse_arguments(value)
                elif key == 'allowed-tools':
                    metadata.allowed_tools = [t.strip() for t in value.split(',')]
                elif key == 'model':
                    metadata.model = value
                elif key == 'context':
                    metadata.context = value
                elif key == 'agent':
                    metadata.agent = value
                elif key == 'effort':
                    metadata.effort = value
                elif key == 'paths':
                    metadata.paths = [p.strip() for p in value.split('\n') if p.strip()]

        body = '\n'.join(lines[end_idx + 1:])
        return metadata, body.strip()

    @staticmethod
    def _parse_arguments(text: str) -> list[dict[str, str]]:
        """解析 arguments 定义"""
        result = []
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('- name:'):
                name = line[7:].strip()
                result.append({"name": name})
        return result
