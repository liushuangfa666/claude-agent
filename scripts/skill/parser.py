"""
Skill 解析器

负责解析 SKILL.md 文件。
"""
from pathlib import Path

from .skill import FrontmatterMetadata, SkillConfig, SkillExecutionMode


class SkillParser:
    """SKILL.md 解析器"""

    SKILL_FILE = "SKILL.md"

    def parse(self, file_path: Path) -> SkillConfig:
        """
        解析 SKILL.md 文件
        
        Args:
            file_path: SKILL.md 文件路径
        
        Returns:
            技能配置
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Skill file not found: {file_path}")

        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        return self.parse_content(content, file_path.parent)

    def parse_content(self, content: str, skill_dir: Path | None = None) -> SkillConfig:
        """
        解析技能内容
        
        Args:
            content: 文件内容
            skill_dir: 技能目录路径
        
        Returns:
            技能配置
        """
        metadata, body = FrontmatterMetadata.parse(content)

        if not metadata.name:
            raise ValueError("Skill must have a name in frontmatter")

        return SkillConfig(
            name=metadata.name,
            description=metadata.description or "",
            when_to_use=metadata.when_to_use or "",
            argument_hint=metadata.argument_hint or "",
            arguments=metadata.arguments,
            allowed_tools=metadata.allowed_tools,
            model=metadata.model,
            context=SkillExecutionMode(metadata.context) if metadata.context else SkillExecutionMode.INLINE,
            agent=metadata.agent or "general-purpose",
            effort=metadata.effort or "medium",
            paths=metadata.paths,
            content=body,
            source_path=skill_dir,
        )

    def parse_inline_commands(self, content: str) -> str:
        """
        解析内联命令
        
        支持 !`shell command` 语法
        
        Args:
            content: 原始内容
        
        Returns:
            命令输出替换后的内容
        """
        import subprocess

        pattern = r'!`([^`]+)`'

        def replace_command(match):
            command = match.group(1).strip()
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return result.stdout.strip() if result.stdout else result.stderr.strip()
            except subprocess.TimeoutExpired:
                return f"[Command timed out: {command}]"
            except Exception:
                return f"[Command failed: {command}]"

        return self._replace_inline_commands(content, replace_command)

    def _replace_inline_commands(self, content: str, replacer) -> str:
        """替换内联命令"""
        import re
        pattern = r'!`([^`]+)`'
        return re.sub(pattern, replacer, content)
