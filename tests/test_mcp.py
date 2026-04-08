"""
MCP 模块测试
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMCPTool:
    """MCPTool 包装器测试"""

    def test_tool_name_format(self):
        """测试 MCP 工具名称格式"""
        from scripts.mcp.mcp_string_utils import format_mcp_tool_name

        name = format_mcp_tool_name("github", "list_repos")
        assert name == "mcp__github__list_repos"

    def test_parse_tool_name(self):
        """测试解析 MCP 工具名称"""
        from scripts.mcp.mcp_string_utils import parse_mcp_tool_name

        server, tool = parse_mcp_tool_name("mcp__github__list_repos")
        assert server == "github"
        assert tool == "list_repos"

    def test_parse_invalid_tool_name(self):
        """测试解析无效工具名称"""
        from scripts.mcp.mcp_string_utils import parse_mcp_tool_name

        result = parse_mcp_tool_name("invalid_name")
        assert result is None

    def test_parse_wrong_prefix(self):
        """测试解析错误前缀"""
        from scripts.mcp.mcp_string_utils import parse_mcp_tool_name

        result = parse_mcp_tool_name("github__list_repos")
        assert result is None


class TestMCPToolExecutor:
    """MCPToolExecutor 测试"""

    def test_executor_init(self):
        """测试执行器初始化"""
        from scripts.mcp import MCPToolExecutor

        executor = MCPToolExecutor()
        assert executor.tool_count == 0

    @pytest.mark.asyncio
    async def test_register_tools_empty(self):
        """测试注册空工具列表"""
        from scripts.mcp import MCPToolExecutor

        mock_manager = MagicMock()
        mock_manager.get_all_tools.return_value = []

        executor = MCPToolExecutor(mock_manager)
        tools = executor.register_all_tools()

        assert len(tools) == 0
        assert executor.tool_count == 0

    @pytest.mark.asyncio
    async def test_register_tools_with_tools(self):
        """测试注册工具"""
        from scripts.mcp import MCPToolExecutor, McpTool

        mock_tool = MagicMock(spec=McpTool)
        mock_tool.server_name = "github"
        mock_tool.name = "list_repos"
        mock_tool.description = "List repositories"
        mock_tool.input_schema = {"type": "object", "properties": {}}

        mock_manager = MagicMock()
        mock_manager.get_all_tools.return_value = [mock_tool]

        executor = MCPToolExecutor(mock_manager)
        tools = executor.register_all_tools()

        assert len(tools) == 1
        assert tools[0].name == "mcp__github__list_repos"
        assert executor.tool_count == 1

    @pytest.mark.asyncio
    async def test_unregister_all_tools(self):
        """测试取消注册所有工具"""
        from scripts.mcp import MCPToolExecutor, McpTool

        mock_tool = MagicMock(spec=McpTool)
        mock_tool.server_name = "github"
        mock_tool.name = "list_repos"
        mock_tool.description = "List repositories"
        mock_tool.input_schema = {"type": "object", "properties": {}}

        mock_manager = MagicMock()
        mock_manager.get_all_tools.return_value = [mock_tool]

        executor = MCPToolExecutor(mock_manager)
        executor.register_all_tools()
        assert executor.tool_count == 1

        executor.unregister_all_tools()
        assert executor.tool_count == 0


class TestMCPManager:
    """MCPServerManager 测试"""

    @pytest.mark.asyncio
    async def test_manager_init(self):
        """测试管理器初始化"""
        from scripts.mcp import MCPServerManager

        manager = MCPServerManager()
        assert len(manager.get_all_servers()) == 0
        assert len(manager.get_connected_servers()) == 0

    def test_get_server_not_found(self):
        """测试获取不存在的服务器"""
        from scripts.mcp import MCPServerManager

        manager = MCPServerManager()
        result = manager.get_server("nonexistent")
        assert result is None

    def test_get_tool_not_found(self):
        """测试获取不存在的工具"""
        from scripts.mcp import MCPServerManager

        manager = MCPServerManager()
        result = manager.get_tool("github", "nonexistent")
        assert result is None

    def test_get_tool_by_full_name_invalid(self):
        """测试获取无效完整名称的工具"""
        from scripts.mcp import MCPServerManager

        manager = MCPServerManager()

        # 无效格式
        result = manager.get_tool_by_full_name("invalid")
        assert result is None

        # 错误前缀
        result = manager.get_tool_by_full_name("github__list_repos")
        assert result is None


class TestMCPIntegration:
    """MCP 集成测试"""

    def test_integration_register_all_tools(self):
        """测试 integration.register_all_tools 不抛出异常"""
        from scripts.integration import register_all_tools

        # 这个函数应该能正常调用（虽然 MCP 可能没有配置）
        result = register_all_tools()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_initialize_mcp_manager_no_config(self):
        """测试初始化无配置的 MCP 管理器"""
        from scripts.integration import _initialize_mcp_manager

        # 没有配置文件应该返回 None 而不是抛出异常
        manager = await _initialize_mcp_manager(None)
        # 实际上会因为没有配置而返回 None
        assert manager is None or hasattr(manager, 'get_all_servers')


class TestMCPServerInfo:
    """MCP 服务器信息测试"""

    def test_server_info_creation(self):
        """测试服务器信息创建"""
        from scripts.mcp import McpServerConfig, McpServerInfo, ServerStatus, TransportType

        config = McpServerConfig(
            name="github",
            transport_type=TransportType.STDIO,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_TOKEN": "test"},
        )

        info = McpServerInfo(
            name="github",
            config=config,
            status=ServerStatus.DISCONNECTED,
        )

        assert info.name == "github"
        assert info.status == ServerStatus.DISCONNECTED
        assert info.tools == []
        assert info.resources == []
        assert info.prompts == []

    def test_server_status_enum(self):
        """测试服务器状态枚举"""
        from scripts.mcp import ServerStatus

        assert ServerStatus.DISCONNECTED.value == "disconnected"
        assert ServerStatus.CONNECTING.value == "connecting"
        assert ServerStatus.CONNECTED.value == "connected"
        assert ServerStatus.ERROR.value == "error"


class TestMCPConfig:
    """MCP 配置测试"""

    def test_load_empty_config(self):
        """测试加载空配置"""
        from scripts.mcp import load_mcp_config

        config = load_mcp_config(None)
        assert config.servers == {}

    def test_load_invalid_config_path(self):
        """测试加载无效配置路径"""
        from scripts.mcp import load_mcp_config

        # 无效路径应该抛出异常
        with pytest.raises(Exception):
            load_mcp_config("/nonexistent/path.json")

    def test_validate_config(self):
        """测试配置验证"""
        from scripts.mcp import McpConfig, McpServerConfig, TransportType, validate_mcp_config

        # 创建一个有效的配置
        server_config = McpServerConfig(
            name="github",
            transport_type=TransportType.STDIO,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
        )

        config = McpConfig()
        config.servers["github"] = server_config

        errors = validate_mcp_config(config)
        assert len(errors) == 0

    def test_validate_config_missing_command(self):
        """测试缺少 command 的配置验证"""
        from scripts.mcp import McpConfig, McpServerConfig, TransportType, validate_mcp_config

        # 创建一个缺少 command 的配置
        invalid_config = McpServerConfig(
            name="github",
            transport_type=TransportType.STDIO,
            command="",
            args=["-y", "@modelcontextprotocol/server-github"],
        )

        config = McpConfig()
        config.servers["github"] = invalid_config

        errors = validate_mcp_config(config)
        assert len(errors) > 0
