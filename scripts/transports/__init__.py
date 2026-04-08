"""
传输层模块 - Agent 通信抽象层

提供统一的传输接口，支持：
- WebSocket 双向通信
- HTTP POST 写入
- Hybrid 混合模式 (WebSocket 读 + HTTP 写)
- SSE 传输模式 (SSE 接收 + HTTP POST 发送)
- StructuredIO (NDJSON 结构化输入输出)
"""
from __future__ import annotations

from .base import Transport, TransportMessage
from .websocket import WebSocketTransport
from .hybrid import HybridTransport
from .sse import SSETransport, SSEEvent, SSEMessage, parse_sse_stream
from .structured_io import (
    StructuredIO,
    NDJSONMessage,
    QueuedMessage,
    HookCallback,
    ElicitationRequest,
    CanUseToolFn,
    MessagePriority,
    parse_ndjson_stream,
    create_ndjson_stream,
)

__all__ = [
    "Transport",
    "TransportMessage",
    "WebSocketTransport",
    "HybridTransport",
    "SSETransport",
    "SSEEvent",
    "SSEMessage",
    "parse_sse_stream",
    "StructuredIO",
    "NDJSONMessage",
    "QueuedMessage",
    "HookCallback",
    "ElicitationRequest",
    "CanUseToolFn",
    "MessagePriority",
    "parse_ndjson_stream",
    "create_ndjson_stream",
]
