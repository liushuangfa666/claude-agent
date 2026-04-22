"""
MCP 配置加载和验证

支持从 .mcp.json 文件加载服务器配置。
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .mcp_types import McpServerConfig, TransportType

logger = logging.getLogger(__name__)


class McpConfigError(Exception):
    """MCP 配置错误"""
    pass


@dataclass
class McpConfig:
    """MCP 配置"""
    mcp_version: str = "1.0"
    servers: dict[str, McpServerConfig] = field(default_factory=dict)


def find_mcp_config_file() -> Path | None:
    """查找 MCP 配置文件"""
    candidates = [
        Path.cwd() / ".mcp.json",
        Path.cwd() / ".mcp" / ".mcp.json",
        Path.home() / ".mcp.json",
        Path.home() / ".config" / "mcp" / "servers.json",
    ]

    env_path = os.environ.get("MCP_SERVERS_CONFIG")
    if env_path:
        candidates.insert(0, Path(env_path))

    for path in candidates:
        if path.exists():
            return path

    return None


def load_mcp_config(config_path: str | Path | None = None) -> McpConfig:
    """加载 MCP 配置"""
    if config_path is None:
        config_path = find_mcp_config_file()

    if config_path is None:
        return McpConfig()

    config_path = Path(config_path)

    if not config_path.exists():
        raise McpConfigError(f"Config file not found: {config_path}")

    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise McpConfigError(f"Invalid JSON in {config_path}: {e}")

    return parse_mcp_config(data)


def parse_mcp_config(data: dict[str, Any]) -> McpConfig:
    """解析 MCP 配置数据"""
    config = McpConfig()

    config.mcp_version = data.get("mcpVersion", "1.0")

    mcp_servers = data.get("mcpServers", {})

    if not isinstance(mcp_servers, dict):
        raise McpConfigError("mcpServers must be an object")

    for server_name, server_data in mcp_servers.items():
        if not isinstance(server_data, dict):
            raise McpConfigError(f"Server {server_name} config must be an object")

        try:
            config.servers[server_name] = McpServerConfig.from_dict(server_name, server_data)
        except Exception as e:
            raise McpConfigError(f"Invalid config for server {server_name}: {e}")

    return config


def validate_mcp_config(config: McpConfig) -> list[str]:
    """验证 MCP 配置，返回警告列表"""
    warnings: list[str] = []

    for server_name, server_config in config.servers.items():
        if server_config.transport_type == TransportType.STDIO:
            if not server_config.command:
                warnings.append(f"Server {server_name}: stdio type requires 'command' field")

        elif server_config.transport_type in (TransportType.HTTP, TransportType.SSE, TransportType.WEBSOCKET):
            if not server_config.url:
                warnings.append(f"Server {server_name}: {server_config.transport_type.value} type requires 'url' field")

        for var_name, var_value in server_config.env.items():
            if not var_value:
                warnings.append(f"Server {server_name}: Environment variable {var_name} is not set")

    return warnings


def create_sample_config() -> dict[str, Any]:
    """创建示例配置"""
    return {
        "mcpVersion": "1.0",
        "mcpServers": {
            "github": {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
            },
            "filesystem": {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
            },
            "slack": {
                "type": "http",
                "url": "https://api.example.com/mcp",
                "headers": {"Authorization": "Bearer ${SLACK_TOKEN}"},
            },
        },
    }


def save_mcp_config(config: dict[str, Any], config_path: str | Path) -> None:
    """保存 MCP 配置"""
    config_path = Path(config_path)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved MCP config to {config_path}")
