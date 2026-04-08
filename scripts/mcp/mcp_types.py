"""
MCP 类型定义

定义 MCP 协议中使用的数据结构。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict


class TransportType(str, Enum):
    """传输类型枚举"""
    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"
    WEBSOCKET = "websocket"


class ServerStatus(str, Enum):
    """服务器状态枚举"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class McpServerConfigDict(TypedDict, total=False):
    """MCP 服务器配置的字典类型（用于 JSON 反序列化）"""
    type: str
    command: str
    args: list[str]
    env: dict[str, str]
    url: str
    headers: dict[str, str]
    timeout: int


@dataclass
class McpServerConfig:
    """MCP 服务器配置"""
    name: str
    transport_type: TransportType
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    timeout: int = 30

    @classmethod
    def from_dict(cls, name: str, config: McpServerConfigDict) -> McpServerConfig:
        """从字典创建配置"""
        transport_type = TransportType(config.get("type", "stdio"))

        # 环境变量替换：${VAR} -> os.environ.get(VAR, "")
        env: dict[str, str] = {}
        for key, value in config.get("env", {}).items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                var_name = value[2:-1]
                env[key] = os.environ.get(var_name, "")
            else:
                env[key] = str(value)

        return cls(
            name=name,
            transport_type=transport_type,
            command=config.get("command"),
            args=list(config.get("args", [])),
            env=env,
            url=config.get("url"),
            headers=dict(config.get("headers", {})),
            timeout=config.get("timeout", 30),
        )

    def to_transport_dict(self) -> dict[str, Any]:
        """转换为传输层配置字典"""
        result: dict[str, Any] = {"type": self.transport_type.value}
        if self.command:
            result["command"] = self.command
        if self.args:
            result["args"] = self.args
        if self.env:
            result["env"] = self.env
        if self.url:
            result["url"] = self.url
        if self.headers:
            result["headers"] = self.headers
        result["timeout"] = self.timeout
        return result


@dataclass
class McpTool:
    """MCP 工具定义"""
    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str

    @property
    def full_name(self) -> str:
        """获取完整名称，格式为 mcp__server__tool"""
        return f"mcp__{self.server_name}__{self.name}"

    def to_tool_definition(self) -> dict[str, Any]:
        """转换为 Agent 工具定义格式"""
        return {
            "name": self.full_name,
            "description": f"[{self.server_name}] {self.description}",
            "input_schema": self.input_schema,
        }


@dataclass
class McpResource:
    """MCP 资源定义"""
    uri: str
    name: str
    description: str | None
    mime_type: str | None
    server_name: str


@dataclass
class McpPrompt:
    """MCP 提示定义"""
    name: str
    description: str | None
    arguments: list[dict[str, Any]]
    server_name: str


@dataclass
class McpCapabilities:
    """MCP 服务器能力"""
    tools: bool = False
    resources: bool = False
    prompts: bool = False
    logging: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> McpCapabilities:
        """从 JSON-RPC 响应创建能力对象"""
        return cls(
            tools=bool(data.get("tools")),
            resources=bool(data.get("resources")),
            prompts=bool(data.get("prompts")),
            logging=bool(data.get("logging")),
        )


@dataclass
class McpServerInfo:
    """已连接的 MCP 服务器信息"""
    name: str
    config: McpServerConfig
    status: ServerStatus
    capabilities: McpCapabilities | None = None
    tools: list[McpTool] = field(default_factory=list)
    resources: list[McpResource] = field(default_factory=list)
    prompts: list[McpPrompt] = field(default_factory=list)
    error_message: str | None = None


class JsonRpcRequest:
    """JSON-RPC 2.0 请求"""
    def __init__(
        self,
        method: str,
        params: dict[str, Any] | list[Any] | None = None,
        request_id: int | str | None = None,
    ):
        self.jsonrpc = "2.0"
        self.method = method
        self.params = params
        self.id = request_id

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params is not None:
            result["params"] = self.params
        if self.id is not None:
            result["id"] = self.id
        return result


class JsonRpcResponse:
    """JSON-RPC 2.0 响应"""
    def __init__(
        self,
        result: Any = None,
        error: dict[str, Any] | None = None,
        response_id: int | str | None = None,
    ):
        self.jsonrpc = "2.0"
        self.result = result
        self.error = error
        self.id = response_id

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JsonRpcResponse:
        """从字典创建响应对象"""
        return cls(
            result=data.get("result"),
            error=data.get("error"),
            response_id=data.get("id"),
        )

    @property
    def is_error(self) -> bool:
        return self.error is not None


class JsonRpcNotification:
    """JSON-RPC 2.0 通知（无响应）"""
    def __init__(self, method: str, params: dict[str, Any] | list[Any] | None = None):
        self.jsonrpc = "2.0"
        self.method = method
        self.params = params

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JsonRpcNotification:
        """从字典创建通知"""
        return cls(
            method=data.get("method", ""),
            params=data.get("params"),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.params is not None:
            result["params"] = self.params
        return result
