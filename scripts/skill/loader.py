"""
Skill 加载器

负责发现和加载技能。
"""
import logging
from pathlib import Path

from .parser import SkillParser
from .skill import LoadedSkill, SkillExecutionMode

logger = logging.getLogger(__name__)


class SkillLoader:
    """技能加载器"""

    SKILL_FILE = "SKILL.md"

    def __init__(self, parser: SkillParser | None = None):
        self._parser = parser or SkillParser()
        self._loaded_skills: dict[str, LoadedSkill] = {}

    def load_skill(self, skill_path: Path) -> LoadedSkill:
        """
        加载单个技能
        
        Args:
            skill_path: 技能目录或 SKILL.md 文件路径
        
        Returns:
            加载的技能
        """
        if skill_path.is_file():
            skill_file = skill_path
            skill_dir = skill_file.parent
        else:
            skill_dir = skill_path
            skill_file = skill_dir / self.SKILL_FILE

        if not skill_file.exists():
            raise FileNotFoundError(f"SKILL.md not found in {skill_dir}")

        config = self._parser.parse(skill_file)

        loaded = LoadedSkill(config=config)
        self._loaded_skills[config.name] = loaded

        logger.info(f"Loaded skill: {config.name}")

        return loaded

    def load_from_directory(self, directory: Path) -> list[LoadedSkill]:
        """
        从目录加载所有技能
        
        Args:
            directory: 技能目录
        
        Returns:
            加载的技能列表
        """
        if not directory.exists():
            return []

        loaded = []

        for item in directory.iterdir():
            if item.is_dir():
                skill_file = item / self.SKILL_FILE
                if skill_file.exists():
                    try:
                        loaded_skill = self.load_skill(skill_file)
                        loaded.append(loaded_skill)
                    except Exception as e:
                        logger.error(f"Failed to load skill from {skill_file}: {e}")

        return loaded

    def discover_skills(self) -> list[LoadedSkill]:
        """
        从标准位置发现技能
        
        查找路径优先级：
        1. .crush/skills/<name>/  (项目级)
        2. ~/.config/crush/skills/<name>/  (用户级)
        3. <managed-path>/.crush/skills/<name>/  (策略级)
        4. <plugin>/skills/<name>/  (插件级)
        """
        loaded = []

        search_paths = [
            Path.cwd() / ".crush" / "skills",
            Path.home() / ".config" / "crush" / "skills",
        ]

        for search_path in search_paths:
            if search_path.exists():
                for item in search_path.iterdir():
                    if item.is_dir() and (item / self.SKILL_FILE).exists():
                        if item.name not in self._loaded_skills:
                            try:
                                loaded_skill = self.load_skill(item / self.SKILL_FILE)
                                loaded.append(loaded_skill)
                            except Exception as e:
                                logger.error(f"Failed to load skill {item.name}: {e}")

        return loaded

    def get_skill(self, name: str) -> LoadedSkill | None:
        """获取已加载的技能"""
        return self._loaded_skills.get(name)

    def get_all_skills(self) -> list[LoadedSkill]:
        """获取所有已加载的技能"""
        return list(self._loaded_skills.values())

    def get_skills_by_mode(self, mode: SkillExecutionMode) -> list[LoadedSkill]:
        """按执行模式获取技能"""
        return [
            s for s in self._loaded_skills.values()
            if s.config.context == mode
        ]

    def reload_skill(self, name: str) -> LoadedSkill | None:
        """重新加载技能"""
        skill = self._loaded_skills.get(name)
        if not skill or not skill.config.source_path:
            return None

        skill_file = skill.config.source_path / self.SKILL_FILE
        if not skill_file.exists():
            return None

        return self.load_skill(skill_file)

    def unload_skill(self, name: str) -> bool:
        """卸载技能"""
        if name in self._loaded_skills:
            del self._loaded_skills[name]
            logger.info(f"Unloaded skill: {name}")
            return True
        return False
