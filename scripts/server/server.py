"""
Server - HTTP/WebSocket 服务器

基于 aiohttp 的异步服务器，提供 REST API 和 WebSocket 端点
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Callable

try:
    from aiohttp import web
except ImportError:
    raise ImportError("aiohttp is required for Server. Install with: pip install aiohttp")

from .lockfile import Lockfile
from .session import Session, SessionManager

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


class Server:
    """
    HTTP + WebSocket 服务器

    提供 REST API 和 WebSocket 端点用于与 Agent 交互

    Attributes:
        host: 监听地址
        port: 监听端口
        on_chat: 聊天回调函数
        app: aiohttp Application
        session_manager: 会话管理器
        lockfile: 进程锁
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 18780,
        on_chat: "Callable[..., Any] | None" = None,
    ) -> None:
        """
        初始化服务器

        Args:
            host: 监听地址，默认 0.0.0.0
            port: 监听端口，默认 18780
            on_chat: 聊天消息回调函数
        """
        self.host = host
        self.port = port
        self.on_chat = on_chat

        self.app: "web.Application" = web.Application()
        self.runner: "web.AppRunner | None" = None
        self.site: "web.TCPSite | None" = None

        self.session_manager: SessionManager = SessionManager()
        self.lockfile: Lockfile = Lockfile()

        self._setup_routes()
        self._setup_websocket()
        self._running = False

    def _setup_routes(self) -> None:
        """设置 REST API 路由"""
        self.app.router.add_post("/api/chat", self.handle_chat)
        self.app.router.add_get("/api/status", self.handle_status)
        self.app.router.add_get("/api/stats", self.handle_stats)
        self.app.router.add_post("/api/session", self.handle_session)
        self.app.router.add_get("/api/sessions", self.handle_sessions)
        self.app.router.add_get("/api/history", self.handle_history)
        self.app.router.add_get("/api/usage", self.handle_usage)

    def _setup_websocket(self) -> None:
        """设置 WebSocket 端点"""
        self.app.router.add_get("/ws", self.handle_websocket)

    async def start(self) -> None:
        """启动服务器"""
        if not self.lockfile.acquire():
            raise RuntimeError("Another instance is running")

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        self._running = True
        logger.info(f"Server started on {self.host}:{self.port}")

    async def stop(self) -> None:
        """停止服务器"""
        self._running = False

        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

        self.lockfile.release()
        logger.info("Server stopped")

    async def handle_chat(self, request: "web.Request") -> "web.Response":
        """
        处理聊天请求

        POST /api/chat
        Body: {"session_id": str, "message": str, "stream": bool}
        """
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        session_id = data.get("session_id", "")
        message = data.get("message", "")
        stream = data.get("stream", False)

        if not message:
            return web.json_response({"error": "Missing message"}, status=400)

        session = self.session_manager.get_or_create(session_id)

        if stream:
            return await self._handle_stream(request, session, message)
        else:
            result = await self._process_message(session, message)
            return web.json_response(result)

    async def _handle_stream(
        self,
        request: "web.Request",
        session: Session,
        message: str,
    ) -> "web.WebSocketResponse":
        """
        处理流式响应

        Args:
            request: HTTP 请求
            session: Session 实例
            message: 用户消息

        Returns:
            WebSocket 响应
        """
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        async for event in session.stream_message(message):
            await ws.send_json(event)

        await ws.close()
        return ws

    async def _process_message(
        self, session: Session, message: str
    ) -> dict[str, Any]:
        """
        处理消息

        Args:
            session: Session 实例
            message: 用户消息

        Returns:
            处理结果字典
        """
        response = await session.process_message(message)
        return {"response": response}

    async def handle_status(self, request: "web.Request") -> "web.Response":
        """
        状态检查端点

        GET /api/status
        """
        return web.json_response({
            "status": "ok" if self._running else "stopped",
            "sessions": self.session_manager.count(),
        })

    async def handle_stats(self, request: "web.Request") -> "web.Response":
        """
        统计信息端点

        GET /api/stats
        """
        return web.json_response(self.session_manager.get_stats())

    async def handle_session(self, request: "web.Request") -> "web.Response":
        """
        会话管理端点

        POST /api/session
        Body: {"action": "create"|"get", "session_id": str}
        """
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        action = data.get("action", "get")

        if action == "create":
            session = self.session_manager.create()
            return web.json_response({"session_id": session.id})
        elif action == "get":
            session_id = data.get("session_id")
            session = self.session_manager.get(session_id)
            if session:
                return web.json_response(session.to_dict())
            return web.json_response({"error": "Not found"}, status=404)
        elif action == "delete":
            session_id = data.get("session_id")
            if self.session_manager.delete(session_id):
                return web.json_response({"status": "deleted"})
            return web.json_response({"error": "Not found"}, status=404)

        return web.json_response({"error": "Invalid action"}, status=400)

    async def handle_sessions(self, request: "web.Request") -> "web.Response":
        """
        列出所有会话

        GET /api/sessions
        """
        sessions = self.session_manager.list()
        return web.json_response({"sessions": sessions})

    async def handle_history(self, request: "web.Request") -> "web.Response":
        """
        对话历史端点

        GET /api/history?session_id=xxx&limit=50
        """
        session_id = request.query.get("session_id")
        limit = int(request.query.get("limit", 50))

        if not session_id:
            return web.json_response({"error": "Missing session_id"}, status=400)

        session = self.session_manager.get(session_id)
        if not session:
            return web.json_response({"error": "Not found"}, status=404)

        return web.json_response({
            "history": session.get_history(limit),
        })

    async def handle_usage(self, request: "web.Request") -> "web.Response":
        """
        使用统计端点

        GET /api/usage?session_id=xxx
        """
        session_id = request.query.get("session_id")

        if session_id:
            session = self.session_manager.get(session_id)
            if not session:
                return web.json_response({"error": "Not found"}, status=404)
            return web.json_response(session.get_usage())

        return web.json_response(self.session_manager.get_usage())

    async def handle_websocket(self, request: "web.Request") -> "web.WebSocketResponse":
        """
        WebSocket 连接端点

        GET /ws?session_id=xxx

        支持的消息类型:
        - {"type": "chat", "message": "..."} - 发送聊天消息
        - {"type": "ping"} - 心跳检测
        """
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        session_id = request.query.get("session_id", "")
        session = self.session_manager.get_or_create(session_id)

        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "error": "Invalid JSON"})
                    continue

                event_type = data.get("type")

                if event_type == "chat":
                    message = data.get("message", "")
                    async for event in session.stream_message(message):
                        await ws.send_json(event)
                elif event_type == "ping":
                    await ws.send_json({"type": "pong"})
                else:
                    await ws.send_json({
                        "type": "error",
                        "error": f"Unknown event type: {event_type}",
                    })
            elif msg.type == web.WSMsgType.ERROR:
                logger.error(f"WebSocket error: {ws.exception()}")

        return ws


async def run_server(
    host: str = "0.0.0.0",
    port: int = 18780,
) -> None:
    """
    运行服务器的便捷函数

    Args:
        host: 监听地址
        port: 监听端口
    """
    server = Server(host=host, port=port)

    try:
        await server.start()
        while server._running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await server.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_server())
