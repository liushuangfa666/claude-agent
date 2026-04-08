"""
Server 模块测试
"""
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestLockfile:
    """Lockfile 测试"""

    def test_lockfile_init(self):
        """测试锁文件初始化"""
        from scripts.server.lockfile import Lockfile

        lock = Lockfile()

        assert lock.lock_file is not None
        assert lock._handle is None
        assert lock._owned is False

    def test_lockfile_custom_path(self):
        """测试自定义锁文件路径"""
        from scripts.server.lockfile import Lockfile

        lock = Lockfile(lock_file="custom.lock")

        assert lock.lock_file == "custom.lock"

    def test_lockfile_is_locked_false_initially(self):
        """测试初始状态未锁定"""
        from scripts.server.lockfile import Lockfile

        lock = Lockfile()
        assert lock.is_locked() is False

    def test_lockfile_acquire_release(self):
        """测试获取和释放锁"""
        from scripts.server.lockfile import Lockfile

        lock = Lockfile()

        # 在新进程锁文件上操作应该可以获取
        result = lock.acquire()
        assert result is True
        assert lock.is_locked() is True

        lock.release()
        assert lock.is_locked() is False

    def test_lockfile_context_manager(self):
        """测试上下文管理器"""
        from scripts.server.lockfile import Lockfile

        lock = Lockfile()
        lock.acquire()  # 先获取锁

        # release后再次进入上下文
        lock.release()

        with lock as l:
            assert l is lock
            assert lock.is_locked() is True


class TestSessionMessage:
    """Session Message 数据类测试"""

    def test_message_creation(self):
        """测试消息创建"""
        import time
        from scripts.server.session import Message

        msg = Message(role="user", content="Hello")

        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.timestamp is not None
        assert msg.tokens == 0

    def test_message_with_tokens(self):
        """测试带 token 的消息"""
        from scripts.server.session import Message

        msg = Message(role="assistant", content="Hi", tokens=100)

        assert msg.tokens == 100


class TestUsageStats:
    """UsageStats 数据类测试"""

    def test_usage_stats_init(self):
        """测试使用统计初始化"""
        from scripts.server.session import UsageStats

        stats = UsageStats()

        assert stats.input_tokens == 0
        assert stats.output_tokens == 0
        assert stats.total_tokens == 0
        assert stats.request_count == 0


class TestSession:
    """Session 测试"""

    def test_session_creation(self):
        """测试会话创建"""
        from scripts.server.session import Session

        session = Session()

        assert session.id is not None
        assert len(session.messages) == 0
        assert session.created_at is not None
        assert session.last_active is not None

    def test_session_custom_id(self):
        """测试自定义会话 ID"""
        from scripts.server.session import Session

        session = Session(session_id="my-session")

        assert session.id == "my-session"

    @pytest.mark.asyncio
    async def test_process_message(self):
        """测试处理消息"""
        from scripts.server.session import Session

        session = Session()
        response = await session.process_message("Hello")

        assert response == "Echo: Hello"
        assert len(session.messages) == 2  # user + assistant

    @pytest.mark.asyncio
    async def test_stream_message(self):
        """测试流式处理消息"""
        from scripts.server.session import Session

        session = Session()
        events = []
        async for event in session.stream_message("Hello"):
            events.append(event)

        assert len(events) == 3
        assert events[0]["type"] == "thinking"
        assert events[1]["type"] == "text"
        assert events[2]["type"] == "done"

    def test_get_history(self):
        """测试获取历史"""
        from scripts.server.session import Session

        session = Session()
        session.messages.append(
            MagicMock(role="user", content="Hi", timestamp=1000.0)
        )
        session.messages.append(
            MagicMock(role="assistant", content="Hello", timestamp=1001.0)
        )

        history = session.get_history(limit=10)

        assert len(history) == 2
        assert history[0]["role"] == "user"

    def test_get_history_limit(self):
        """测试历史限制"""
        from scripts.server.session import Session

        session = Session()
        for i in range(10):
            session.messages.append(
                MagicMock(role="user", content=f"Msg {i}", timestamp=float(i))
            )

        history = session.get_history(limit=5)

        assert len(history) == 5

    def test_get_usage(self):
        """测试获取使用统计"""
        from scripts.server.session import Session

        session = Session()
        usage = session.get_usage()

        assert "input_tokens" in usage
        assert "output_tokens" in usage
        assert "total_tokens" in usage
        assert "request_count" in usage

    def test_to_dict(self):
        """测试转换为字典"""
        from scripts.server.session import Session

        session = Session(session_id="test-123")
        data = session.to_dict()

        assert data["id"] == "test-123"
        assert "created_at" in data
        assert "last_active" in data
        assert "message_count" in data


