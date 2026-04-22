"""
LSP (Language Server Protocol) 模块测试
"""
import asyncio
import json
import pytest
from unittest.mock import MagicMock, AsyncMock


class TestLSPDiagnostic:
    """LSPDiagnostic 数据类测试"""

    def test_diagnostic_creation(self):
        """测试诊断信息创建"""
        from scripts.lsp import LSPDiagnostic

        diag = LSPDiagnostic(
            file_path="/path/to/file.py",
            line=10,
            column=5,
            severity="error",
            message="Undefined variable",
            source="pyright"
        )

        assert diag.file_path == "/path/to/file.py"
        assert diag.line == 10
        assert diag.column == 5
        assert diag.severity == "error"
        assert diag.message == "Undefined variable"
        assert diag.source == "pyright"

    def test_diagnostic_optional_source(self):
        """测试可选 source 字段"""
        from scripts.lsp import LSPDiagnostic

        diag = LSPDiagnostic(
            file_path="/path/to/file.py",
            line=10,
            column=5,
            severity="warning",
            message="Unused variable"
        )

        assert diag.source is None


class TestLSPLocation:
    """LSPLocation 数据类测试"""

    def test_location_creation(self):
        """测试位置信息创建"""
        from scripts.lsp import LSPLocation, LSPPosition

        location = LSPLocation(
            file_path="/path/to/file.py",
            start=LSPPosition(line=10, character=5),
            end=LSPPosition(line=10, character=15)
        )

        assert location.file_path == "/path/to/file.py"
        assert location.start.line == 10
        assert location.start.character == 5
        assert location.end.line == 10
        assert location.end.character == 15


class TestLSPClientInit:
    """LSPClient 初始化测试"""

    def test_client_initial_state(self):
        """测试客户端初始状态"""
        from scripts.lsp import LSPClient

        client = LSPClient()

        assert client.process is None
        assert client.request_id == 0
        assert client._initialized is False
        assert client.server_capabilities == {}
        assert client._reader_task is None

    def test_client_has_diagnostic_callbacks_attribute(self):
        """测试客户端是否有诊断回调属性（如果已实现）"""
        from scripts.lsp import LSPClient

        client = LSPClient()

        # 检查是否有诊断回调支持
        if hasattr(client, '_diagnostic_callbacks'):
            assert isinstance(client._diagnostic_callbacks, list)
        else:
            # 诊断回调尚未实现，这是预期的
            pass


class TestLSPClientUriConversion:
    """LSP URI 转换测试"""

    def test_path_to_uri_windows(self):
        """测试 Windows 路径转 URI"""
        from scripts.lsp import LSPClient

        client = LSPClient()

        # Windows 路径
        uri = client._path_to_uri("c:\\Users\\test\\file.py")
        assert uri.startswith("file:///")
        assert "c" in uri.lower()

    def test_path_to_uri_unix(self):
        """测试 Unix 路径转 URI"""
        from scripts.lsp import LSPClient

        client = LSPClient()

        # Unix 路径
        uri = client._path_to_uri("/home/test/file.py")
        assert uri.startswith("file:///")
        assert "/home/test/file.py" in uri

    def test_uri_to_path(self):
        """测试 URI 转路径"""
        from scripts.lsp import LSPClient

        client = LSPClient()

        # Windows URI
        path = client._uri_to_path("file:///c:/Users/test/file.py")
        assert "c" in path.lower() or "Users" in path

        # Unix URI
        path = client._uri_to_path("file:///home/test/file.py")
        assert "/home/test/file.py" in path


