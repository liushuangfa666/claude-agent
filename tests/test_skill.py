"""
Skill 和 Slash Command 测试
"""
import pytest

from scripts.skill.slash_parser import (
    parse_slash_command,
    is_slash_command,
    extract_skill_invocation,
    SlashCommand,
)
from scripts.skill.skill_tool import SkillTool, SkillListTool, SkillInfoTool
from scripts.skill.loader import SkillLoader


class TestSlashParser:
    """Slash 命令解析器测试"""

    def test_parse_slash_command_basic(self):
        """测试基本 slash 命令"""
        result = parse_slash_command("/help")
        assert result is not None
        assert result.skill_name == "help"
        assert result.arguments == ""

    def test_parse_slash_command_with_args(self):
        """测试带参数的 slash 命令"""
        result = parse_slash_command("/test arg1 arg2")
        assert result is not None
        assert result.skill_name == "test"
        assert result.arguments == "arg1 arg2"

    def test_parse_slash_command_with_quoted_args(self):
        """测试带引号参数的 slash 命令"""
        result = parse_slash_command('/skill "multi word"')
        assert result is not None
        assert result.skill_name == "skill"
        assert result.arguments == '"multi word"'

    def test_parse_slash_command_normal_message(self):
        """测试普通消息返回 None"""
        result = parse_slash_command("normal message")
        assert result is None

    def test_parse_slash_command_empty(self):
        """测试空消息返回 None"""
        assert parse_slash_command("") is None
        assert parse_slash_command("   ") is None
        assert parse_slash_command(None) is None

    def test_parse_slash_command_double_slash(self):
        """测试双斜杠返回 None"""
        assert parse_slash_command("//skill") is None

    def test_parse_slash_command_no_name(self):
        """测试只有斜杠返回 None"""
        result = parse_slash_command("/")
        assert result is None

    def test_parse_slash_command_with_spaces(self):
        """测试多空格分隔"""
        result = parse_slash_command("/skill    arg1    arg2")
        assert result is not None
        assert result.skill_name == "skill"
        assert result.arguments == "arg1    arg2"

    def test_is_slash_command(self):
        """测试 slash 命令识别"""
        assert is_slash_command("/skill") is True
        assert is_slash_command("/s") is True
        assert is_slash_command("normal") is False
        assert is_slash_command("/") is False
        assert is_slash_command("//skill") is False

    def test_extract_skill_invocation(self):
        """测试 skill 调用提取"""
        result = extract_skill_invocation("/skill arg1")
        assert result == ("skill", "arg1")

        result = extract_skill_invocation("normal message")
        assert result is None

    def test_slash_command_is_empty(self):
        """测试 SlashCommand.is_empty"""
        cmd = SlashCommand(skill_name="test", arguments="")
        assert cmd.is_empty is False

        cmd = SlashCommand(skill_name="", arguments="")
        assert cmd.is_empty is True


class TestSkillLoader:
    """Skill 加载器测试"""

    def test_loader_initialization(self):
        """测试加载器初始化"""
        loader = SkillLoader()
        assert loader is not None
        assert loader._loaded_skills == {}

    def test_discover_skills(self):
        """测试技能发现"""
        loader = SkillLoader()
        skills = loader.discover_skills()
        # 返回已加载的技能列表
        assert isinstance(skills, list)


class TestSkillTool:
    """Skill 工具测试"""

    @pytest.fixture
    def skill_tool(self):
        return SkillTool()

    @pytest.mark.asyncio
    async def test_skill_tool_initialization(self, skill_tool):
        """测试 SkillTool 初始化"""
        assert skill_tool is not None
        assert skill_tool.name == "Skill"

    @pytest.mark.asyncio
    async def test_skill_tool_invalid_skill(self, skill_tool):
        """测试不存在的 skill"""
        result = await skill_tool.call({"skill": "nonexistent_skill"}, {})
        assert result.success is False
        assert result.data is None
        assert "not found" in str(result.error)


class TestSkillListTool:
    """SkillList 工具测试"""

    @pytest.fixture
    def list_tool(self):
        return SkillListTool()

    @pytest.mark.asyncio
    async def test_skill_list_tool(self, list_tool):
        """测试列出所有技能"""
        result = await list_tool.call({}, {})
        assert result.success is True
        assert "skills" in result.data
        assert "count" in result.data
        assert isinstance(result.data["skills"], list)


class TestSkillInfoTool:
    """SkillInfo 工具测试"""

    @pytest.fixture
    def info_tool(self):
        return SkillInfoTool()

    @pytest.mark.asyncio
    async def test_skill_info_tool_invalid(self, info_tool):
        """测试获取不存在的 skill 详情"""
        result = await info_tool.call({"skill": "nonexistent"}, {})
        assert result.success is False
        assert result.data is None
        assert "not found" in str(result.error)
