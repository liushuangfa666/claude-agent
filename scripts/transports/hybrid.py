"""
Hybrid 传输层实现

Hybrid Transport: WebSocket 读 + HTTP POST 写
用于 CCR v2 兼容模式。

特性：
- WebSocket 用于接收服务器推送
- HTTP POST 用于发送事件（支持批量合并）
- stream_event 类型消息延迟批量发送
- 非 stream 消息立即发送
- 队列满时背压控制
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

from .base import Transport, TransportMessage
from .websocket import WebSocketTransport

logger = logging.getLogger(__name__)


class HybridTransport(Transport):
    """
    Hybrid Transport: WebSocket 读 + HTTP POST 写

    用于 CCR v2 兼容模式，平衡实时性和效率。
    """

    def __init__(
        self,
        ws_url: str,
        http_url: str,
        session_id: str,
        batch_delay: float = 0.1,
        max_queue_size: int = 100_000,
    ) -> None:
        super().__init__()
        self._ws_url = ws_url
        self._http_url = http_url
        self._session_id = session_id
        self._batch_delay = batch_delay
        self._max_queue_size = max_queue_size

        self._ws_transport: WebSocketTransport | None = None
        self._write_queue: asyncio.Queue[TransportMessage] = asyncio.Queue(
            maxsize=max_queue_size
        )
        self._running = False
        self._flush_task: asyncio.Task[None] | None = None
        self._writer_task: asyncio.Task[None] | None = None
        self._stream_buffer: list[dict[str, Any]] = []
        self._buffer_lock = asyncio.Lock()

    async def connect(self) -> None:
        """建立连接"""
        self._ws_transport = WebSocketTransport(self._ws_url)
        self._ws_transport.set_on_connect(self._on_ws_connect)
        self._ws_transport.set_on_disconnect(self._on_ws_disconnect)
        self._ws_transport.set_on_error(self._on_ws_error)

        await self._ws_transport.connect()

        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        self._writer_task = asyncio.create_task(self._writer_loop())

    def _on_ws_connect(self) -> None:
        """WebSocket 连接成功回调"""
        logger.info("Hybrid transport: WebSocket connected")
        self._trigger_connect()

    def _on_ws_disconnect(self) -> None:
        """WebSocket 断开回调"""
        logger.info("Hybrid transport: WebSocket disconnected")
        self._trigger_disconnect()

    def _on_ws_error(self, error: Exception) -> None:
        """WebSocket 错误回调"""
        logger.error(f"Hybrid transport: WebSocket error: {error}")
        self._trigger_error(error)

    async def _flush_loop(self) -> None:
        """定期批量刷新循环"""
        while self._running:
            try:
                await asyncio.sleep(self._batch_delay)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Flush loop error: {e}")

    async def _flush(self) -> None:
        """刷新流缓冲区到 HTTP"""
        async with self._buffer_lock:
            if not self._stream_buffer:
                return

            events = self._stream_buffer.copy()

        if not events:
            return

        try:
            import aiohttp

            payload = {
                "session_id": self._session_id,
                "events": events,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._http_url}/session/{self._session_id}/events",
                    json=payload,
                ) as resp:
                    if resp.status == 200:
                        async with self._buffer_lock:
                            self._stream_buffer.clear()
                        logger.debug(f"Flushed {len(events)} stream events")
                    elif resp.status == 429:
                        logger.warning("Rate limited, will retry flush")
                        await asyncio.sleep(self._batch_delay * 2)
                    elif resp.status >= 500:
                        logger.warning(f"Server error {resp.status}, will retry")
                        await asyncio.sleep(self._batch_delay * 2)
                    else:
                        logger.error(f"HTTP error {resp.status}, discarding events")

        except ImportError:
            logger.error("aiohttp not installed, cannot flush events")
        except Exception as e:
            logger.error(f"Failed to flush events: {e}")

    async def write(self, message: TransportMessage) -> None:
        """
        写入消息

        - stream_event 类型消息延迟批量发送
        - 非 stream 消息立即发送
        """
        if message.type == "stream_event":
            async with self._buffer_lock:
                if len(self._stream_buffer) >= self._max_queue_size:
                    removed = self._stream_buffer.pop(0)
                    logger.warning(
                        f"Stream buffer full, removed oldest event: {removed.get('type')}"
                    )
                self._stream_buffer.append(message.data)
        else:
            await self._flush()
            try:
                self._write_queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.error("Write queue full, dropping message")

    async def _writer_loop(self) -> None:
        """写入循环 - 通过 HTTP POST"""
        try:
            import aiohttp
        except ImportError:
            logger.error("aiohttp not installed, HTTP writes disabled")
            return

        async with aiohttp.ClientSession() as session:
            while self._running:
                try:
                    message = await asyncio.wait_for(
                        self._write_queue.get(),
                        timeout=30.0,
                    )

                    payload = {
                        "session_id": self._session_id,
                        "events": [message.data],
                    }

                    async with session.post(
                        f"{self._http_url}/session/{self._session_id}/events",
                        json=payload,
                    ) as resp:
                        if resp.status >= 400 and resp.status != 429:
                            logger.warning(
                                f"HTTP write failed with {resp.status}, discarding"
                            )
                        elif resp.status == 429:
                            logger.warning("Rate limited, retrying write")
                            await asyncio.sleep(self._batch_delay)
                            self._write_queue.put_nowait(message)

                except asyncio.TimeoutError:
                    pass
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Writer loop error: {e}")
                    await asyncio.sleep(1)

    def read(self) -> AsyncGenerator[TransportMessage, None]:
        """读取 - 来自 WebSocket"""
        if self._ws_transport:
            return self._ws_transport.read()
        return self._empty_generator()

    async def _empty_generator(
        self,
    ) -> AsyncGenerator[TransportMessage, None]:
        """空生成器"""
        if False:
            yield TransportMessage()
        return

    async def disconnect(self) -> None:
        """断开连接"""
        self._running = False

        await self._flush()

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        if self._writer_task:
            self._writer_task.cancel()
            try:
                await self._writer_task
            except asyncio.CancelledError:
                pass
            self._writer_task = None

        if self._ws_transport:
            await self._ws_transport.disconnect()
            self._ws_transport = None

        logger.info("Hybrid transport disconnected")

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._ws_transport.is_connected if self._ws_transport else False
