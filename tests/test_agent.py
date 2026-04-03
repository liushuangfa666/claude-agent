import pytest
from scripts.agent import Agent, AgentConfig
from scripts.tools import ReadTool, BashTool, WriteTool


class TestAgentConfig:
    def test_default_config(self):
        config = AgentConfig()
        assert config.max_turns == 20
        assert config.timeout == 180
        assert config.temperature == 0.1

    def test_custom_config(self):
        config = AgentConfig(max_turns=5, timeout=60)
        assert config.max_turns == 5
        assert config.timeout == 60


class TestToolRegistry:
    def test_tool_registration(self):
        from scripts.tool import get_registry, ToolRegistry
        registry = ToolRegistry()
        tool = ReadTool()
        registry.register(tool)
        assert registry.get("Read") is tool
        assert registry.find("Read") is tool

    def test_tool_not_found(self):
        from scripts.tool import get_registry
        registry = get_registry()
        assert registry.get("NonExistent") is None


class TestReadToolValidation:
    def test_valid_input(self):
        tool = ReadTool()
        valid, err = tool.validate_input({"file_path": "README.md"})
        assert valid is True
        assert err is None

    def test_missing_required(self):
        tool = ReadTool()
        valid, err = tool.validate_input({})
        assert valid is False
        assert "file_path" in err


class TestBashToolDestructive:
    def test_destructive_commands(self):
        tool = BashTool()
        assert tool.is_destructive({"command": "rm -rf /"}) is True
        assert tool.is_destructive({"command": "rm file.txt"}) is True

    def test_safe_commands(self):
        tool = BashTool()
        assert tool.is_destructive({"command": "ls -la"}) is False
        assert tool.is_destructive({"command": "git status"}) is False


class TestWriteToolDestructive:
    def test_overwrite_is_destructive(self):
        tool = WriteTool()
        assert tool.is_destructive({"file_path": "existing.txt", "content": ""}) is True

    def test_append_not_destructive(self):
        tool = WriteTool()
        assert tool.is_destructive({"file_path": "existing.txt", "content": "", "append": True}) is False


class TestPermissionEngine:
    def test_allow_pattern(self):
        from scripts.permission import PermissionEngine
        engine = PermissionEngine()
        engine.allow("Bash(git *)")
        result = engine.check("Bash", {"command": "git status"})
        assert result.behavior == "allow"

    def test_deny_pattern(self):
        from scripts.permission import PermissionEngine
        engine = PermissionEngine()
        engine.deny("Bash(rm *)")
        result = engine.check("Bash", {"command": "rm file.txt"})
        assert result.behavior == "deny"

    def test_default_behavior(self):
        from scripts.permission import PermissionEngine
        engine = PermissionEngine()
        engine.set_default("ask")
        result = engine.check("Bash", {"command": "ls"})
        assert result.behavior == "ask"

    def test_glob_matching(self):
        from scripts.permission import PermissionEngine
        engine = PermissionEngine()
        engine.deny("Edit(*.env)")
        result = engine.check("Edit", {"file_path": "prod.env"})
        assert result.behavior == "deny"
        result = engine.check("Edit", {"file_path": "config.py"})
        assert result.behavior != "deny"


class TestContextBuilder:
    def test_context_structure(self):
        from scripts.context import ContextBuilder
        builder = ContextBuilder()
        builder.add_system_context("git status info")
        builder.add_user_context("cwd info")
        ctx = builder.build()
        assert "system" in ctx
        assert "user" in ctx
        assert "git status info" in ctx["system"]
        assert "cwd info" in ctx["user"]

    def test_default_context(self):
        from scripts.context import build_default_context
        ctx = build_default_context()
        assert isinstance(ctx, dict)
        assert "system" in ctx


class TestSystemPromptBuilder:
    def test_build_prompt(self):
        from scripts.system_prompt import SystemPromptBuilder
        from scripts.tool import ToolDefinition
        builder = SystemPromptBuilder()
        builder.add_role()
        builder.add_tools_section([])
        builder.add_guidelines()
        prompt = builder.build()
        assert len(prompt) > 0
        assert "AI 助手" in prompt or "assistant" in prompt.lower()