class TestSessionManager:
    """SessionManager 测试"""

    def test_manager_init(self):
        """测试管理器初始化"""
        from scripts.server.session import SessionManager

        manager = SessionManager()

        assert manager._sessions == {}
        assert manager.count() == 0

    def test_create_session(self):
        """测试创建会话"""
        from scripts.server.session import SessionManager

        manager = SessionManager()
        session = manager.create()

        assert session is not None
        assert manager.count() == 1

    def test_get_session(self):
        """测试获取会话"""
        from scripts.server.session import SessionManager

        manager = SessionManager()
        created = manager.create()
        found = manager.get(created.id)

        assert found is created

    def test_get_nonexistent_session(self):
        """测试获取不存在的会话"""
        from scripts.server.session import SessionManager

        manager = SessionManager()
        found = manager.get("nonexistent")

        assert found is None

    def test_get_or_create_existing(self):
        """测试获取已存在的会话"""
        from scripts.server.session import SessionManager

        manager = SessionManager()
        created = manager.create()

        found = manager.get_or_create(created.id)

        assert found is created
        assert manager.count() == 1

    def test_get_or_create_new(self):
        """测试获取或创建新会话"""
        from scripts.server.session import SessionManager

        manager = SessionManager()
        found = manager.get_or_create("")

        assert found is not None
        assert manager.count() == 1

    def test_delete_session(self):
        """测试删除会话"""
        from scripts.server.session import SessionManager

        manager = SessionManager()
        session = manager.create()

        result = manager.delete(session.id)

        assert result is True
        assert manager.count() == 0

    def test_delete_nonexistent_session(self):
        """测试删除不存在的会话"""
        from scripts.server.session import SessionManager

        manager = SessionManager()
        result = manager.delete("nonexistent")

        assert result is False

    def test_list_sessions(self):
        """测试列出所有会话"""
        from scripts.server.session import SessionManager

        manager = SessionManager()
        manager.create()
        manager.create()

        sessions = manager.list()

        assert len(sessions) == 2

    def test_get_stats(self):
        """测试获取统计信息"""
        from scripts.server.session import SessionManager

        manager = SessionManager()
        stats = manager.get_stats()

        assert "session_count" in stats
        assert "total_usage" in stats
        assert stats["session_count"] == 0

    def test_get_usage(self):
        """测试获取使用统计"""
        from scripts.server.session import SessionManager

        manager = SessionManager()
        usage = manager.get_usage()

        assert "input_tokens" in usage
        assert "output_tokens" in usage
        assert "total_tokens" in usage
        assert "request_count" in usage


class TestServerInit:
    """Server 初始化测试"""

    def test_server_init_defaults(self):
        """测试服务器默认初始化"""
        with patch("scripts.server.server.web"):
            from scripts.server.server import Server

            server = Server()

            assert server.host == "0.0.0.0"
            assert server.port == 18780
            assert server.on_chat is None
            assert server.app is not None
            assert server.session_manager is not None
            assert server.lockfile is not None

    def test_server_init_custom(self):
        """测试服务器自定义初始化"""
        with patch("scripts.server.server.web"):
            from scripts.server.server import Server

            server = Server(host="127.0.0.1", port=8080)

            assert server.host == "127.0.0.1"
            assert server.port == 8080


