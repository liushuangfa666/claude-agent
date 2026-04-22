"""
MCP 客户端实现

支持多种传输层实现：
- StdioTransport: 本地进程 (subprocess)
- SSETransport: Server-Sent Events
- HTTPTransport: Streamable HTTP
- WebSocketTransport: WebSocket
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

from .mcp_types import (
    JsonRpcNotification,
    JsonRpcRequest,
    JsonRpcResponse,
    McpCapabilities,
    McpPrompt,
    McpResource,
    McpTool,
)

logger = logging.getLogger(__name__)


class Transport(ABC):
    """传输层抽象基类"""

    @abstractmethod
    async def connect(self) -> None:
        """建立连接"""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接"""
        pass

    @abstractmethod
    async def send(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """发送请求并等待响应"""
        pass

    @abstractmethod
    async def send_notification(self, notification: JsonRpcNotification) -> None:
        """发送通知（无响应）"""
        pass

    @abstractmethod
    async def receive(self) -> AsyncGenerator[JsonRpcResponse | JsonRpcNotification, None]:
        """接收消息流"""
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """是否已连接"""
        pass


class StdioTransport(Transport):
    """stdio 传输层 - 通过子进程通信"""

    def __init__(
        self,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
        timeout: int = 30,
    ):
        self.command = command
        self.args = args
        self.env = env or {}
        self.timeout = timeout
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._response_futures: dict[int, asyncio.Future[JsonRpcResponse]] = {}
        self._notification_queue: asyncio.Queue[JsonRpcResponse | JsonRpcNotification] = asyncio.Queue()
        self._reader_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        """启动子进程并建立通信"""
        if self._process is not None:
            return

        full_env = {**dict(os.environ), **self.env}

        self._process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            env=full_env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        self._reader_task = asyncio.create_task(self._read_loop())

        logger.info(f"StdioTransport: Started process {self.command}")

    async def disconnect(self) -> None:
        """终止子进程"""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
            self._process = None

        for future in self._response_futures.values():
            future.cancel()
        self._response_futures.clear()

        logger.info("StdioTransport: Disconnected")

    async def send(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """发送请求并等待响应"""
        if not self._process or self._process.stdin is None:
            raise ConnectionError("Not connected")

        async with self._lock:
            self._request_id += 1
            request.id = self._request_id

        future: asyncio.Future[JsonRpcResponse] = asyncio.Future()
        self._response_futures[self._request_id] = future

        try:
            data = json.dumps(request.to_dict())
            self._process.stdin.write((data + "\n").encode())
            await self._process.stdin.drain()

            response = await asyncio.wait_for(future, timeout=self.timeout)
            return response
        except asyncio.TimeoutError:
            raise TimeoutError(f"Request {request.method} timed out after {self.timeout}s")
        finally:
            self._response_futures.pop(self._request_id, None)

    async def send_notification(self, notification: JsonRpcNotification) -> None:
        """发送通知"""
        if not self._process or self._process.stdin is None:
            raise ConnectionError("Not connected")

        data = json.dumps(notification.to_dict())
        self._process.stdin.write((data + "\n").encode())
        await self._process.stdin.drain()

    async def receive(self) -> AsyncGenerator[JsonRpcResponse | JsonRpcNotification, None]:
        """接收消息流"""
        while True:
            try:
                message = await self._notification_queue.get()
                yield message
            except asyncio.CancelledError:
                break

    async def _read_loop(self) -> None:
        """持续读取子进程输出"""
        if not self._process or not self._process.stdout:
            return

        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break

                try:
                    data = json.loads(line.decode().strip())
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON: {e}, line: {line}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Read loop error: {e}")

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """处理接收到的消息"""
        msg_id = data.get("id")

        # 有 id 的是 response（需要匹配 future）
        if msg_id is not None:
            if data.get("result") is not None or data.get("error") is not None:
                response = JsonRpcResponse.from_dict(data)
                if isinstance(msg_id, int) and msg_id in self._response_futures:
                    future = self._response_futures.pop(msg_id)
                    if not future.done():
                        future.set_result(response)
                else:
                    # 找不到对应的 future，记录警告
                    logger.warning(f"Received response with unknown id {msg_id}")
            return

        # 没有 id 且有 method 的是 notification
        if "method" in data:
            notification = JsonRpcNotification.from_dict(data)
            await self._notification_queue.put(notification)

    @property
    def is_connected(self) -> bool:
        return self._process is not None and self._process.returncode is None


class SSETransport(Transport):
    """SSE (Server-Sent Events) 传输层"""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
    ):
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self._session: Any = None
        self._event_queue: asyncio.Queue[JsonRpcResponse | JsonRpcNotification] = asyncio.Queue()
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._reader_task: asyncio.Task[None] | None = None
        self._connected = False

    async def connect(self) -> None:
        """建立 SSE 连接"""
        try:
            import aiohttp
        except ImportError:
            raise ImportError("aiohttp is required for SSE transport: pip install aiohttp")

        self._session = aiohttp.ClientSession(headers=self.headers)
        self._connected = True
        self._reader_task = asyncio.create_task(self._sse_loop())

        logger.info(f"SSETransport: Connected to {self.url}")

    async def disconnect(self) -> None:
        """断开 SSE 连接"""
        self._connected = False

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._session:
            await self._session.close()
            self._session = None

        logger.info("SSETransport: Disconnected")

    async def send(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """发送请求"""
        if not self._session:
            raise ConnectionError("Not connected")

        async with self._lock:
            self._request_id += 1
            request.id = self._request_id

        try:
            import aiohttp
            async with self._session.post(
                self.url,
                json=request.to_dict(),
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                data = await response.json()
                return JsonRpcResponse.from_dict(data)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Request {request.method} timed out")

    async def send_notification(self, notification: JsonRpcNotification) -> None:
        """发送通知"""
        if not self._session:
            raise ConnectionError("Not connected")

        import aiohttp
        async with self._session.post(
            self.url,
            json=notification.to_dict(),
            timeout=aiohttp.ClientTimeout(total=self.timeout),
        ):
            pass

    async def receive(self) -> AsyncGenerator[JsonRpcResponse | JsonRpcNotification, None]:
        """接收 SSE 事件流"""
        while self._connected:
            try:
                message = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                yield message
            except asyncio.TimeoutError:
                continue

    async def _sse_loop(self) -> None:
        """SSE 事件循环"""
        if not self._session:
            return

        try:
            async with self._session.get(
                self.url,
                headers={**self.headers, "Accept": "text/event-stream"},
            ) as response:
                async for line in response.content:
                    if not self._connected:
                        break

                    line = line.decode().strip()
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data:
                            try:
                                parsed = json.loads(data)
                                if "method" in parsed:
                                    await self._event_queue.put(JsonRpcNotification(method=parsed["method"], params=parsed.get("params")))
                                else:
                                    await self._event_queue.put(JsonRpcResponse.from_dict(parsed))
                            except json.JSONDecodeError:
                                pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"SSE loop error: {e}")

    @property
    def is_connected(self) -> bool:
        return self._connected and self._session is not None


class HTTPTransport(Transport):
    """HTTP 传输层 (Streamable HTTP)"""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
    ):
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self._session: Any = None
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._connected = False

    async def connect(self) -> None:
        """建立 HTTP 连接"""
        try:
            import aiohttp
        except ImportError:
            raise ImportError("aiohttp is required for HTTP transport: pip install aiohttp")

        self._session = aiohttp.ClientSession(headers=self.headers)
        self._connected = True
        logger.info(f"HTTPTransport: Connected to {self.url}")

    async def disconnect(self) -> None:
        """断开 HTTP 连接"""
        self._connected = False
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("HTTPTransport: Disconnected")

    async def send(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """发送请求"""
        if not self._session:
            raise ConnectionError("Not connected")

        async with self._lock:
            self._request_id += 1
            request.id = self._request_id

        try:
            import aiohttp
            async with self._session.post(
                self.url,
                json=request.to_dict(),
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as response:
                data = await response.json()
                return JsonRpcResponse.from_dict(data)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Request {request.method} timed out")

    async def send_notification(self, notification: JsonRpcNotification) -> None:
        """发送通知"""
        if not self._session:
            raise ConnectionError("Not connected")

        import aiohttp
        try:
            async with self._session.post(
                self.url,
                json=notification.to_dict(),
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ):
                pass
        except asyncio.TimeoutError:
            raise TimeoutError("Notification timed out")

    async def receive(self) -> AsyncGenerator[JsonRpcResponse | JsonRpcNotification, None]:
        """HTTP 传输不支持接收流"""
        if False:
            yield
        return

    @property
    def is_connected(self) -> bool:
        return self._connected and self._session is not None


class WebSocketTransport(Transport):
    """WebSocket 传输层"""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
    ):
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self._ws: Any = None
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._event_queue: asyncio.Queue[JsonRpcResponse | JsonRpcNotification] = asyncio.Queue()
        self._reader_task: asyncio.Task[None] | None = None
        self._connected = False

    async def connect(self) -> None:
        """建立 WebSocket 连接"""
        try:
            import websockets
        except ImportError:
            raise ImportError("websockets is required for WebSocket transport: pip install websockets")

        async with websockets.connect(self.url, extra_headers=self.headers) as ws:
            self._ws = ws
            self._connected = True
            self._reader_task = asyncio.create_task(self._ws_loop())

            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                pass

    async def disconnect(self) -> None:
        """断开 WebSocket 连接"""
        self._connected = False

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._ws:
            await self._ws.close()
            self._ws = None

        logger.info("WebSocketTransport: Disconnected")

    async def send(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """发送请求并等待响应"""
        if not self._ws:
            raise ConnectionError("Not connected")

        async with self._lock:
            self._request_id += 1
            request.id = self._request_id

        response_future: asyncio.Future[JsonRpcResponse] = asyncio.Future()

        async with self._lock:
            await self._ws.send(json.dumps(request.to_dict()))

        try:
            response = await asyncio.wait_for(response_future, timeout=self.timeout)
            return response
        except asyncio.TimeoutError:
            raise TimeoutError(f"Request {request.method} timed out")

    async def send_notification(self, notification: JsonRpcNotification) -> None:
        """发送通知"""
        if not self._ws:
            raise ConnectionError("Not connected")

        await self._ws.send(json.dumps(notification.to_dict()))

    async def receive(self) -> AsyncGenerator[JsonRpcResponse | JsonRpcNotification, None]:
        """接收 WebSocket 消息流"""
        while self._connected:
            try:
                message = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                yield message
            except asyncio.TimeoutError:
                continue

    async def _ws_loop(self) -> None:
        """WebSocket 消息循环"""
        if not self._ws:
            return

        try:
            async for message in self._ws:
                if not self._connected:
                    break

                try:
                    data = json.loads(message)
                    if "result" in data or "error" in data:
                        await self._event_queue.put(JsonRpcResponse.from_dict(data))
                    elif "method" in data:
                        await self._event_queue.put(JsonRpcNotification(method=data["method"], params=data.get("params")))
                except json.JSONDecodeError:
                    pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"WebSocket loop error: {e}")

    @property
    def is_connected(self) -> bool:
        return self._connected and self._ws is not None


def create_transport(config: dict[str, Any]) -> Transport:
    """根据配置创建相应的传输层"""
    transport_type = config.get("type", "stdio")

    if transport_type == "stdio":
        return StdioTransport(
            command=config["command"],
            args=config.get("args", []),
            env=config.get("env"),
            timeout=config.get("timeout", 30),
        )
    elif transport_type == "sse":
        return SSETransport(
            url=config["url"],
            headers=config.get("headers"),
            timeout=config.get("timeout", 30),
        )
    elif transport_type == "http":
        return HTTPTransport(
            url=config["url"],
            headers=config.get("headers"),
            timeout=config.get("timeout", 30),
        )
    elif transport_type == "websocket":
        return WebSocketTransport(
            url=config["url"],
            headers=config.get("headers"),
            timeout=config.get("timeout", 30),
        )
    else:
        raise ValueError(f"Unknown transport type: {transport_type}")


class MCPClientProtocol(ABC):
    """MCP 客户端协议接口"""

    @property
    @abstractmethod
    def client_name(self) -> str:
        """客户端名称"""
        pass

    @property
    @abstractmethod
    def protocol_version(self) -> str:
        """协议版本"""
        pass

    @abstractmethod
    async def initialize(self) -> McpCapabilities:
        """初始化连接，获取服务器能力"""
        pass

    @abstractmethod
    async def list_tools(self) -> list[McpTool]:
        """列出所有可用工具"""
        pass

    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """调用工具"""
        pass

    @abstractmethod
    async def list_resources(self) -> list[McpResource]:
        """列出所有可用资源"""
        pass

    @abstractmethod
    async def list_prompts(self) -> list[McpPrompt]:
        """列出所有可用提示"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭连接"""
        pass


class MCPClient(MCPClientProtocol):
    """MCP 客户端实现"""

    def __init__(
        self,
        name: str = "crush-agent",
        protocol_version: str = "2024-11-05",
    ):
        self._name = name
        self._protocol_version = protocol_version
        self._transport: Transport | None = None
        self._capabilities: McpCapabilities | None = None
        self._server_info: dict[str, Any] | None = None
        self._notification_handler: callable | None = None
        self._notification_task: asyncio.Task[None] | None = None

    @property
    def client_name(self) -> str:
        return self._name

    @property
    def protocol_version(self) -> str:
        return self._protocol_version

    async def connect(self, transport: Transport) -> None:
        """连接到 MCP 服务器"""
        self._transport = transport
        await transport.connect()
        # 如果有 notification handler，启动监听
        if self._notification_handler:
            self._start_notification_listener()

    async def close(self) -> None:
        """关闭连接"""
        # 停止 notification 监听任务
        if self._notification_task:
            self._notification_task.cancel()
            try:
                await self._notification_task
            except asyncio.CancelledError:
                pass
            self._notification_task = None

        if self._transport:
            await self._transport.disconnect()
            self._transport = None
        self._capabilities = None
        self._server_info = None

    def set_notification_handler(self, handler: callable) -> None:
        """
        设置 notification 处理器

        Args:
            handler: 回调函数，签名为 (method: str, params: dict | None) -> None
                    如果 handler 返回 False，将停止监听
        """
        self._notification_handler = handler
        # 如果已经连接，启动监听
        if self._transport and self._transport.is_connected:
            self._start_notification_listener()

    def _start_notification_listener(self) -> None:
        """启动 notification 监听循环"""
        if self._notification_task and not self._notification_task.done():
            return  # 已经在运行

        async def listen():
            if not self._transport:
                return

            try:
                async for message in self._transport.receive():
                    if self._notification_handler is None:
                        break

                    # 判断是 notification
                    if isinstance(message, JsonRpcNotification):
                        should_continue = self._notification_handler(message.method, message.params)
                        if should_continue is False:
                            break
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Notification listener error: {e}")

        self._notification_task = asyncio.create_task(listen())

    async def initialize(self) -> McpCapabilities:
        """初始化连接"""
        if not self._transport:
            raise ConnectionError("Not connected")

        request = JsonRpcRequest(
            method="initialize",
            params={
                "protocolVersion": self._protocol_version,
                "clientInfo": {
                    "name": self._name,
                    "version": "1.0.0",
                },
                "capabilities": {
                    "roots": {"listChanged": True},
                    "sampling": {},
                },
            },
        )

        response = await self._transport.send(request)
        if response.is_error:
            raise ConnectionError(f"Initialize failed: {response.error}")

        self._server_info = response.result.get("serverInfo", {})
        self._capabilities = McpCapabilities.from_dict(response.result.get("capabilities", {}))

        await self._transport.send_notification(JsonRpcNotification(method="notifications/initialized"))

        logger.info(f"MCP Client: Initialized with server {self._server_info.get('name', 'unknown')}")

        return self._capabilities

    def get_capabilities(self) -> McpCapabilities | None:
        """获取服务器能力"""
        return self._capabilities

    def get_server_info(self) -> dict[str, Any] | None:
        """获取服务器信息"""
        return self._server_info

    async def list_tools(self) -> list[McpTool]:
        """列出所有可用工具"""
        if not self._transport:
            raise ConnectionError("Not connected")

        request = JsonRpcRequest(method="tools/list")
        response = await self._transport.send(request)

        if response.is_error:
            raise ConnectionError(f"List tools failed: {response.error}")

        tools = []
        for tool_data in response.result.get("tools", []):
            tools.append(McpTool(
                name=tool_data["name"],
                description=tool_data.get("description", ""),
                input_schema=tool_data.get("inputSchema", {}),
                server_name="",
            ))

        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """调用工具"""
        if not self._transport:
            raise ConnectionError("Not connected")

        request = JsonRpcRequest(
            method="tools/call",
            params={
                "name": tool_name,
                "arguments": arguments,
            },
        )

        response = await self._transport.send(request)

        if response.is_error:
            return {"success": False, "error": response.error.get("message", "Unknown error")}

        return {"success": True, "result": response.result}

    async def list_resources(self) -> list[McpResource]:
        """列出所有可用资源"""
        if not self._transport:
            raise ConnectionError("Not connected")

        request = JsonRpcRequest(method="resources/list")
        response = await self._transport.send(request)

        if response.is_error:
            return []

        resources = []
        for res_data in response.result.get("resources", []):
            resources.append(McpResource(
                uri=res_data["uri"],
                name=res_data.get("name", ""),
                description=res_data.get("description"),
                mime_type=res_data.get("mimeType"),
                server_name="",
            ))

        return resources

    async def list_prompts(self) -> list[McpPrompt]:
        """列出所有可用提示"""
        if not self._transport:
            raise ConnectionError("Not connected")

        request = JsonRpcRequest(method="prompts/list")
        response = await self._transport.send(request)

        if response.is_error:
            return []

        prompts = []
        for prompt_data in response.result.get("prompts", []):
            prompts.append(McpPrompt(
                name=prompt_data["name"],
                description=prompt_data.get("description"),
                arguments=prompt_data.get("arguments", []),
                server_name="",
            ))

        return prompts

    @property
    def is_connected(self) -> bool:
        return self._transport is not None and self._transport.is_connected
