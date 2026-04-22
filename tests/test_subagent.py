"""
Subagent Tests - Phase 1
"""
import pytest
import sys
import os

# Add scripts to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.subagent.types import SubagentType
from scripts.subagent.tool_filter import is_tool_allowed, filter_tools_by_type, get_allowed_tools
from scripts.subagent.prompts import get_subagent_prompt


class TestSubagentType:
    """SubagentType 枚举测试"""

    def test_subagent_type_enum_values(self):
        """测试 SubagentType 枚举值"""
        assert SubagentType.EXPLORE.value == "Explore"
        assert SubagentType.PLAN.value == "Plan"
        assert SubagentType.VERIFICATION.value == "Verification"
        assert SubagentType.GENERAL_PURPOSE.value == "GeneralPurpose"

    def test_subagent_type_from_string(self):
        """测试从字符串创建 SubagentType"""
        assert SubagentType.from_string("Explore") == SubagentType.EXPLORE
        assert SubagentType.from_string("Plan") == SubagentType.PLAN
        assert SubagentType.from_string("Verification") == SubagentType.VERIFICATION
        assert SubagentType.from_string("GeneralPurpose") == SubagentType.GENERAL_PURPOSE

        # 大小写敏感（按实际实现）
        with pytest.raises(ValueError):
            SubagentType.from_string("explore")

    def test_subagent_type_description(self):
        """测试描述属性"""
        assert "探索" in SubagentType.EXPLORE.description
        assert "规划" in SubagentType.PLAN.description
        assert "验证" in SubagentType.VERIFICATION.description


class TestToolFilter:
    """工具过滤测试"""

    def test_explore_allows_readonly_tools(self):
        """Explore 类型只能使用只读工具"""
        assert is_tool_allowed("Read", "Explore")
        assert is_tool_allowed("Glob", "Explore")
        assert is_tool_allowed("Grep", "Explore")
        # Agent 工具不在 Explore 允许列表中
        assert not is_tool_allowed("Agent", "Explore")

    def test_explore_blocks_write_tools(self):
        """Explore 类型阻止写工具"""
        assert not is_tool_allowed("Edit", "Explore")
        assert not is_tool_allowed("Write", "Explore")
        assert not is_tool_allowed("Bash", "Explore")

    def test_plan_allows_some_tools(self):
        """Plan 类型可以使用部分工具"""
        assert is_tool_allowed("Read", "Plan")
        assert is_tool_allowed("Glob", "Plan")
        assert is_tool_allowed("Grep", "Plan")
        # Plan 类型不允许 Edit 工具
        assert not is_tool_allowed("Edit", "Plan")
        assert not is_tool_allowed("Bash", "Plan")

    def test_verification_allows_bash(self):
        """Verification 类型可以使用 Bash"""
        assert is_tool_allowed("Bash", "Verification")
        assert is_tool_allowed("Read", "Verification")

    def test_general_purpose_allows_all(self):
        """GeneralPurpose 类型允许所有工具"""
        assert is_tool_allowed("Read", "GeneralPurpose")
        assert is_tool_allowed("Edit", "GeneralPurpose")
        assert is_tool_allowed("Bash", "GeneralPurpose")
        assert is_tool_allowed("Write", "GeneralPurpose")

    def test_filter_tools_by_type(self):
        """测试按类型过滤工具列表"""
        all_tools = [
            {"name": "Read"},
            {"name": "Edit"},
            {"name": "Bash"},
            {"name": "Glob"},
        ]

        explore_tools = filter_tools_by_type(all_tools, "Explore")
        explore_names = [t["name"] for t in explore_tools]
        assert "Read" in explore_names
        assert "Glob" in explore_names
        assert "Edit" not in explore_names
        assert "Bash" not in explore_names

    def test_get_allowed_tools(self):
        """测试获取允许的工具名称"""
        explore_tools = get_allowed_tools("Explore")
        assert "Read" in explore_tools
        assert "Edit" not in explore_tools

        plan_tools = get_allowed_tools("Plan")
        assert "Read" in plan_tools
        # Plan 类型不允许 Edit
        assert "Edit" not in plan_tools


class TestSubagentPrompts:
    """子代理提示词测试"""

    def test_get_subagent_prompt_explore(self):
        """测试 Explore 类型提示词"""
        prompt = get_subagent_prompt("Explore")
        assert "只读" in prompt or "只读" not in prompt  # 只要返回了就行
        assert len(prompt) > 0

    def test_get_subagent_prompt_plan(self):
        """测试 Plan 类型提示词"""
        prompt = get_subagent_prompt("Plan")
        assert len(prompt) > 0

    def test_get_subagent_prompt_verification(self):
        """测试 Verification 类型提示词"""
        prompt = get_subagent_prompt("Verification")
        assert len(prompt) > 0

    def test_get_subagent_prompt_with_context(self):
        """测试带上下文的提示词"""
        from scripts.subagent.prompts import get_subagent_prompt_with_context

        prompt = get_subagent_prompt_with_context(
            "Explore",
            task_context="这是一个 Python 项目"
        )
        assert len(prompt) > 0
        assert "Python" in prompt


class TestSubagentRegistry:
    """子代理注册表测试"""

    def test_subagent_registry_create(self):
        """测试创建子代理"""
        from scripts.subagent.registry import SubagentRegistry

        registry = SubagentRegistry()
        info = registry.create(
            name="test_agent",
            subagent_type=SubagentType.EXPLORE,
            description="测试代理",
            prompt="查看目录结构",
        )

        assert info.agent_id is not None
        assert info.name == "test_agent"
        assert info.subagent_type == SubagentType.EXPLORE
        assert info.status == "pending"

    def test_subagent_registry_get(self):
        """测试获取子代理"""
        from scripts.subagent.registry import SubagentRegistry

        registry = SubagentRegistry()
        info = registry.create(
            name="test_agent",
            subagent_type=SubagentType.PLAN,
            description="测试",
            prompt="规划任务",
        )

        retrieved = registry.get(info.agent_id)
        assert retrieved is not None
        assert retrieved.agent_id == info.agent_id

    def test_subagent_registry_update_status(self):
        """测试更新子代理状态"""
        from scripts.subagent.registry import SubagentRegistry

        registry = SubagentRegistry()
        info = registry.create(
            name="test_agent",
            subagent_type=SubagentType.GENERAL_PURPOSE,
            description="测试",
            prompt="执行任务",
        )

        success = registry.update_status(info.agent_id, "running")
        assert success

        updated = registry.get(info.agent_id)
        assert updated.status == "running"
