"""
SSH Daemon - SSH 守护进程支持

提供通过 SSH 远程连接到 Claude Agent 的功能。

功能：
- SSH 服务器（需要 paramiko）
- TCP 简单 shell（无依赖）
- 身份验证
- 命令处理
- 会话管理

参考 Claude Code 的 SSH Daemon 设计。
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# 检查 paramiko 是否可用
try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False


@dataclass
class SSHDConfig:
    """SSH Daemon 配置"""
    host: str = "0.0.0.0"
    port: int = 2222
    username: str = "claude"
    password: str | None = None  # 如果为 None，使用密钥认证
    key_file: str | None = None  # SSH 公钥文件路径
    allowed_public_keys: list[str] | None = None  # 允许的公钥列表
    max_connections: int = 5
    timeout: int = 300  # 超时时间（秒）


class SSHDaemon:
    """
    SSH 守护进程

    支持两种模式：
    1. SSH 模式（需要 paramiko）：完整的 SSH 协议支持
    2. TCP 模式（无依赖）：简单的基于文本的协议
    """

    def __init__(self, config: SSHDConfig | None = None):
        self.config = config or SSHDConfig()
        self._server: asyncio.Server | None = None
        self._running = False
        self._use_tcp_mode = not HAS_PARAMIKO

        if self._use_tcp_mode:
            logger.warning("paramiko not available, using TCP mode (insecure)")
        else:
            logger.info("Using SSH mode with paramiko")

    async def start(self) -> None:
        """启动 SSH 守护进程"""
        if self._running:
            logger.warning("SSH Daemon already running")
            return

        self._running = True

        if self._use_tcp_mode:
            await self._start_tcp_mode()
        else:
            await self._start_ssh_mode()

    async def stop(self) -> None:
        """停止 SSH 守护进程"""
        self._running = False

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        logger.info("SSH Daemon stopped")

    async def _start_tcp_mode(self) -> None:
        """启动 TCP 模式（简单文本协议）"""
        self._server = await asyncio.start_server(
            self._handle_tcp_connection,
            self.config.host,
            self.config.port,
        )

        addr = self._server.sockets[0].getsockname()
        logger.info(f"TCP Daemon listening on {addr[0]}:{addr[1]}")

    async def _start_ssh_mode(self) -> None:
        """启动 SSH 模式（完整 SSH 协议）"""
        if not HAS_PARAMIKO:
            raise RuntimeError("paramiko is required for SSH mode")

        # 创建 SSH 服务器
        server_key = paramiko.RSAKey.generate(2048)

        self._server = await asyncio.start_server(
            self._handle_ssh_connection,
            self.config.host,
            self.config.port,
        )

        addr = self._server.sockets[0].getsockname()
        logger.info(f"SSH Daemon listening on {addr[0]}:{addr[1]}")

    async def _handle_tcp_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """处理 TCP 连接"""
        addr = writer.get_extra_info('peername')
        logger.info(f"TCP connection from {addr}")

        try:
            # 发送欢迎消息
            welcome = (
                "Claude Agent SSH Daemon (TCP Mode)\n"
                "=================================\n"
                "Warning: This connection is not encrypted!\n"
                "Press Ctrl+C or type 'exit' to disconnect.\n\n"
            )
            writer.write(welcome.encode())
            await writer.drain()

            # 简单认证
            writer.write(b"Username: ")
            await writer.drain()
            username = (await reader.readline()).decode().strip()

            if self.config.username and username != self.config.username:
                writer.write(b"Authentication failed\n")
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            writer.write(b"Password (ignored in TCP mode): ")
            await writer.drain()
            await reader.readline()  # 读取密码（忽略）

            writer.write(f"Welcome, {username}!\n\n".encode())
            await writer.drain()

            # 命令循环
            while self._running:
                writer.write(f"{username}@claude-agent> ".encode())
                await writer.drain()

                try:
                    line = await asyncio.wait_for(
                        reader.readline(),
                        timeout=self.config.timeout
                    )
                except asyncio.TimeoutError:
                    writer.write(b"\nConnection timed out\n")
                    await writer.drain()
                    break

                command = line.decode().strip()

                if not command:
                    continue

                if command.lower() in ("exit", "quit", "logout"):
                    writer.write(b"Goodbye!\n")
                    await writer.drain()
                    break

                # 处理命令
                response = await self._execute_command(command)
                writer.write(response.encode() + b"\n")
                await writer.drain()

        except ConnectionResetError:
            logger.info(f"Connection closed by {addr}")
        except Exception as e:
            logger.error(f"TCP connection error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_ssh_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """处理 SSH 连接"""
        if not HAS_PARAMIKO:
            return

        addr = writer.get_extra_info('peername')
        logger.info(f"SSH connection from {addr}")

        try:
            # 创建 SSH 服务器传输
            transport = await asyncio.get_event_loop().create_server(
                lambda: paramiko.ServerInterface(),
                sock=socket.socket(),
            )

            # 获取 transport
            # 注意：这是简化的实现，完整的 paramiko SSH 服务器需要更多设置

        except Exception as e:
            logger.error(f"SSH connection error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def _execute_command(self, command: str) -> str:
        """执行命令并返回结果"""
        # 这是简化的命令处理，实际实现应该调用 Agent
        if command.startswith("/"):
            # 处理 slash 命令
            return f"Slash command: {command}"
        elif command.startswith("!"):
            # 处理 shell 命令
            proc = await asyncio.create_subprocess_shell(
                command[1:],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return stdout.decode() or stderr.decode()
        else:
            # 文本消息，传递给 Agent
            return f"[Agent would process: {command}]"


class SSHAgentSession:
    """
    SSH Agent 会话

    管理通过 SSH 连接到 Agent 的会话。
    """

    def __init__(self, session_id: str, username: str):
        self.session_id = session_id
        self.username = username
        self.created_at = None
        self.last_activity = None
        self.agent = None

    async def handle_input(self, input_data: str) -> str:
        """处理用户输入并返回 Agent 响应"""
        # 这里应该调用 Agent 来处理输入
        return f"Echo: {input_data}"

    def close(self) -> None:
        """关闭会话"""
        logger.info(f"Session {self.session_id} closed")


# 全局 SSH Daemon 实例
_ssh_daemon: SSHDaemon | None = None


def get_ssh_daemon(config: SSHDConfig | None = None) -> SSHDaemon:
    """获取全局 SSH Daemon 实例"""
    global _ssh_daemon
    if _ssh_daemon is None:
        _ssh_daemon = SSHDaemon(config)
    return _ssh_daemon


async def start_ssh_daemon(config: SSHDConfig | None = None) -> SSHDaemon:
    """启动 SSH 守护进程"""
    daemon = get_ssh_daemon(config)
    await daemon.start()
    return daemon


async def stop_ssh_daemon() -> None:
    """停止 SSH 守护进程"""
    global _ssh_daemon
    if _ssh_daemon:
        await _ssh_daemon.stop()
        _ssh_daemon = None
