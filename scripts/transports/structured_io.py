"""
StructuredIO - NDJSON 结构化输入输出

提供基于 NewLine-Delimited JSON 的结构化通信接口。

功能：
- NDJSON 解析和序列化
- 命令队列（批处理、优先级机制）
- Hook 回调管理
- MCP 消息处理
- 采集请求处理 (elicitation)

参考 Claude Code 的 StructuredIO 设计。
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator, Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class MessagePriority(Enum):
    """消息优先级"""
    HIGH = 1  # 立即发送 (非流式事件)
    NORMAL = 2  # 普通 (流式事件，可批量)
    LOW = 3  # 低优先级 (心跳等)


@dataclass
class NDJSONMessage:
    """NDJSON 消息封装"""
    id: str
    type: str
    data: dict[str, Any]
    priority: MessagePriority = MessagePriority.NORMAL

    def to_json(self) -> str:
        """序列化为 JSON 行"""
        obj = {"id": self.id, "type": self.type, **self.data}
        return json.dumps(obj, ensure_ascii=False)

    @classmethod
    def from_json(cls, line: str) -> NDJSONMessage | None:
        """从 JSON 行解析"""
        try:
            obj = json.loads(line)
            return cls(
                id=obj.get("id", str(uuid.uuid4())),
                type=obj.get("type", "unknown"),
                data=obj,
                priority=MessagePriority.NORMAL,
            )
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse NDJSON: {line[:100]}")
            return None


@dataclass
class QueuedMessage:
    """队列消息封装"""
    message: NDJSONMessage
    attempt: int = 0
    created_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())


class HookCallback:
    """Hook 回调封装"""

    def __init__(
        self,
        callback_id: str,
        callback: Callable[..., Awaitable[Any]],
        timeout: float | None = None,
    ):
        self.callback_id = callback_id
        self.callback = callback
        self.timeout = timeout
        self._future: asyncio.Future | None = None

    async def invoke(self, *args: Any, **kwargs: Any) -> Any:
        """调用回调"""
        if self.timeout:
            try:
                return await asyncio.wait_for(
                    self.callback(*args, **kwargs),
                    timeout=self.timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(f"Hook callback {self.callback_id} timed out")
                raise
        else:
            return await self.callback(*args, **kwargs)


@dataclass
class ElicitationRequest:
    """采集请求"""
    server_name: str
    message: str
    schema: dict[str, Any] | None = None
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class CanUseToolFn:
    """权限检查回调函数类型"""

    def __init__(
        self,
        on_permission_prompt: Callable[[str, dict], Coroutine[Any, Any, str]],
    ):
        self._on_permission_prompt = on_permission_prompt

    async def __call__(self, tool_name: str, args: dict) -> str:
        """
        检查工具使用权限

        Args:
            tool_name: 工具名称
            args: 工具参数

        Returns:
            str: "allowed", "denied", 或 "prompt"
        """
        return await self._on_permission_prompt(tool_name, args)


class StructuredIO:
    """
    StructuredIO - NDJSON 结构化输入输出

    用于 Agent 与外部系统之间的结构化通信。
    支持：
    - NDJSON 行解析
    - 优先级队列
    - Hook 回调
    - 采集请求处理
    """

    def __init__(
        self,
        structured_input: AsyncGenerator[dict[str, Any], None] | None = None,
        outbound: asyncio.Queue[NDJSONMessage] | None = None,
    ):
        """
        初始化 StructuredIO

        Args:
            structured_input: 结构化输入生成器
            outbound: 输出队列
        """
        self._structured_input = structured_input
        self._outbound = outbound or asyncio.Queue()
        self._hooks: dict[str, HookCallback] = {}
        self._elicitation_handlers: dict[str, Callable[..., Awaitable[Any]]] = {}
        self._running = False
        self._reader_task: asyncio.Task[None] | None = None

        # 命令队列（用于批处理）
        self._command_queue: asyncio.PriorityQueue[QueuedMessage] = asyncio.PriorityQueue()
        self._batch_task: asyncio.Task[None] | None = None
        self._batch_delay = 0.05  # 50ms 批量延迟
        self._max_batch_size = 100

    def set_structured_input(
        self,
        input_gen: AsyncGenerator[dict[str, Any], None],
    ) -> None:
        """设置结构化输入生成器"""
        self._structured_input = input_gen

    def set_outbound_queue(self, queue: asyncio.Queue[NDJSONMessage]) -> None:
        """设置输出队列"""
        self._outbound = queue

    async def start(self) -> None:
        """启动 IO 处理"""
        self._running = True
        if self._structured_input:
            self._reader_task = asyncio.create_task(self._reader_loop())
        self._batch_task = asyncio.create_task(self._batch_loop())

    async def stop(self) -> None:
        """停止 IO 处理"""
        self._running = False

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._batch_task:
            self._batch_task.cancel()
            try:
                await self._batch_task
            except asyncio.CancelledError:
                pass
            self._batch_task = None

    async def _reader_loop(self) -> None:
        """输入读取循环"""
        if not self._structured_input:
            return

        try:
            async for data in self._structured_input:
                if not self._running:
                    break
                await self._handle_input(data)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"StructuredIO reader error: {e}")

    async def _handle_input(self, data: dict[str, Any]) -> None:
        """处理输入数据"""
        msg_type = data.get("type", "")

        if msg_type == "hook_callback":
            await self._handle_hook_callback(data)
        elif msg_type == "elicitation":
            await self._handle_elicitation(data)
        elif msg_type == "mcp_message":
            await self._handle_mcp_message(data)
        else:
            logger.debug(f"Unknown message type: {msg_type}")

    async def _handle_hook_callback(self, data: dict[str, Any]) -> None:
        """处理 Hook 回调"""
        callback_id = data.get("callback_id")
        if not callback_id or callback_id not in self._hooks:
            logger.warning(f"Unknown hook callback: {callback_id}")
            return

        hook = self._hooks[callback_id]
        result = data.get("result")

        try:
            if hook._future and not hook._future.done():
                hook._future.set_result(result)
        except Exception as e:
            logger.error(f"Hook callback error: {e}")

    async def _handle_elicitation(self, data: dict[str, Any]) -> None:
        """处理采集请求"""
        server_name = data.get("server_name", "")
        request_id = data.get("request_id", "")

        handler_key = f"{server_name}:{request_id}"
        if handler_key in self._elicitation_handlers:
            handler = self._elicitation_handlers[handler_key]
            try:
                result = await handler(data)
                await self.send_result(request_id, result)
            except Exception as e:
                logger.error(f"Elicitation handler error: {e}")
                await self.send_error(request_id, str(e))

    async def _handle_mcp_message(self, data: dict[str, Any]) -> None:
        """处理 MCP 消息"""
        server_name = data.get("server_name", "")
        method = data.get("method")

        handler_key = f"mcp:{server_name}"
        if handler_key in self._elicitation_handlers:
            handler = self._elicitation_handlers[handler_key]
            try:
                result = await handler(data)
                await self.send_mcp_result(server_name, data.get("request_id"), result)
            except Exception as e:
                logger.error(f"MCP message handler error: {e}")
                await self.send_mcp_error(server_name, data.get("request_id"), str(e))

    async def _batch_loop(self) -> None:
        """批量发送循环"""
        while self._running:
            try:
                await asyncio.sleep(self._batch_delay)
                await self._flush_batch()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Batch loop error: {e}")

    async def _flush_batch(self) -> None:
        """刷新批量消息"""
        batch: list[QueuedMessage] = []

        # 收集批量消息（高优先级消息立即发送）
        while not self._command_queue.empty():
            try:
                queued = self._command_queue.get_nowait()
                batch.append(queued)

                # 高优先级消息立即发送，不批量
                if queued.message.priority == MessagePriority.HIGH:
                    break

                # 达到批量大小，发送
                if len(batch) >= self._max_batch_size:
                    break
            except asyncio.QueueEmpty:
                break

        # 发送批量消息
        for queued in batch:
            try:
                await self._send_direct(queued.message)
            except Exception as e:
                logger.error(f"Failed to send message: {e}")

    async def _send_direct(self, message: NDJSONMessage) -> None:
        """直接发送消息"""
        await self._outbound.put(message)

    def create_can_use_tool(
        self,
        on_permission_prompt: Callable[[str, dict], Coroutine[Any, Any, str]],
    ) -> CanUseToolFn:
        """
        创建权限检查函数

        Args:
            on_permission_prompt: 权限提示回调

        Returns:
            CanUseToolFn: 权限检查函数
        """
        return CanUseToolFn(on_permission_prompt)

    def create_hook_callback(
        self,
        callback_id: str,
        callback: Callable[..., Awaitable[Any]],
        timeout: float | None = None,
    ) -> HookCallback:
        """
        创建 Hook 回调

        Args:
            callback_id: 回调 ID
            callback: 回调函数
            timeout: 超时时间（秒）

        Returns:
            HookCallback: Hook 回调封装
        """
        hook = HookCallback(callback_id, callback, timeout)
        self._hooks[callback_id] = hook
        return hook

    def remove_hook_callback(self, callback_id: str) -> bool:
        """
        移除 Hook 回调

        Args:
            callback_id: 回调 ID

        Returns:
            bool: 是否成功移除
        """
        if callback_id in self._hooks:
            del self._hooks[callback_id]
            return True
        return False

    async def invoke_hook(self, callback_id: str, *args: Any, **kwargs: Any) -> Any:
        """
        调用 Hook 回调

        Args:
            callback_id: 回调 ID
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            Any: 回调结果
        """
        if callback_id not in self._hooks:
            raise ValueError(f"Unknown hook callback: {callback_id}")

        hook = self._hooks[callback_id]
        return await hook.invoke(*args, **kwargs)

    def handle_elicitation(
        self,
        server_name: str,
        message: str,
        schema: dict[str, Any] | None = None,
    ) -> asyncio.Future[Any]:
        """
        处理采集请求

        Args:
            server_name: 服务器名称
            message: 请求消息
            schema: 输入模式

        Returns:
            asyncio.Future: 结果 Future
        """
        request = ElicitationRequest(
            server_name=server_name,
            message=message,
            schema=schema,
        )

        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        handler_key = f"{server_name}:{request.request_id}"
        self._elicitation_handlers[handler_key] = lambda _: future
        self._elicitation_handlers[f"pending:{handler_key}"] = future

        return future

    def register_elicitation_handler(
        self,
        server_name: str,
        handler: Callable[..., Awaitable[Any]],
    ) -> None:
        """
        注册采集请求处理器

        Args:
            server_name: 服务器名称
            handler: 处理函数
        """
        handler_key = f"mcp:{server_name}"
        self._elicitation_handlers[handler_key] = handler

    async def send_result(self, request_id: str, result: Any) -> None:
        """
        发送采集结果

        Args:
            request_id: 请求 ID
            result: 结果
        """
        msg = NDJSONMessage(
            id=str(uuid.uuid4()),
            type="elicitation_result",
            data={
                "request_id": request_id,
                "result": result,
            },
            priority=MessagePriority.HIGH,
        )
        await self._outbound.put(msg)

    async def send_error(self, request_id: str, error: str) -> None:
        """
        发送错误响应

        Args:
            request_id: 请求 ID
            error: 错误信息
        """
        msg = NDJSONMessage(
            id=str(uuid.uuid4()),
            type="error",
            data={
                "request_id": request_id,
                "error": error,
            },
            priority=MessagePriority.HIGH,
        )
        await self._outbound.put(msg)

    async def send_mcp_message(self, server_name: str, message: dict[str, Any]) -> None:
        """
        发送 MCP 消息

        Args:
            server_name: MCP 服务器名称
            message: 消息内容
        """
        msg = NDJSONMessage(
            id=str(uuid.uuid4()),
            type="mcp_message",
            data={
                "server_name": server_name,
                **message,
            },
            priority=MessagePriority.HIGH,
        )
        await self._outbound.put(msg)

    async def send_mcp_result(
        self,
        server_name: str,
        request_id: str,
        result: Any,
    ) -> None:
        """
        发送 MCP 结果

        Args:
            server_name: MCP 服务器名称
            request_id: 请求 ID
            result: 结果
        """
        msg = NDJSONMessage(
            id=str(uuid.uuid4()),
            type="mcp_result",
            data={
                "server_name": server_name,
                "request_id": request_id,
                "result": result,
            },
            priority=MessagePriority.HIGH,
        )
        await self._outbound.put(msg)

    async def send_mcp_error(
        self,
        server_name: str,
        request_id: str,
        error: str,
    ) -> None:
        """
        发送 MCP 错误

        Args:
            server_name: MCP 服务器名称
            request_id: 请求 ID
            error: 错误信息
        """
        msg = NDJSONMessage(
            id=str(uuid.uuid4()),
            type="mcp_error",
            data={
                "server_name": server_name,
                "request_id": request_id,
                "error": error,
            },
            priority=MessagePriority.HIGH,
        )
        await self._outbound.put(msg)

    async def send_stream_event(
        self,
        event_type: str,
        content: str,
        **kwargs: Any,
    ) -> None:
        """
        发送流式事件（可批量）

        Args:
            event_type: 事件类型
            content: 事件内容
            **kwargs: 其他字段
        """
        msg = NDJSONMessage(
            id=str(uuid.uuid4()),
            type="stream_event",
            data={
                "event_type": event_type,
                "content": content,
                **kwargs,
            },
            priority=MessagePriority.NORMAL,
        )
        await self._command_queue.put(QueuedMessage(message=msg))

    async def send_high_priority(
        self,
        msg_type: str,
        data: dict[str, Any],
    ) -> None:
        """
        发送高优先级消息（立即发送，不批量）

        Args:
            msg_type: 消息类型
            data: 消息数据
        """
        msg = NDJSONMessage(
            id=str(uuid.uuid4()),
            type=msg_type,
            data=data,
            priority=MessagePriority.HIGH,
        )
        await self._outbound.put(msg)


async def parse_ndjson_stream(
    stream: AsyncGenerator[str, None],
) -> AsyncGenerator[NDJSONMessage, None]:
    """
    解析 NDJSON 流

    Args:
        stream: 字符串流

    Yields:
        NDJSONMessage: 解析后的消息
    """
    buffer = ""

    async for chunk in stream:
        buffer += chunk

        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if not line:
                continue

            msg = NDJSONMessage.from_json(line)
            if msg:
                yield msg


async def create_ndjson_stream(
    messages: AsyncGenerator[NDJSONMessage, None],
) -> AsyncGenerator[str, None]:
    """
    创建 NDJSON 流

    Args:
        messages: 消息生成器

    Yields:
        str: JSON 行
    """
    async for msg in messages:
        yield msg.to_json() + "\n"
