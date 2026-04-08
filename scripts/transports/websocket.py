"""
WebSocket 传输层实现 - 修复版

特性：
- 自动重连机制（指数退避 + 抖动）
- 永久错误不重试（4xx 错误码）
- 序列号确认机制
- Reader/Writer 任务协同
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from .base import Transport, TransportMessage

logger = logging.getLogger(__name__)

# WebSocket 永久关闭码（不重试）
PERMANENT_CLOSE_CODES: set[int] = {1002, 4001, 4003}


class WebSocketTransport(Transport):
    """
    WebSocket 传输层 - 修复版

    修复了原版中的连接生命周期管理问题，
    确保 reader 和 writer 任务正确协同。
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        max_reconnect_attempts: int = 10,
        max_reconnect_delay: float = 600.0,
    ) -> None:
        super().__init__()
        self.url = url
        self.headers = headers or {}
        self.max_reconnect_attempts = max_reconnect_attempts
        self.max_reconnect_delay = max_reconnect_delay

        self._ws: Any = None  # websockets.WebSocketClientProtocol
        self._connected = False
        self._reader_task: asyncio.Task[None] | None = None
        self._writer_task: asyncio.Task[None] | None = None
        self._queue: asyncio.Queue[TransportMessage] = asyncio.Queue()
        self._running = False

        # 序列号机制
        self._sequence = 0
        self._unconfirmed: dict[int, TransportMessage] = {}
        self._sequence_lock = asyncio.Lock()

    async def connect(self) -> None:
        """建立连接，带重连逻辑"""
        self._running = True
        await self._connect_with_retry()

    async def _connect_with_retry(self) -> None:
        """带指数退避的重连"""
        import websockets

        attempt = 0
        last_error: Exception | None = None

        while attempt < self.max_reconnect_attempts and self._running:
            try:
                self._ws = await websockets.connect(
                    self.url,
                    extra_headers=self.headers,
                )
                self._connected = True
                logger.info(f"WebSocket connected to {self.url}")

                # 重连后重发未确认的消息
                await self._resend_unconfirmed()

                # 启动读写任务
                self._reader_task = asyncio.create_task(self._reader_loop())
                self._writer_task = asyncio.create_task(self._writer_loop())

                self._trigger_connect()
                return

            except websockets.exceptions.InvalidURI as e:
                logger.error(f"Invalid WebSocket URI: {e}")
                self._trigger_error(e)
                raise

            except websockets.exceptions.InvalidHandshake as e:
                logger.error(f"Invalid handshake: {e}")
                self._trigger_error(e)
                raise

            except OSError as e:
                last_error = e
                attempt += 1
                logger.warning(f"WebSocket connection attempt {attempt} failed: {e}")

                delay = self._calculate_delay(attempt)
                logger.info(f"Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)

            except Exception as e:
                last_error = e
                attempt += 1

                if self._is_permanent_error(e):
                    logger.error(f"Permanent error, not retrying: {e}")
                    self._trigger_error(e)
                    raise

                delay = self._calculate_delay(attempt)
                logger.warning(f"WebSocket error (will retry): {e}")
                await asyncio.sleep(delay)

        if last_error:
            self._trigger_error(last_error)
            raise last_error

    def _is_permanent_error(self, error: Exception) -> bool:
        """判断是否为永久错误（不重试）"""
        if hasattr(error, "code") and error.code in PERMANENT_CLOSE_CODES:
            return True

        if hasattr(error, "errno"):
            if 400 <= (error.errno % 1000) < 500:
                return True

        return False

    def _calculate_delay(self, attempt: int) -> float:
        """指数退避 + 抖动"""
        base_delay = min(60.0 * (2**attempt), self.max_reconnect_delay)
        jitter = random.uniform(0, base_delay * 0.1)
        return base_delay + jitter

    async def _resend_unconfirmed(self) -> None:
        """重发未确认的消息"""
        if not self._ws:
            return

        async with self._sequence_lock:
            for seq, msg in list(self._unconfirmed.items()):
                try:
                    data = msg.to_dict()
                    data["sequence"] = seq
                    await self._ws.send(json.dumps(data))
                    logger.debug(f"Resent unconfirmed message: {seq}")
                except Exception as e:
                    logger.warning(f"Failed to resend message {seq}: {e}")

    async def _reader_loop(self) -> None:
        """读取循环"""
        import websockets

        try:
            async for raw in self._ws:
                if not self._running:
                    break

                try:
                    data = json.loads(raw)
                    seq = data.get("sequence")

                    if seq and isinstance(seq, int) and seq in self._unconfirmed:
                        async with self._sequence_lock:
                            del self._unconfirmed[seq]
                        logger.debug(f"Confirmed message sequence: {seq}")

                    msg = TransportMessage.from_dict(data)
                    self._queue.put_nowait(msg)

                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON: {raw[:100]}")
                    continue

        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket connection closed")
        except asyncio.CancelledError:
            logger.debug("Reader loop cancelled")
        except Exception as e:
            logger.error(f"Reader loop error: {e}")
        finally:
            was_connected = self._connected
            self._connected = False

            if was_connected:
                self._trigger_disconnect()

            if self._running:
                logger.info("Scheduling reconnection...")
                asyncio.create_task(self._connect_with_retry())

    async def _writer_loop(self) -> None:
        """写入循环"""
        while self._running and self._connected:
            try:
                message = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=30.0,
                )

                async with self._sequence_lock:
                    self._sequence += 1
                    message.sequence = self._sequence
                    self._unconfirmed[self._sequence] = message

                data = message.to_dict()
                await self._ws.send(json.dumps(data))
                logger.debug(f"Sent message with sequence: {self._sequence}")

            except asyncio.TimeoutError:
                if self._ws and self._connected:
                    try:
                        await self._ws.send("")
                    except Exception:
                        pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Writer loop error: {e}")
                await asyncio.sleep(1)

    async def write(self, message: TransportMessage) -> None:
        """发送消息到队列"""
        await self._queue.put(message)

    def read(self) -> AsyncGenerator[TransportMessage, None]:
        """读取消息流"""
        return self._message_generator()

    async def _message_generator(self) -> AsyncGenerator[TransportMessage, None]:
        """异步消息生成器"""
        while self._running:
            try:
                message = await self._queue.get()
                yield message
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in message generator: {e}")
                break

    async def disconnect(self) -> None:
        """断开连接"""
        self._running = False

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

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        self._connected = False
        self._unconfirmed.clear()
        logger.info("WebSocket disconnected")

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected
