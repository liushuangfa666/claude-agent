"""
Transports 模块测试
"""
import pytest
import asyncio


class TestNDJSONMessage:
    """NDJSONMessage 测试"""

    def test_message_creation(self):
        """测试消息创建"""
        from scripts.transports.structured_io import NDJSONMessage, MessagePriority

        msg = NDJSONMessage(
            id="msg-1",
            type="test",
            data={"key": "value"},
            priority=MessagePriority.NORMAL
        )

        assert msg.id == "msg-1"
        assert msg.type == "test"
        assert msg.data == {"key": "value"}
        assert msg.priority == MessagePriority.NORMAL

    def test_message_to_json(self):
        """测试消息序列化"""
        from scripts.transports.structured_io import NDJSONMessage, MessagePriority

        msg = NDJSONMessage(
            id="msg-1",
            type="test",
            data={"key": "value"},
            priority=MessagePriority.NORMAL
        )

        json_str = msg.to_json()
        assert "msg-1" in json_str
        assert "test" in json_str
        assert "key" in json_str

    def test_message_from_json(self):
        """测试消息反序列化"""
        from scripts.transports.structured_io import NDJSONMessage

        json_str = '{"id":"msg-1","type":"test","key":"value"}'
        msg = NDJSONMessage.from_json(json_str)

        assert msg is not None
        assert msg.id == "msg-1"
        assert msg.type == "test"
        assert msg.data["key"] == "value"

    def test_message_from_invalid_json(self):
        """测试无效 JSON"""
        from scripts.transports.structured_io import NDJSONMessage

        msg = NDJSONMessage.from_json("not valid json")
        assert msg is None

    def test_message_from_json_with_missing_fields(self):
        """测试缺少字段的 JSON"""
        from scripts.transports.structured_io import NDJSONMessage

        msg = NDJSONMessage.from_json('{"type":"test"}')
        assert msg is not None
        assert msg.id is not None  # 应该自动生成
        assert msg.type == "test"


class TestMessagePriority:
    """MessagePriority 枚举测试"""

    def test_priority_values(self):
        """测试优先级枚举值"""
        from scripts.transports.structured_io import MessagePriority

        assert MessagePriority.HIGH.value == 1
        assert MessagePriority.NORMAL.value == 2
        assert MessagePriority.LOW.value == 3

    def test_priority_ordering(self):
        """测试优先级顺序"""
        from scripts.transports.structured_io import MessagePriority

        # 比较枚举值
        assert MessagePriority.HIGH.value < MessagePriority.NORMAL.value
        assert MessagePriority.NORMAL.value < MessagePriority.LOW.value


class TestQueuedMessage:
    """QueuedMessage 测试"""

    def test_queued_message_creation(self):
        """测试队列消息创建"""
        import time
        from scripts.transports.structured_io import QueuedMessage, NDJSONMessage

        msg = NDJSONMessage(id="1", type="test", data={})
        # 直接传入 created_at 避免 event loop 问题
        queued = QueuedMessage(message=msg, attempt=0, created_at=time.time())

        assert queued.message == msg
        assert queued.attempt == 0
        assert queued.created_at is not None


class TestElicitationRequest:
    """ElicitationRequest 测试"""

    def test_request_creation(self):
        """测试采集请求创建"""
        from scripts.transports.structured_io import ElicitationRequest

        request = ElicitationRequest(
            server_name="github",
            message="Select repository"
        )

        assert request.server_name == "github"
        assert request.message == "Select repository"
        assert request.schema is None
        assert request.request_id is not None

    def test_request_with_schema(self):
        """测试带 schema 的采集请求"""
        from scripts.transports.structured_io import ElicitationRequest

        schema = {"type": "object", "properties": {"repo": {"type": "string"}}}
        request = ElicitationRequest(
            server_name="github",
            message="Select repository",
            schema=schema
        )

        assert request.schema == schema


class TestCanUseToolFn:
    """CanUseToolFn 测试"""

    @pytest.mark.asyncio
    async def test_permission_allowed(self):
        """测试权限允许"""
        from scripts.transports.structured_io import CanUseToolFn

        async def mock_prompt(tool_name, args):
            return "allowed"

        fn = CanUseToolFn(mock_prompt)
        result = await fn("Read", {"file_path": "test.py"})

        assert result == "allowed"

    @pytest.mark.asyncio
    async def test_permission_denied(self):
        """测试权限拒绝"""
        from scripts.transports.structured_io import CanUseToolFn

        async def mock_prompt(tool_name, args):
            return "denied"

        fn = CanUseToolFn(mock_prompt)
        result = await fn("Bash", {"command": "rm -rf /"})

        assert result == "denied"


