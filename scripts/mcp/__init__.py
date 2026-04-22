"""
MCP (Model Context Protocol) 支持模块

提供对 MCP 服务器的连接管理和工具调用支持。
"""
from .mcp_client import MCPClient, MCPClientProtocol
from .mcp_config import (
    McpConfig,
    McpConfigError,
    load_mcp_config,
    validate_mcp_config,
)
from .mcp_manager import MCPServerManager, get_server_manager
from .mcp_string_utils import (
    format_mcp_tool_name,
    get_server_name_from_tool_name,
    get_tool_name_from_mcp_name,
    parse_mcp_tool_name,
)
from .mcp_tool import MCPTool, MCPToolExecutor
from .mcp_types import (
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    McpCapabilities,
    McpPrompt,
    McpResource,
    McpServerConfig,
    McpServerConfigDict,
    McpServerInfo,
    McpTool,
    ServerStatus,
    TransportType,
)
from .mcp_oauth import (
    MCPOAuthManager,
    OAuthConfig,
    OAuthError,
    OAuthFlow,
    OAuthToken,
    OAuthTokenStore,
    get_oauth_manager,
)

__all__ = [
    # Types
    "McpServerConfig",
    "McpServerConfigDict",
    "McpTool",
    "McpResource",
    "McpPrompt",
    "McpCapabilities",
    "McpServerInfo",
    "ServerStatus",
    "TransportType",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "JsonRpcNotification",
    # Config
    "McpConfig",
    "McpConfigError",
    "load_mcp_config",
    "validate_mcp_config",
    # Client
    "MCPClient",
    "MCPClientProtocol",
    # Manager
    "MCPServerManager",
    "get_server_manager",
    # Tool
    "MCPTool",
    "MCPToolExecutor",
    # Utils
    "format_mcp_tool_name",
    "parse_mcp_tool_name",
    "get_server_name_from_tool_name",
    "get_tool_name_from_mcp_name",
    # OAuth
    "MCPOAuthManager",
    "OAuthConfig",
    "OAuthError",
    "OAuthFlow",
    "OAuthToken",
    "OAuthTokenStore",
    "get_oauth_manager",
]
