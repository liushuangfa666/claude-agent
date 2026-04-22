"""
MCP 工具实现

将 MCP 工具集成到 Agent 的工具系统中。
"""
from __future__ import annotations

import logging
from typing import Any

from ..tool import BaseTool, ToolResult
from .mcp_manager import MCPServerManager, get_server_manager
from .mcp_string_utils import format_mcp_tool_name

logger = logging.getLogger(__name__)


class MCPTool(BaseTool):
    """MCP 工具包装器
    
    将 MCP 服务器提供的工具包装为 Agent 可调用的 BaseTool。
    """

    def __init__(
        self,
        server_name: str,
        tool_name: str,
        description: str,
        input_schema: dict[str, Any],
    ):
        self._server_name = server_name
        self._tool_name = tool_name
        self._description = description
        self._input_schema = input_schema
        self._full_name = format_mcp_tool_name(server_name, tool_name)

        super().__init__()

    @property
    def name(self) -> str:
        """工具名称"""
        return self._full_name

    @property
    def description(self) -> str:
        """工具描述"""
        return f"[{self._server_name}] {self._description}"

    @property
    def input_schema(self) -> dict[str, Any]:
        """输入 schema"""
        return self._input_schema

    async def call(self, args: dict, context: dict) -> ToolResult:
        """执行 MCP 工具调用"""
        manager = get_server_manager()

        try:
            result = await manager.call_tool(
                self._server_name,
                self._tool_name,
                args,
            )

            if result.get("success", False):
                return ToolResult(
                    success=True,
                    data=result.get("result", {}),
                )
            else:
                return ToolResult(
                    success=False,
                    data=None,
                    error=result.get("error", "Unknown error"),
                )

        except ConnectionError as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"服务器 {self._server_name} 未连接: {e}",
            )
        except Exception as e:
            logger.error(f"MCPTool call failed: {e}")
            return ToolResult(
                success=False,
                data=None,
                error=str(e),
            )

    def is_destructive(self, args: dict) -> bool:
        """MCP 工具默认不标记为危险操作"""
        return False

    def get_activity_description(self, args: dict) -> str:
        """获取活动描述"""
        return f"Calling {self._server_name}/{self._tool_name}"


class MCPToolExecutor:
    """MCP 工具执行器
    
    负责注册和管理所有 MCP 工具。
    """

    def __init__(self, manager: MCPServerManager | None = None):
        self._manager = manager or get_server_manager()
        self._registered_tools: dict[str, MCPTool] = {}

    def register_all_tools(self) -> list[MCPTool]:
        """注册所有 MCP 服务器的工具"""
        from ..tool import get_registry

        self._registered_tools.clear()

        all_tools = self._manager.get_all_tools()

        for mcp_tool in all_tools:
            tool = MCPTool(
                server_name=mcp_tool.server_name,
                tool_name=mcp_tool.name,
                description=mcp_tool.description,
                input_schema=mcp_tool.input_schema,
            )

            self._registered_tools[tool.name] = tool
            get_registry().register(tool)

            logger.debug(f"Registered MCP tool: {tool.name}")

        logger.info(f"MCPToolExecutor: Registered {len(self._registered_tools)} tools")

        return list(self._registered_tools.values())

    def unregister_all_tools(self) -> None:
        """取消注册所有 MCP 工具"""
        from ..tool import get_registry

        for tool_name in list(self._registered_tools.keys()):
            if tool_name in get_registry()._tools:
                del get_registry()._tools[tool_name]

        self._registered_tools.clear()
        logger.info("MCPToolExecutor: Unregistered all tools")

    def get_tool(self, full_name: str) -> MCPTool | None:
        """获取指定工具"""
        return self._registered_tools.get(full_name)

    def get_all_tools(self) -> list[MCPTool]:
        """获取所有已注册的工具"""
        return list(self._registered_tools.values())

    async def refresh_tools(self) -> list[MCPTool]:
        """刷新工具列表"""
        self.unregister_all_tools()
        return self.register_all_tools()

    @property
    def tool_count(self) -> int:
        """工具数量"""
        return len(self._registered_tools)


async def register_mcp_tools(manager: MCPServerManager | None = None) -> list[MCPTool]:
    """注册所有 MCP 工具的便捷函数"""
    executor = MCPToolExecutor(manager)
    return executor.register_all_tools()


async def refresh_mcp_tools() -> list[MCPTool]:
    """刷新 MCP 工具的便捷函数"""
    executor = MCPToolExecutor()
    return await executor.refresh_tools()