class TestHookCallback:
    """HookCallback 测试"""

    @pytest.mark.asyncio
    async def test_callback_invocation(self):
        """测试回调调用"""
        from scripts.transports.structured_io import HookCallback

        result = None
        async def callback(x, y):
            return x + y

        hook = HookCallback("cb-1", callback)
        value = await hook.invoke(1, 2)
        assert value == 3

    @pytest.mark.asyncio
    async def test_callback_with_timeout(self):
        """测试带超时的回调"""
        from scripts.transports.structured_io import HookCallback

        async def slow_callback():
            await asyncio.sleep(0.1)
            return "done"

        hook = HookCallback("cb-1", slow_callback, timeout=0.5)

        value = await hook.invoke()
        assert value == "done"

    @pytest.mark.asyncio
    async def test_callback_timeout_exceeded(self):
        """测试超时"""
        from scripts.transports.structured_io import HookCallback

        async def slow_callback():
            await asyncio.sleep(1.0)
            return "done"

        hook = HookCallback("cb-1", slow_callback, timeout=0.1)

        with pytest.raises(asyncio.TimeoutError):
            await hook.invoke()


class TestStructuredIOInit:
    """StructuredIO 初始化测试"""

    def test_structured_io_creation(self):
        """测试 StructuredIO 创建"""
        from scripts.transports.structured_io import StructuredIO

        sio = StructuredIO()

        assert sio._structured_input is None
        assert isinstance(sio._outbound, asyncio.Queue)
        assert sio._hooks == {}
        assert sio._elicitation_handlers == {}
        assert sio._running is False

    def test_structured_io_with_queue(self):
        """测试带队列的 StructuredIO"""
        from scripts.transports.structured_io import StructuredIO

        queue = asyncio.Queue()
        sio = StructuredIO(outbound=queue)

        assert sio._outbound == queue


class TestStructuredIOStructuredInput:
    """StructuredIO 结构化输入测试"""

    def test_set_structured_input(self):
        """测试设置结构化输入"""
        from scripts.transports.structured_io import StructuredIO

        sio = StructuredIO()

        async def mock_gen():
            yield {"type": "test"}

        sio.set_structured_input(mock_gen())

        assert sio._structured_input is not None


class TestStructuredIOHighPriority:
    """StructuredIO 高优先级消息测试"""

    @pytest.mark.asyncio
    async def test_send_high_priority(self):
        """测试发送高优先级消息"""
        from scripts.transports.structured_io import StructuredIO, NDJSONMessage

        sio = StructuredIO()
        await sio.start()

        await sio.send_high_priority("test_type", {"key": "value"})

        # 检查队列中是否有消息
        assert not sio._outbound.empty()

        await sio.stop()


class TestStructuredIOStreamEvent:
    """StructuredIO 流式事件测试"""

    @pytest.mark.asyncio
    async def test_send_stream_event(self):
        """测试发送流式事件"""
        from scripts.transports.structured_io import StructuredIO

        sio = StructuredIO()
        await sio.start()

        await sio.send_stream_event("thinking", "Processing...")

        # 事件应该进入批处理队列
        assert not sio._command_queue.empty()

        await sio.stop()


class TestStructuredIOError:
    """StructuredIO 错误消息测试"""

    @pytest.mark.asyncio
    async def test_send_error(self):
        """测试发送错误"""
        from scripts.transports.structured_io import StructuredIO

        sio = StructuredIO()
        await sio.start()

        await sio.send_error("req-1", "Something went wrong")

        # 检查队列
        assert not sio._outbound.empty()

        await sio.stop()


class TestStructuredIOElicitation:
    """StructuredIO 采集请求测试"""

    @pytest.mark.asyncio
    async def test_handle_elicitation(self):
        """测试处理采集请求"""
        from scripts.transports.structured_io import StructuredIO

        sio = StructuredIO()

        future = sio.handle_elicitation("github", "Select repository")

        assert isinstance(future, asyncio.Future)
        # 检查是否有 github 相关 handler（key 包含 request_id）
        github_handlers = [k for k in sio._elicitation_handlers.keys() if k.startswith("github")]
        assert len(github_handlers) >= 1

    def test_register_elicitation_handler(self):
        """测试注册采集处理器"""
        from scripts.transports.structured_io import StructuredIO

        sio = StructuredIO()

        async def handler(data):
            return "handled"

        sio.register_elicitation_handler("github", handler)

        assert sio._elicitation_handlers.get("mcp:github") == handler


