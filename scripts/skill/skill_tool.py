"""
Skill 工具实现

提供技能执行能力。
"""
import logging
import re
from pathlib import Path

from ..tool import BaseTool, ToolResult
from .loader import SkillLoader
from .skill import SkillContext, SkillExecutionMode

logger = logging.getLogger(__name__)


class SkillTool(BaseTool):
    """技能执行工具"""

    name = "Skill"
    description = "执行一个技能/工作流"

    input_schema = {
        "type": "object",
        "properties": {
            "skill": {"type": "string", "description": "技能名称"},
            "args": {"type": "string", "description": "技能参数"},
        },
        "required": ["skill"],
    }

    def __init__(self, loader: SkillLoader | None = None):
        super().__init__()
        self._loader = loader or SkillLoader()
        self._loader.discover_skills()

    async def call(self, args: dict, context: dict) -> ToolResult:
        """
        执行技能
        
        Args:
            skill: 技能名称
            args: 技能参数
        """
        skill_name = args["skill"]
        skill_args = args.get("args", "")

        loaded = self._loader.get_skill(skill_name)

        if not loaded:
            return ToolResult(
                success=False,
                data=None,
                error=f"Skill '{skill_name}' not found",
            )

        skill_context = SkillContext(
            skill_name=skill_name,
            arguments=skill_args,
            working_dir=Path.cwd(),
            session_id=context.get("session_id"),
        )

        expanded_content = loaded.config.expand_content(
            skill_args,
            loaded.config.source_path,
        )

        expanded_content = self._expand_inline_commands(expanded_content)

        loaded.mark_used()

        if loaded.config.context == SkillExecutionMode.INLINE:
            return ToolResult(
                success=True,
                data={
                    "mode": "inline",
                    "skill": skill_name,
                    "expanded_prompt": expanded_content,
                    "allowed_tools": loaded.config.allowed_tools,
                },
            )
        else:
            return ToolResult(
                success=True,
                data={
                    "mode": "fork",
                    "skill": skill_name,
                    "prompt": expanded_content,
                    "agent": loaded.config.agent,
                    "model": loaded.config.model,
                },
            )

    def _expand_inline_commands(self, content: str) -> str:
        """展开内联命令"""
        pattern = r'!`([^`]+)`'

        def replace_command(match):
            command = match.group(1).strip()
            try:
                import subprocess
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
            except Exception as e:
                return f"[Command failed: {e}]"

        return re.sub(pattern, replace_command, content)

    def is_destructive(self, args: dict) -> bool:
        """技能默认不标记为危险操作"""
        return False

    def get_activity_description(self, args: dict) -> str:
        """获取活动描述"""
        return f"Executing skill: {args.get('skill', 'unknown')}"


class SkillListTool(BaseTool):
    """列出所有技能"""

    name = "SkillList"
    description = "列出所有可用的技能"

    input_schema = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, loader: SkillLoader | None = None):
        super().__init__()
        self._loader = loader or SkillLoader()
        self._loader.discover_skills()

    async def call(self, args: dict, context: dict) -> ToolResult:
        skills = self._loader.get_all_skills()

        skill_list = []
        for skill in skills:
            skill_list.append({
                "name": skill.config.name,
                "description": skill.config.description,
                "when_to_use": skill.config.when_to_use,
                "context": skill.config.context.value,
                "use_count": skill.use_count,
                "last_used": skill.last_used.isoformat() if skill.last_used else None,
            })

        return ToolResult(
            success=True,
            data={"skills": skill_list, "count": len(skill_list)},
        )


class SkillInfoTool(BaseTool):
    """获取技能详情"""

    name = "SkillInfo"
    description = "获取技能详细信息"

    input_schema = {
        "type": "object",
        "properties": {
            "skill": {"type": "string", "description": "技能名称"},
        },
        "required": ["skill"],
    }

    def __init__(self, loader: SkillLoader | None = None):
        super().__init__()
        self._loader = loader or SkillLoader()
        self._loader.discover_skills()

    async def call(self, args: dict, context: dict) -> ToolResult:
        skill_name = args["skill"]

        loaded = self._loader.get_skill(skill_name)

        if not loaded:
            return ToolResult(
                success=False,
                data=None,
                error=f"Skill '{skill_name}' not found",
            )

        return ToolResult(
            success=True,
            data={
                "name": loaded.config.name,
                "description": loaded.config.description,
                "when_to_use": loaded.config.when_to_use,
                "argument_hint": loaded.config.argument_hint,
                "arguments": loaded.config.arguments,
                "allowed_tools": loaded.config.allowed_tools,
                "model": loaded.config.model,
                "context": loaded.config.context.value,
                "agent": loaded.config.agent,
                "effort": loaded.config.effort,
                "paths": loaded.config.paths,
                "use_count": loaded.use_count,
                "last_used": loaded.last_used.isoformat() if loaded.last_used else None,
            },
        )
