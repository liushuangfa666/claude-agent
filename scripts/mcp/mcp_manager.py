"""
MCP 服务器管理器

管理多个 MCP 服务器的连接生命周期。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from .mcp_client import MCPClient, create_transport
from .mcp_config import McpConfig, load_mcp_config
from .mcp_types import McpServerInfo, McpTool, ServerStatus

logger = logging.getLogger(__name__)


class MCPServerManager:
    """MCP 服务器管理器"""

    def __init__(self):
        self._servers: dict[str, McpServerInfo] = {}
        self._clients: dict[str, MCPClient] = {}
        self._lock = asyncio.Lock()
        self._config: McpConfig | None = None

    async def load_config(self, config_path: str | None = None) -> McpConfig:
        """加载 MCP 配置"""
        self._config = load_mcp_config(config_path)

        for server_name, server_config in self._config.servers.items():
            self._servers[server_name] = McpServerInfo(
                name=server_name,
                config=server_config,
                status=ServerStatus.DISCONNECTED,
            )

        logger.info(f"MCPServerManager: Loaded {len(self._servers)} server configs")
        return self._config

    async def connect_server(self, server_name: str) -> McpServerInfo:
        """连接到指定服务器"""
        async with self._lock:
            if server_name not in self._servers:
                raise ValueError(f"Unknown server: {server_name}")

            server_info = self._servers[server_name]

            if server_info.status == ServerStatus.CONNECTED:
                return server_info

            server_info.status = ServerStatus.CONNECTING

            try:
                client = MCPClient(name=f"crush-{server_name}")
                transport = create_transport(server_info.config.to_transport_dict())

                await client.connect(transport)
                capabilities = await client.initialize()

                tools = await client.list_tools()
                for tool in tools:
                    tool.server_name = server_name

                resources = await client.list_resources()
                for resource in resources:
                    resource.server_name = server_name

                prompts = await client.list_prompts()
                for prompt in prompts:
                    prompt.server_name = server_name

                server_info.status = ServerStatus.CONNECTED
                server_info.capabilities = capabilities
                server_info.tools = tools
                server_info.resources = resources
                server_info.prompts = prompts
                server_info.error_message = None

                self._clients[server_name] = client

                logger.info(f"MCPServerManager: Connected to {server_name} with {len(tools)} tools")

                return server_info

            except Exception as e:
                server_info.status = ServerStatus.ERROR
                server_info.error_message = str(e)
                logger.error(f"MCPServerManager: Failed to connect to {server_name}: {e}")
                raise

    async def disconnect_server(self, server_name: str) -> None:
        """断开指定服务器连接"""
        async with self._lock:
            if server_name not in self._servers:
                return

            server_info = self._servers[server_name]

            if server_name in self._clients:
                client = self._clients.pop(server_name)
                await client.close()

            server_info.status = ServerStatus.DISCONNECTED
            server_info.capabilities = None
            server_info.tools = []
            server_info.resources = []
            server_info.prompts = []

            logger.info(f"MCPServerManager: Disconnected from {server_name}")

    async def reconnect_server(self, server_name: str) -> McpServerInfo:
        """重新连接服务器"""
        await self.disconnect_server(server_name)
        return await self.connect_server(server_name)

    async def connect_all(self) -> dict[str, McpServerInfo]:
        """连接所有配置的服务器"""
        results = {}
        for server_name in self._servers:
            try:
                results[server_name] = await self.connect_server(server_name)
            except Exception as e:
                logger.error(f"Failed to connect to {server_name}: {e}")
                results[server_name] = self._servers[server_name]
        return results

    async def disconnect_all(self) -> None:
        """断开所有服务器连接"""
        for server_name in list(self._clients.keys()):
            await self.disconnect_server(server_name)

    def get_server(self, server_name: str) -> McpServerInfo | None:
        """获取服务器信息"""
        return self._servers.get(server_name)

    def get_all_servers(self) -> dict[str, McpServerInfo]:
        """获取所有服务器信息"""
        return dict(self._servers)

    def get_connected_servers(self) -> dict[str, McpServerInfo]:
        """获取已连接的服务器"""
        return {
            name: info
            for name, info in self._servers.items()
            if info.status == ServerStatus.CONNECTED
        }

    def get_all_tools(self) -> list[McpTool]:
        """获取所有服务器的可用工具"""
        tools = []
        for server_info in self._servers.values():
            if server_info.status == ServerStatus.CONNECTED:
                tools.extend(server_info.tools)
        return tools

    def get_tool(self, server_name: str, tool_name: str) -> McpTool | None:
        """获取指定工具"""
        server_info = self._servers.get(server_name)
        if not server_info:
            return None
        for tool in server_info.tools:
            if tool.name == tool_name:
                return tool
        return None

    def get_tool_by_full_name(self, full_name: str) -> tuple[str, McpTool] | None:
        """通过完整名称获取工具，格式为 mcp__server__tool"""
        parts = full_name.split("__")
        if len(parts) != 3 or parts[0] != "mcp":
            return None

        server_name = parts[1]
        tool_name = parts[2]

        tool = self.get_tool(server_name, tool_name)
        if tool:
            return (server_name, tool)
        return None

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """调用服务器上的工具"""
        if server_name not in self._clients:
            raise ConnectionError(f"Not connected to {server_name}")

        client = self._clients[server_name]
        return await client.call_tool(tool_name, arguments)

    @asynccontextmanager
    async def server_context(self, server_name: str) -> AsyncGenerator[McpServerInfo, None]:
        """服务器连接上下文管理器"""
        await self.connect_server(server_name)
        try:
            yield self._servers[server_name]
        finally:
            await self.disconnect_server(server_name)

    @property
    def config(self) -> McpConfig | None:
        """获取配置"""
        return self._config


_server_manager: MCPServerManager | None = None


def get_server_manager() -> MCPServerManager:
    """获取全局服务器管理器实例"""
    global _server_manager
    if _server_manager is None:
        _server_manager = MCPServerManager()
    return _server_manager


async def initialize_mcp(config_path: str | None = None) -> MCPServerManager:
    """初始化 MCP 系统"""
    manager = get_server_manager()
    await manager.load_config(config_path)
    await manager.connect_all()
    return manager


async def shutdown_mcp() -> None:
    """关闭 MCP 系统"""
    global _server_manager
    if _server_manager:
        await _server_manager.disconnect_all()
        _server_manager = None