class TestStructuredIOHookCallbacks:
    """StructuredIO Hook 回调测试"""

    def test_create_hook_callback(self):
        """测试创建 Hook 回调"""
        from scripts.transports.structured_io import StructuredIO

        sio = StructuredIO()

        async def callback():
            return "done"

        hook = sio.create_hook_callback("cb-1", callback)

        assert hook.callback_id == "cb-1"
        assert "cb-1" in sio._hooks

    def test_remove_hook_callback(self):
        """测试移除 Hook 回调"""
        from scripts.transports.structured_io import StructuredIO

        sio = StructuredIO()

        async def callback():
            return "done"

        sio.create_hook_callback("cb-1", callback)
        result = sio.remove_hook_callback("cb-1")

        assert result is True
        assert "cb-1" not in sio._hooks

    def test_remove_nonexistent_hook_callback(self):
        """测试移除不存在的回调"""
        from scripts.transports.structured_io import StructuredIO

        sio = StructuredIO()
        result = sio.remove_hook_callback("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_invoke_hook(self):
        """测试调用 Hook"""
        from scripts.transports.structured_io import StructuredIO

        sio = StructuredIO()

        async def callback(x):
            return x * 2

        sio.create_hook_callback("cb-1", callback)
        result = await sio.invoke_hook("cb-1", 5)

        assert result == 10

    @pytest.mark.asyncio
    async def test_invoke_nonexistent_hook(self):
        """测试调用不存在的 Hook"""
        from scripts.transports.structured_io import StructuredIO

        sio = StructuredIO()

        with pytest.raises(ValueError, match="Unknown hook callback"):
            await sio.invoke_hook("nonexistent")


class TestParseNDJSONStream:
    """parse_ndjson_stream 测试"""

    @pytest.mark.asyncio
    async def test_parse_single_message(self):
        """测试解析单条消息"""
        from scripts.transports.structured_io import parse_ndjson_stream

        async def mock_stream():
            yield '{"id":"1","type":"test","data":{}}\n'

        messages = []
        async for msg in parse_ndjson_stream(mock_stream()):
            messages.append(msg)

        assert len(messages) == 1
        assert messages[0].id == "1"

    @pytest.mark.asyncio
    async def test_parse_multiple_messages(self):
        """测试解析多条消息"""
        from scripts.transports.structured_io import parse_ndjson_stream

        async def mock_stream():
            yield '{"id":"1","type":"test1","data":{}}\n'
            yield '{"id":"2","type":"test2","data":{}}\n'

        messages = []
        async for msg in parse_ndjson_stream(mock_stream()):
            messages.append(msg)

        assert len(messages) == 2
        assert messages[0].id == "1"
        assert messages[1].id == "2"

    @pytest.mark.asyncio
    async def test_parse_empty_lines(self):
        """测试解析空行"""
        from scripts.transports.structured_io import parse_ndjson_stream

        async def mock_stream():
            yield '{"id":"1","type":"test","data":{}}\n'
            yield '\n'
            yield '{"id":"2","type":"test","data":{}}\n'

        messages = []
        async for msg in parse_ndjson_stream(mock_stream()):
            messages.append(msg)

        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_parse_fragmented_json(self):
        """测试解析分片 JSON"""
        from scripts.transports.structured_io import parse_ndjson_stream

        async def mock_stream():
            yield '{"id":"1"'
            yield ',"type":"test"}\n'

        messages = []
        async for msg in parse_ndjson_stream(mock_stream()):
            messages.append(msg)

        assert len(messages) == 1


class TestCreateNDJSONStream:
    """create_ndjson_stream 测试"""

    @pytest.mark.asyncio
    async def test_create_single_message(self):
        """测试创建单条消息流"""
        from scripts.transports.structured_io import create_ndjson_stream, NDJSONMessage

        async def mock_messages():
            yield NDJSONMessage(id="1", type="test", data={})

        lines = []
        async for line in create_ndjson_stream(mock_messages()):
            lines.append(line)

        assert len(lines) == 1
        assert "1" in lines[0]
        assert lines[0].endswith("\n")

    @pytest.mark.asyncio
    async def test_create_multiple_messages(self):
        """测试创建多条消息流"""
        from scripts.transports.structured_io import create_ndjson_stream, NDJSONMessage

        async def mock_messages():
            yield NDJSONMessage(id="1", type="test1", data={})
            yield NDJSONMessage(id="2", type="test2", data={})

        lines = []
        async for line in create_ndjson_stream(mock_messages()):
            lines.append(line)

        assert len(lines) == 2
        assert all(line.endswith("\n") for line in lines)


class TestStructuredIOStartStop:
    """StructuredIO 启动停止测试"""

    @pytest.mark.asyncio
    async def test_start_sets_running(self):
        """测试启动设置运行标志"""
        from scripts.transports.structured_io import StructuredIO

        sio = StructuredIO()
        await sio.start()

        assert sio._running is True

        await sio.stop()

    @pytest.mark.asyncio
    async def test_stop_clears_running(self):
        """测试停止清除运行标志"""
        from scripts.transports.structured_io import StructuredIO

        sio = StructuredIO()
        await sio.start()
        await sio.stop()

        assert sio._running is False

    @pytest.mark.asyncio
    async def test_double_start(self):
        """测试重复启动"""
        from scripts.transports.structured_io import StructuredIO

        sio = StructuredIO()
        await sio.start()
        await sio.start()  # 不应抛出异常

        await sio.stop()

    @pytest.mark.asyncio
    async def test_double_stop(self):
        """测试重复停止"""
        from scripts.transports.structured_io import StructuredIO

        sio = StructuredIO()
        await sio.start()
        await sio.stop()
        await sio.stop()  # 不应抛出异常
