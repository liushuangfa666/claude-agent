"""
SSE Transport 实现 - Server-Sent Events + HTTP POST

SSETransport: HTTP GET 接收 SSE 事件 + HTTP POST 发送事件

特性：
- SSE 解析 (event:, id:, data:)
- 序列号去重
- 45秒保活超时
- POST 重试机制（指数退避）
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from .base import Transport, TransportMessage

logger = logging.getLogger(__name__)


@dataclass
class SSEEvent:
    """SSE 事件解析结果"""
    event: str = "message"
    data: str = ""
    id: str | None = None
    retry: int | None = None

    @property
    def is_heartbeat(self) -> bool:
        """是否是心跳事件"""
        return self.event == "heartbeat" or self.data == ""


@dataclass
class SSEMessage:
    """SSE 消息封装"""
    event_type: str
    data: dict[str, Any]
    event_id: str | None = None
    sequence: int | None = None


class SSETransport(Transport):
    """
    SSE Transport: HTTP GET (SSE) + HTTP POST

    用于接收服务器推送 (SSE) 和发送事件 (HTTP POST)。
    典型用例：Claude Code 的通信协议。
    """

    def __init__(
        self,
        sse_url: str,
        post_url: str,
        session_id: str,
        headers: dict[str, str] | None = None,
        heartbeat_timeout: float = 45.0,
        max_reconnect_attempts: int = 10,
        max_reconnect_delay: float = 600.0,
        retry_post_delay: float = 1.0,
    ) -> None:
        """
        初始化 SSE Transport

        Args:
            sse_url: SSE 接收 URL (HTTP GET)
            post_url: 事件发送 URL (HTTP POST)
            session_id: 会话 ID
            headers: HTTP 请求头
            heartbeat_timeout: 心跳超时时间（秒）
            max_reconnect_attempts: 最大重连次数
            max_reconnect_delay: 最大重连延迟
            retry_post_delay: POST 重试基础延迟
        """
        super().__init__()
        self._sse_url = sse_url
        self._post_url = post_url
        self._session_id = session_id
        self._headers = headers or {}
        self._heartbeat_timeout = heartbeat_timeout
        self._max_reconnect_attempts = max_reconnect_attempts
        self._max_reconnect_delay = max_reconnect_delay
        self._retry_post_delay = retry_post_delay

        self._connected = False
        self._running = False
        self._reader_task: asyncio.Task[None] | None = None
        self._message_queue: asyncio.Queue[TransportMessage] = asyncio.Queue()
        self._post_queue: asyncio.Queue[tuple[TransportMessage, int]] = asyncio.Queue()
        self._writer_task: asyncio.Task[None] | None = None

        # 序列号去重
        self._last_event_id: str | None = None
        self._seen_event_ids: set[str] = field(default_factory=set)
        self._max_seen_ids: int = 1000

        # POST 重试状态
        self._post_retry_count: dict[str, int] = {}

    async def connect(self) -> None:
        """建立连接"""
        self._running = True
        self._connected = True
        self._trigger_connect()

        self._reader_task = asyncio.create_task(self._sse_reader_loop())
        self._writer_task = asyncio.create_task(self._post_writer_loop())

        logger.info(f"SSE transport connected: {self._sse_url}")

    async def _sse_reader_loop(self) -> None:
        """SSE 读取循环"""
        import aiohttp

        attempt = 0
        last_error: Exception | None = None

        while self._running:
            try:
                headers = dict(self._headers)
                if self._last_event_id:
                    headers["Last-Event-ID"] = self._last_event_id

                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        self._sse_url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=None),
                    ) as resp:
                        if resp.status != 200:
                            logger.warning(f"SSE connection failed with status {resp.status}")
                            resp.close()
                            await self._handle_retry(attempt)
                            attempt += 1
                            continue

                        resp_headers = resp.headers
                        if "Content-Type" in resp_headers:
                            content_type = resp_headers.get("Content-Type", "")
                            if "text/event-stream" not in content_type:
                                logger.warning(f"Unexpected content type: {content_type}")

                        attempt = 0
                        async for line in resp.content:
                            if not self._running:
                                break

                            event = self._parse_sse_line(line)
                            if event is None:
                                continue

                            if event.is_heartbeat:
                                logger.debug("Received heartbeat")
                                continue

                            # 序列号去重
                            if event.id and event.id in self._seen_event_ids:
                                logger.debug(f"Skipping duplicate event: {event.id}")
                                continue

                            if event.id:
                                self._last_event_id = event.id
                                self._seen_event_ids.add(event.id)
                                if len(self._seen_event_ids) > self._max_seen_ids:
                                    oldest = next(iter(self._seen_event_ids))
                                    self._seen_event_ids.discard(oldest)

                            msg = TransportMessage(
                                id=event.id or str(uuid.uuid4()),
                                type=event.event_type,
                                data={"content": event.data},
                            )
                            await self._message_queue.put(msg)

            except asyncio.CancelledError:
                logger.debug("SSE reader cancelled")
                break
            except aiohttp.ClientError as e:
                last_error = e
                logger.warning(f"SSE client error: {e}")
                await self._handle_retry(attempt)
                attempt += 1
            except Exception as e:
                last_error = e
                logger.error(f"SSE reader error: {e}")
                await self._handle_retry(attempt)
                attempt += 1

        self._connected = False
        self._trigger_disconnect()

    def _parse_sse_line(self, line: bytes) -> SSEEvent | None:
        """
        解析单行 SSE 数据

        Args:
            line: 原始行数据

        Returns:
            SSEEvent | None: 解析后的事件，如果是无用行则返回 None
        """
        if not line:
            return None

        line_str = line.decode("utf-8").rstrip("\r\n")

        # 空行表示事件结束
        if not line_str:
            return None

        # 注释行
        if line_str.startswith(":"):
            return None

        # 解析字段
        if ":" in line_str:
            field_str, _, value = line_str.partition(":")
            field_str = field_str.strip()
            value = value.strip()
        else:
            field_str = line_str.strip()
            value = ""

        event = SSEEvent()

        if field_str == "event":
            event.event = value or "message"
        elif field_str == "data":
            event.data = value
        elif field_str == "id":
            event.id = value if value else None
        elif field_str == "retry":
            try:
                event.retry = int(value)
            except ValueError:
                pass

        return event

    async def _handle_retry(self, attempt: int) -> None:
        """处理重连"""
        if attempt >= self._max_reconnect_attempts:
            logger.error(f"Max reconnect attempts ({self._max_reconnect_attempts}) reached")
            error = Exception(f"Max reconnect attempts reached. Last error: {self._last_error()}")
            self._trigger_error(error)
            self._running = False
            return

        delay = min(self._retry_post_delay * (2 ** attempt), self._max_reconnect_delay)
        logger.info(f"Reconnecting in {delay:.1f}s (attempt {attempt + 1})...")
        await asyncio.sleep(delay)

    def _last_error(self) -> str:
        """获取最后的错误信息"""
        return "Connection failed"

    async def _post_writer_loop(self) -> None:
        """HTTP POST 写入循环"""
        import aiohttp

        while self._running:
            try:
                message, original_attempt = await self._post_queue.get()

                if message.id in self._post_retry_count:
                    attempt = self._post_retry_count[message.id]
                else:
                    attempt = original_attempt
                    self._post_retry_count[message.id] = attempt

                payload = {
                    "session_id": self._session_id,
                    "event_id": message.id,
                    "type": message.type,
                    "data": message.data,
                }

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self._post_url}/session/{self._session_id}/events",
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=30.0),
                    ) as resp:
                        if resp.status == 200:
                            if message.id in self._post_retry_count:
                                del self._post_retry_count[message.id]
                            logger.debug(f"POST succeeded for event {message.id}")
                        elif resp.status == 429:
                            # 限流，重试
                            await self._retry_post(message, attempt + 1)
                        elif 400 <= resp.status < 500:
                            # 客户端错误，不重试
                            logger.warning(f"POST failed with client error {resp.status}: {message.id}")
                            if message.id in self._post_retry_count:
                                del self._post_retry_count[message.id]
                        else:
                            # 服务端错误，重试
                            await self._retry_post(message, attempt + 1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"POST writer error: {e}")
                await asyncio.sleep(1)

    async def _retry_post(self, message: TransportMessage, attempt: int) -> None:
        """重试 POST 请求"""
        if attempt > self._max_reconnect_attempts:
            logger.warning(f"Max POST retries reached for {message.id}")
            if message.id in self._post_retry_count:
                del self._post_retry_count[message.id]
            return

        self._post_retry_count[message.id] = attempt
        delay = self._retry_post_delay * (2 ** min(attempt, 10))
        await asyncio.sleep(delay)
        await self._post_queue.put((message, attempt))

    async def write(self, message: TransportMessage) -> None:
        """
        发送消息到服务器

        Args:
            message: 传输消息
        """
        await self._post_queue.put((message, 0))

    def read(self) -> AsyncGenerator[TransportMessage, None]:
        """
        读取消息流

        Yields:
            TransportMessage: 接收到的消息
        """
        return self._message_generator()

    async def _message_generator(self) -> AsyncGenerator[TransportMessage, None]:
        """异步消息生成器"""
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=self._heartbeat_timeout,
                )
                yield message
            except asyncio.TimeoutError:
                # 心跳超时检查
                if not self._running:
                    break
                logger.debug("SSE read timeout, still waiting...")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Message generator error: {e}")
                break

    async def disconnect(self) -> None:
        """断开连接"""
        self._running = False
        self._connected = False

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._writer_task:
            self._writer_task.cancel()
            try:
                await self._writer_task
            except asyncio.CancelledError:
                pass
            self._writer_task = None

        self._seen_event_ids.clear()
        self._post_retry_count.clear()
        logger.info("SSE transport disconnected")

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected


def parse_sse_stream(data: str) -> list[SSEEvent]:
    """
    解析完整的 SSE 数据流

    Args:
        data: 完整的 SSE 数据（多行）

    Returns:
        List[SSEEvent]: 解析后的事件列表
    """
    events = []
    current_event = SSEEvent()

    for line in data.split("\n"):
        line = line.rstrip("\r\n")

        if not line:
            if current_event.data or current_event.event != "message":
                events.append(current_event)
            current_event = SSEEvent()
            continue

        if line.startswith(":"):
            continue

        if ":" in line:
            field_str, _, value = line.partition(":")
            field_str = field_str.strip()
            value = value.strip()
        else:
            field_str = line.strip()
            value = ""

        if field_str == "event":
            current_event.event = value or "message"
        elif field_str == "data":
            current_event.data = value
        elif field_str == "id":
            current_event.id = value if value else None
        elif field_str == "retry":
            try:
                current_event.retry = int(value)
            except ValueError:
                pass

    if current_event.data or current_event.event != "message":
        events.append(current_event)

    return events