class TestServerRoutes:
    """Server 路由测试"""

    @pytest.mark.asyncio
    async def test_handle_chat_valid_message(self):
        """测试处理聊天请求"""
        from scripts.server.server import Server

        server = Server()

        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={
            "session_id": "test-session",
            "message": "Hello",
            "stream": False
        })

        response = await server.handle_chat(mock_request)

        # 验证返回的是 json_response
        assert response.status == 200

    @pytest.mark.asyncio
    async def test_handle_chat_missing_message(self):
        """测试缺少消息的请求"""
        from scripts.server.server import Server

        server = Server()

        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={
            "session_id": "test-session",
            "message": "",
            "stream": False
        })

        response = await server.handle_chat(mock_request)

        assert response.status == 400

    @pytest.mark.asyncio
    async def test_handle_chat_invalid_json(self):
        """测试无效 JSON 请求"""
        from scripts.server.server import Server

        server = Server()

        mock_request = MagicMock()
        mock_request.json = AsyncMock(
            side_effect=json.JSONDecodeError("Invalid", "", 0)
        )

        response = await server.handle_chat(mock_request)

        assert response.status == 400

    @pytest.mark.asyncio
    async def test_handle_status(self):
        """测试状态检查端点"""
        from scripts.server.server import Server

        server = Server()
        server._running = True

        mock_request = MagicMock()

        response = await server.handle_status(mock_request)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_handle_stats(self):
        """测试统计信息端点"""
        from scripts.server.server import Server

        server = Server()

        mock_request = MagicMock()

        response = await server.handle_stats(mock_request)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_handle_session_create(self):
        """测试创建会话"""
        from scripts.server.server import Server

        server = Server()

        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={
            "action": "create"
        })

        response = await server.handle_session(mock_request)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_handle_session_get(self):
        """测试获取会话"""
        from scripts.server.server import Server

        server = Server()
        session = server.session_manager.create()

        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={
            "action": "get",
            "session_id": session.id
        })

        response = await server.handle_session(mock_request)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_handle_session_get_not_found(self):
        """测试获取不存在的会话"""
        from scripts.server.server import Server

        server = Server()

        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={
            "action": "get",
            "session_id": "nonexistent"
        })

        response = await server.handle_session(mock_request)

        assert response.status == 404

    @pytest.mark.asyncio
    async def test_handle_session_delete(self):
        """测试删除会话"""
        from scripts.server.server import Server

        server = Server()
        session = server.session_manager.create()

        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={
            "action": "delete",
            "session_id": session.id
        })

        response = await server.handle_session(mock_request)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_handle_session_invalid_action(self):
        """测试无效的会话操作"""
        from scripts.server.server import Server

        server = Server()

        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={
            "action": "invalid"
        })

        response = await server.handle_session(mock_request)

        assert response.status == 400

    @pytest.mark.asyncio
    async def test_handle_sessions(self):
        """测试列出所有会话"""
        from scripts.server.server import Server

        server = Server()
        server.session_manager.create()
        server.session_manager.create()

        mock_request = MagicMock()

        response = await server.handle_sessions(mock_request)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_handle_history(self):
        """测试获取对话历史"""
        from scripts.server.server import Server

        server = Server()
        session = server.session_manager.create()

        mock_request = MagicMock()
        mock_request.query.get = lambda key, default=None: session.id if key == "session_id" else "50"

        response = await server.handle_history(mock_request)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_handle_history_missing_session_id(self):
        """测试缺少 session_id"""
        from scripts.server.server import Server

        server = Server()

        mock_request = MagicMock()
        mock_request.query.get = lambda key, default=None: None if key == "session_id" else "50"

        response = await server.handle_history(mock_request)

        assert response.status == 400

    @pytest.mark.asyncio
    async def test_handle_history_not_found(self):
        """测试会话不存在"""
        from scripts.server.server import Server

        server = Server()

        mock_request = MagicMock()
        mock_request.query.get = lambda key, default=None: "nonexistent" if key == "session_id" else "50"

        response = await server.handle_history(mock_request)

        assert response.status == 404

    @pytest.mark.asyncio
    async def test_handle_usage_with_session(self):
        """测试获取会话使用统计"""
        from scripts.server.server import Server

        server = Server()
        session = server.session_manager.create()

        mock_request = MagicMock()
        mock_request.query.get = lambda key, default=None: session.id if key == "session_id" else None

        response = await server.handle_usage(mock_request)

        assert response.status == 200

    @pytest.mark.asyncio
    async def test_handle_usage_global(self):
        """测试获取全局使用统计"""
        from scripts.server.server import Server

        server = Server()

        mock_request = MagicMock()
        mock_request.query.get = lambda key, default=None: None

        response = await server.handle_usage(mock_request)

        assert response.status == 200


class TestServerLifecycle:
    """Server 生命周期测试"""

    @pytest.mark.asyncio
    async def test_start_server(self):
        """测试启动服务器"""
        from scripts.server.server import Server

        server = Server()
        server.lockfile.acquire = MagicMock(return_value=True)
        server.lockfile.release = MagicMock()

        mock_runner = MagicMock()
        mock_runner.setup = AsyncMock()
        mock_runner.cleanup = AsyncMock()
        mock_site = MagicMock()
        mock_site.start = AsyncMock()
        mock_site.stop = AsyncMock()

        with patch("scripts.server.server.web.AppRunner", return_value=mock_runner):
            with patch("scripts.server.server.web.TCPSite", return_value=mock_site):
                await server.start()

        assert server._running is True
        assert server.runner is not None

        await server.stop()

    @pytest.mark.asyncio
    async def test_start_server_lock_failed(self):
        """测试启动服务器但锁获取失败"""
        from scripts.server.server import Server

        server = Server()
        server.lockfile.acquire = MagicMock(return_value=False)

        with pytest.raises(RuntimeError, match="Another instance is running"):
            await server.start()

    @pytest.mark.asyncio
    async def test_stop_server(self):
        """测试停止服务器"""
        from scripts.server.server import Server

        server = Server()
        server._running = True

        mock_site = MagicMock()
        mock_site.stop = AsyncMock()
        mock_runner = MagicMock()
        mock_runner.cleanup = AsyncMock()
        server.site = mock_site
        server.runner = mock_runner

        await server.stop()

        assert server._running is False