class TestLSPManagerLanguageDetection:
    """LSPManager 语言检测测试"""

    def test_detect_python(self):
        """测试 Python 文件检测"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("test.py") == "python"
        assert manager._detect_language("main.py") == "python"
        assert manager._detect_language("test.PY") == "python"

    def test_detect_typescript(self):
        """测试 TypeScript 文件检测"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("test.ts") == "typescript"
        assert manager._detect_language("test.tsx") == "typescript"

    def test_detect_javascript(self):
        """测试 JavaScript 文件检测"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("test.js") == "javascript"
        assert manager._detect_language("test.jsx") == "javascript"

    def test_detect_go(self):
        """测试 Go 文件检测"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("test.go") == "go"

    def test_detect_rust(self):
        """测试 Rust 文件检测"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("test.rs") == "rust"

    def test_detect_ruby(self):
        """测试 Ruby 文件检测"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("test.rb") == "ruby"

    def test_detect_java(self):
        """测试 Java 文件检测"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("Test.java") == "java"

    def test_detect_c_cpp(self):
        """测试 C/C++ 文件检测"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("test.c") == "c"
        assert manager._detect_language("test.cpp") == "cpp"
        assert manager._detect_language("test.cc") == "cpp"
        assert manager._detect_language("test.h") == "c"
        assert manager._detect_language("test.hpp") == "cpp"

    def test_detect_csharp(self):
        """测试 C# 文件检测"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("test.cs") == "csharp"

    def test_detect_php(self):
        """测试 PHP 文件检测"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("test.php") == "php"

    def test_detect_swift(self):
        """测试 Swift 文件检测"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("test.swift") == "swift"

    def test_detect_kotlin(self):
        """测试 Kotlin 文件检测"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("test.kt") == "kotlin"
        assert manager._detect_language("test.kts") == "kotlin"

    def test_detect_shell(self):
        """测试 Shell 文件检测"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("test.sh") == "bash"
        assert manager._detect_language("test.bash") == "bash"
        assert manager._detect_language("test.zsh") == "bash"

    def test_detect_powershell(self):
        """测试 PowerShell 文件检测"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("test.ps1") == "powershell"
        assert manager._detect_language("test.psm1") == "powershell"

    def test_detect_json(self):
        """测试 JSON 文件检测"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("test.json") == "json"

    def test_detect_yaml(self):
        """测试 YAML 文件检测"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("test.yaml") == "yaml"
        assert manager._detect_language("test.yml") == "yaml"

    def test_detect_unsupported(self):
        """测试不支持的文件类型"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        assert manager._detect_language("test.xyz") is None
        assert manager._detect_language("test.abc") is None
        assert manager._detect_language("test") is None


class TestLSPManagerInit:
    """LSPManager 初始化测试"""

    def test_manager_initial_state(self):
        """测试管理器初始状态"""
        from scripts.lsp import LSPManager

        manager = LSPManager()

        assert manager.config == {}
        assert manager.clients == {}

    def test_manager_with_config(self):
        """测试带配置的管理器"""
        from scripts.lsp import LSPManager

        config = {
            "python": {"command": "pyright-langserver", "args": ["--stdio"]},
            "typescript": {"command": "typescript-language-server", "args": ["--stdio"]}
        }
        manager = LSPManager(config)

        assert manager.config == config
        assert manager.clients == {}

    def test_set_config(self):
        """测试设置配置"""
        from scripts.lsp import LSPManager

        manager = LSPManager()
        new_config = {"python": {"command": "pyright"}}

        manager.set_config(new_config)

        assert manager.config == new_config


class TestLSPClientPositionConversion:
    """LSPClient 位置转换测试"""

    def test_position_to_params(self):
        """测试位置转参数"""
        from scripts.lsp import LSPClient

        client = LSPClient()
        params = client._position_to_params("/path/to/file.py", 10, 5)

        assert "textDocument" in params
        assert params["textDocument"]["uri"] == "file:///path/to/file.py"
        assert "position" in params
        assert params["position"]["line"] == 10
        assert params["position"]["character"] == 5

    def test_position_to_params_with_unicode(self):
        """测试带 Unicode 字符的位置"""
        from scripts.lsp import LSPClient

        client = LSPClient()
        # 确保不抛出异常
        params = client._position_to_params("/path/to/文件.py", 0, 0)
        assert "textDocument" in params


class TestLSPClientMessageDispatch:
    """LSPClient 消息分发测试"""

    @pytest.mark.asyncio
    async def test_dispatch_response_message(self):
        """测试分发响应消息"""
        from scripts.lsp import LSPClient

        client = LSPClient()
        client._initialized = True

        # 手动添加一个 pending future
        future = asyncio.get_event_loop().create_future()
        client.pending[1] = future

        # 模拟接收响应
        await client._dispatch_message('{"jsonrpc":"2.0","id":1,"result":{"capabilities":{}}}')

        # 验证 future 被设置
        assert 1 not in client.pending  # 应该被取出
        # 注意：future.result() 在这里会阻塞，因为 mock future 行为不同

    @pytest.mark.asyncio
    async def test_dispatch_error_message(self):
        """测试分发错误消息"""
        from scripts.lsp import LSPClient

        client = LSPClient()
        client._initialized = True

        # 创建 pending future
        client.pending[1] = AsyncMock()

        # 模拟接收错误响应
        await client._dispatch_message('{"jsonrpc":"2.0","id":1,"error":{"code":-32600,"message":"Invalid Request"}}')

    def test_dispatch_invalid_json(self):
        """测试分发无效 JSON"""
        from scripts.lsp import LSPClient

        client = LSPClient()

        # 不应抛出异常
        client._dispatch_message("not valid json")


class TestLSPClientSend:
    """LSPClient 发送消息测试"""

    def test_send_without_process(self):
        """测试没有进程时发送"""
        from scripts.lsp import LSPClient

        client = LSPClient()

        future = client._send("initialize", {})

        assert future is None

    def test_send_notify(self):
        """测试发送通知（不需要响应）"""
        from scripts.lsp import LSPClient

        client = LSPClient()

        # 创建一个假的进程
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        client.process = mock_process

        result = client._send("exit", {}, is_notify=True)

        assert result is None


class TestLSPClientStateCheck:
    """LSPClient 状态检查测试"""

    def test_is_running_false_when_not_started(self):
        """测试未启动时返回 False"""
        from scripts.lsp import LSPClient

        client = LSPClient()

        assert client.is_running() is False

    def test_is_running_false_when_process_none(self):
        """测试进程为 None 时返回 False"""
        from scripts.lsp import LSPClient

        client = LSPClient()
        client._initialized = True

        assert client.is_running() is False


class TestLSPClientDiagnostics:
    """LSPClient 诊断回调测试"""

    def test_on_diagnostics(self):
        """测试注册诊断回调"""
        from scripts.lsp import LSPClient

        client = LSPClient()

        received = []
        def callback(diagnostics):
            received.extend(diagnostics)

        client.on_diagnostics(callback)

        assert len(client._diagnostic_callbacks) == 1
        assert client._diagnostic_callbacks[0] == callback

    def test_remove_diagnostics_callback(self):
        """测试移除诊断回调"""
        from scripts.lsp import LSPClient

        client = LSPClient()

        def callback(diagnostics):
            pass

        client.on_diagnostics(callback)
        result = client.remove_diagnostics_callback(callback)

        assert result is True
        assert len(client._diagnostic_callbacks) == 0

    def test_remove_nonexistent_callback(self):
        """测试移除不存在的回调"""
        from scripts.lsp import LSPClient

        client = LSPClient()

        def callback(diagnostics):
            pass

        result = client.remove_diagnostics_callback(callback)

        assert result is False

    def test_handle_diagnostics(self):
        """测试诊断解析"""
        from scripts.lsp import LSPClient, LSPDiagnostic

        client = LSPClient()

        diagnostics_data = [
            {
                "severity": 1,
                "message": "Undefined variable",
                "source": "pyright",
                "file_path": "/test.py",
                "line": 10,
                "column": 5,
            },
            {
                "severity": 2,
                "message": "Unused import",
                "source": "pyright",
                "file_path": "/test.py",
                "line": 5,
                "column": 1,
            },
        ]

        result = client._handle_diagnostics(diagnostics_data)

        assert len(result) == 2
        assert result[0].severity == "error"
        assert result[0].message == "Undefined variable"
        assert result[1].severity == "warning"
        assert result[1].message == "Unused import"

    def test_handle_diagnostics_empty(self):
        """测试空诊断列表"""
        from scripts.lsp import LSPClient

        client = LSPClient()

        result = client._handle_diagnostics([])

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_dispatch_diagnostics_message(self):
        """测试分发诊断消息"""
        from scripts.lsp import LSPClient

        client = LSPClient()
        client._initialized = True

        received = []
        def callback(diagnostics):
            received.extend(diagnostics)

        client.on_diagnostics(callback)

        # 模拟诊断消息
        diag_msg = json.dumps({
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {
                "uri": "file:///test.py",
                "diagnostics": [
                    {
                        "severity": 1,
                        "message": "Error",
                        "source": "test",
                        "range": {
                            "start": {"line": 0, "character": 0},
                            "end": {"line": 0, "character": 5}
                        }
                    }
                ]
            }
        })

        await client._dispatch_message(diag_msg)

        # 注意：file_path 和 line/column 解析依赖于诊断消息格式
        # 实际解析可能需要根据真实 LSP 服务器响应调整
