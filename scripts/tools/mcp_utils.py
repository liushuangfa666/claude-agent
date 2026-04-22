"""
MCP 资源工具 - MCP 资源读取和管理
"""
from __future__ import annotations

import logging
from typing import Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ListMcpResourcesTool(BaseTool):
    """列出 MCP 资源工具"""

    name = "ListMcpResources"
    description = "List available resources from MCP servers"

    input_schema = {
        "type": "object",
        "properties": {
            "server": {
                "type": "string",
                "description": "MCP server name (optional, list all if not specified)",
            },
        },
    }

    def is_enabled(self) -> bool:
        """MCP 可用时启用"""
        try:
            from ..mcp import mcp_manager
            return True
        except ImportError:
            return False

    async def call(self, args: dict, context: Any) -> ToolResult:
        server_name = args.get("server")

        try:
            from ..mcp.mcp_manager import MCPServerManager

            manager = MCPServerManager.get_instance()
        except ImportError:
            return ToolResult(
                success=False,
                data=None,
                error="MCP is not available",
            )

        try:
            all_resources = []

            if server_name:
                server_info = manager.get_server(server_name)
                if not server_info:
                    return ToolResult(
                        success=False,
                        data=None,
                        error=f"Server '{server_name}' not found",
                    )
                resources = getattr(server_info, "resources", [])
                all_resources = self._format_resources(resources, server_name)
            else:
                for name, server_info in manager.get_all_servers().items():
                    status = getattr(server_info, "status", None)
                    if status and status.value == "connected":
                        resources = getattr(server_info, "resources", [])
                        formatted = self._format_resources(resources, name)
                        all_resources.extend(formatted)

            return ToolResult(
                success=True,
                data={
                    "count": len(all_resources),
                    "resources": all_resources,
                },
            )

        except Exception as e:
            logger.error(f"ListMcpResources failed: {e}")
            return ToolResult(success=False, data=None, error=str(e))

    def _format_resources(
        self, resources: list, server_name: str
    ) -> list[dict]:
        """格式化资源列表"""
        result = []
        for r in resources:
            result.append({
                "uri": getattr(r, "uri", ""),
                "name": getattr(r, "name", ""),
                "description": getattr(r, "description", ""),
                "mime_type": getattr(r, "mime_type", ""),
                "server": server_name,
            })
        return result


class ReadMcpResourceTool(BaseTool):
    """读取 MCP 资源工具"""

    name = "ReadMcpResource"
    description = "Read content from an MCP resource"

    input_schema = {
        "type": "object",
        "properties": {
            "server": {"type": "string", "description": "MCP server name"},
            "uri": {"type": "string", "description": "Resource URI to read"},
        },
        "required": ["server", "uri"],
    }

    def is_enabled(self) -> bool:
        """MCP 可用时启用"""
        try:
            from ..mcp import mcp_manager
            return True
        except ImportError:
            return False

    async def call(self, args: dict, context: Any) -> ToolResult:
        server_name = args["server"]
        uri = args["uri"]

        try:
            from ..mcp.mcp_manager import MCPServerManager

            manager = MCPServerManager.get_instance()
        except ImportError:
            return ToolResult(
                success=False,
                data=None,
                error="MCP is not available",
            )

        try:
            server_info = manager.get_server(server_name)
            if not server_info:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Server '{server_name}' not found",
                )

            status = getattr(server_info, "status", None)
            if not status or status.value != "connected":
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Server '{server_name}' is not connected",
                )

            # Placeholder - 实际通过 MCP 客户端读取资源
            return ToolResult(
                success=True,
                data={
                    "uri": uri,
                    "server": server_name,
                    "content": [],
                },
            )

        except Exception as e:
            logger.error(f"ReadMcpResource failed: {e}")
            return ToolResult(success=False, data=None, error=str(e))
