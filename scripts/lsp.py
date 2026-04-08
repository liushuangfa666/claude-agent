"""
LSP (Language Server Protocol) 客户端实现

用于启动和管理语言服务器，获取代码语义信息（定义、类型、诊断等）
"""
import asyncio
import json
import os
import subprocess
import threading
from dataclasses import dataclass
from typing import Any, Callable

LSPServerInfo = dict[str, str]


@dataclass
class LSPDiagnostic:
    """LSP 诊断信息"""
    file_path: str
    line: int
    column: int
    severity: str  # error, warning, info, hint
    message: str
    source: str | None = None


@dataclass
class LSPPosition:
    line: int
    character: int


@dataclass
class LSPLocation:
    file_path: str
    start: LSPPosition
    end: LSPPosition


class LSPClient:
    """
    LSP 客户端，管理与语言服务器的通信

    使用方式：
    ```python
    client = LSPClient()
    await client.start("python", {"command": "pyright-langserver", "args": ["--stdio"]})
    definitions = await client.get_definitions("src/main.py", 10, 5)
    await client.stop()
    ```
    """

    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.request_id = 0
        self.lock = threading.Lock()
        self.pending: dict[int, asyncio.Future] = {}
        self._initialized = False
        self.server_capabilities: dict[str, Any] = {}
        self._reader_task: asyncio.Task | None = None
        self._stdout_reader: asyncio.StreamReader | None = None
        self._diagnostic_callbacks: list[Callable] = []

    async def start(
        self,
        language: str,
        config: dict[str, Any],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> LSPServerInfo | None:
        """
        启动 LSP 服务器

        Args:
            language: 语言标识 (python, typescript, go, etc.)
            config: LSP 配置，包含 command, args, env 等
            cwd: 工作目录，默认为当前目录
            env: 环境变量
            timeout: 初始化超时时间（秒）

        Returns:
            服务器信息，包含 name, version 等
        """
        if self.process is not None:
            await self.stop()

        command = config.get("command", "")
        args = config.get("args", [])
        server_env = config.get("env", {})

        if not command:
            raise ValueError(f"No command specified for LSP server: {language}")

        # 合并环境变量
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
        full_env.update(server_env)

        # 启动进程
        try:
            self.process = subprocess.Popen(
                [command] + args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd or os.getcwd(),
                env=full_env,
                text=False,  # binary mode for JSON-RPC
            )
        except FileNotFoundError:
            raise RuntimeError(f"LSP server command not found: {command}")

        # 设置 stderr 读取
        self._stderr_task = asyncio.create_task(self._read_stderr())

        # 启动读取循环
        self._reader_task = asyncio.create_task(self._read_messages())

        # 初始化
        result = await self._initialize(timeout=timeout)
        self._initialized = True

        return result

    async def _read_stderr(self):
        """读取 stderr（用于日志）"""
        if self.process and self.process.stderr:
            try:
                while True:
                    line = await asyncio.get_event_loop().run_in_executor(
                        None, self.process.stderr.readline
                    )
                    if not line:
                        break
                    # 可以选择记录 stderr 日志
            except Exception:
                pass

    async def _read_messages(self):
        """持续读取 LSP 服务器的消息"""
        if not self.process or not self.process.stdout:
            return

        try:
            while True:
                # 读取 Content-Length header
                headers = {}
                while True:
                    line = await asyncio.get_event_loop().run_in_executor(
                        None, self.process.stdout.readline
                    )
                    if not line:
                        return
                    line = line.decode("utf-8").strip()
                    if not line:
                        break
                    if ":" in line:
                        key, value = line.split(":", 1)
                        headers[key.strip().lower()] = value.strip()

                content_length = int(headers.get("content-length", 0))
                if content_length == 0:
                    continue

                # 读取内容
                body = b""
                while len(body) < content_length:
                    chunk = await asyncio.get_event_loop().run_in_executor(
                        None, self.process.stdout.read, content_length - len(body)
                    )
                    if not chunk:
                        break
                    body += chunk

                if body:
                    await self._dispatch_message(body.decode("utf-8"))
        except Exception:
            pass

    def on_diagnostics(self, callback: Callable[[list[LSPDiagnostic]], None]) -> None:
        """
        注册诊断回调函数

        Args:
            callback: 回调函数，接收诊断列表
        """
        self._diagnostic_callbacks.append(callback)

    def remove_diagnostics_callback(self, callback: Callable[[list[LSPDiagnostic]], None]) -> bool:
        """
        移除诊断回调函数

        Args:
            callback: 要移除的回调函数

        Returns:
            是否成功移除
        """
        if callback in self._diagnostic_callbacks:
            self._diagnostic_callbacks.remove(callback)
            return True
        return False

    def _handle_diagnostics(self, diagnostics: list[dict]) -> list[LSPDiagnostic]:
        """
        处理诊断消息

        Args:
            diagnostics: LSP 诊断列表

        Returns:
            解析后的诊断列表
        """
        result = []
        for diag in diagnostics:
            severity = "info"
            severity_num = diag.get("severity", 2)
            if severity_num == 1:
                severity = "error"
            elif severity_num == 2:
                severity = "warning"
            elif severity_num == 3:
                severity = "info"
            elif severity_num == 4:
                severity = "hint"

            result.append(LSPDiagnostic(
                file_path=diag.get("file_path", ""),
                line=diag.get("line", 0),
                column=diag.get("column", 0),
                severity=severity,
                message=diag.get("message", ""),
                source=diag.get("source"),
            ))
        return result

    async def _dispatch_message(self, body: str):
        """分发接收到的消息"""
        try:
            msg = json.loads(body)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("method", "")
        if msg_type:
            # 处理服务器主动发来的消息（如 $/cancelRequest, diagnostics 等）
            if msg_type == "textDocument/publishDiagnostics":
                # 处理诊断消息
                params = msg.get("params", {})
                uri = params.get("uri", "")
                diagnostics = params.get("diagnostics", [])

                # 解析诊断
                parsed = self._handle_diagnostics(diagnostics)

                # 调用所有回调
                for callback in self._diagnostic_callbacks:
                    try:
                        callback(parsed)
                    except Exception:
                        pass
        else:
            # 处理响应
            msg_id = msg.get("id")
            if msg_id is not None and msg_id in self.pending:
                future = self.pending.pop(msg_id)
                if "error" in msg:
                    future.set_exception(Exception(str(msg["error"])))
                else:
                    future.set_result(msg.get("result"))

    def _send(self, method: str, params: dict | None = None, is_notify: bool = False) -> asyncio.Future | None:
        """发送 JSON-RPC 请求"""
        if not self.process or self.process.stdin is None:
            return None

        with self.lock:
            self.request_id += 1
            req_id = self.request_id

        message = {
            "jsonrpc": "2.0",
            "id": req_id if not is_notify else None,
            "method": method,
        }
        if params is not None:
            message["params"] = params

        body = json.dumps(message, ensure_ascii=False)

        # 写入 Content-Length header
        header = f"Content-Length: {len(body)}\r\n\r\n"
        data = (header + body).encode("utf-8")

        try:
            self.process.stdin.write(data)
            self.process.stdin.flush()
        except BrokenPipeError:
            raise RuntimeError("LSP server process has terminated")

        if is_notify:
            return None

        # 创建 Future 等待响应
        future = asyncio.get_event_loop().create_future()
        self.pending[req_id] = future
        return future

    async def _initialize(self, timeout: int = 30) -> LSPServerInfo | None:
        """发送 initialize 请求"""
        future = self._send("initialize", {
            "processId": os.getpid(),
            "rootUri": self._path_to_uri(os.getcwd()),
            "capabilities": {
                "workspace": {
                    "applyEdit": True,
                    "workspaceFolders": True,
                },
                "textDocument": {
                    "synchronization": {
                        "didSave": True,
                    },
                },
            },
        })

        if not future:
            return None

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            self.server_capabilities = result.get("capabilities", {}) if result else {}
            return result.get("serverInfo")
        except asyncio.TimeoutError:
            raise TimeoutError(f"LSP initialize timeout after {timeout}s")
        except Exception as e:
            raise RuntimeError(f"LSP initialize failed: {e}")
        finally:
            # 发送 initialized 通知
            self._send("initialized", {"capabilities": {}}, is_notify=True)

    async def initialized(self):
        """通知服务器初始化完成"""
        self._send("initialized", {}, is_notify=True)
        await asyncio.sleep(0.1)  # 给服务器一点时间

    def _path_to_uri(self, file_path: str) -> str:
        """将文件路径转换为 file URI"""
        # 处理 Windows 路径
        if os.path.isabs(file_path):
            # Windows: C:\path\to\file -> file:///C:/path/to/file
            file_path = file_path.replace("\\", "/")
            if len(file_path) > 1 and file_path[1] == ":":
                file_path = file_path[0] + ":" + file_path[1:]
                return f"file:///{file_path}"
            return f"file://{file_path}"
        return f"file://{os.getcwd()}/{file_path}"

    def _uri_to_path(self, uri: str) -> str:
        """将 file URI 转换为文件路径"""
        if uri.startswith("file://"):
            path = uri[7:]
            # Windows: /C:/path/to/file -> C:\path\to\file
            if len(path) > 2 and path[0] == "/" and path[2] == ":":
                path = path[1] + ":" + path[2:].replace("/", "\\")
            return path
        return uri

    def _position_to_params(self, file_path: str, line: int, character: int) -> dict:
        """将位置转换为 textDocument/position 的参数"""
        return {
            "textDocument": {"uri": self._path_to_uri(file_path)},
            "position": {"line": line, "character": character},
        }

    async def get_definitions(
        self, file_path: str, line: int, character: int
    ) -> list[LSPLocation]:
        """
        获取光标位置的定义（Go to Definition）

        Args:
            file_path: 文件路径
            line: 行号（0-based）
            character: 列号（0-based）

        Returns:
            定义位置的列表
        """
        if not self._initialized:
            return []

        future = self._send(
            "textDocument/definition",
            self._position_to_params(file_path, line, character)
        )

        if not future:
            return []

        try:
            result = await asyncio.wait_for(future, timeout=10)
            if not result:
                return []

            locations = []
            items = result if isinstance(result, list) else [result]

            for item in items:
                uri = item.get("uri", "")
                start = item.get("range", {}).get("start", {})
                end = item.get("range", {}).get("end", {})
                locations.append(LSPLocation(
                    file_path=self._uri_to_path(uri),
                    start=LSPPosition(start.get("line", 0), start.get("character", 0)),
                    end=LSPPosition(end.get("line", 0), end.get("character", 0)),
                ))
            return locations
        except (asyncio.TimeoutError, Exception):
            return []

    async def get_hover(
        self, file_path: str, line: int, character: int
    ) -> str | None:
        """
        获取光标位置的 Hover 信息（类型、文档）

        Args:
            file_path: 文件路径
            line: 行号（0-based）
            character: 列号（0-based）

        Returns:
            Hover 文本或 None
        """
        if not self._initialized:
            return None

        future = self._send(
            "textDocument/hover",
            self._position_to_params(file_path, line, character)
        )

        if not future:
            return None

        try:
            result = await asyncio.wait_for(future, timeout=10)
            if not result:
                return None

            contents = result.get("contents", {})
            if isinstance(contents, str):
                return contents
            elif isinstance(contents, dict):
                # LSP MarkupContent
                return contents.get("value") or contents.get("string")
            return None
        except (asyncio.TimeoutError, Exception):
            return None

    async def get_type_definition(
        self, file_path: str, line: int, character: int
    ) -> list[LSPLocation]:
        """获取类型定义（Go to Type Definition）"""
        if not self._initialized:
            return []

        future = self._send(
            "textDocument/typeDefinition",
            self._position_to_params(file_path, line, character)
        )

        if not future:
            return []

        try:
            result = await asyncio.wait_for(future, timeout=10)
            if not result:
                return []

            locations = []
            items = result if isinstance(result, list) else [result]

            for item in items:
                uri = item.get("uri", "")
                start = item.get("range", {}).get("start", {})
                end = item.get("range", {}).get("end", {})
                locations.append(LSPLocation(
                    file_path=self._uri_to_path(uri),
                    start=LSPPosition(start.get("line", 0), start.get("character", 0)),
                    end=LSPPosition(end.get("line", 0), end.get("character", 0)),
                ))
            return locations
        except (asyncio.TimeoutError, Exception):
            return []

    async def get_references(
        self, file_path: str, line: int, character: int, include_declaration: bool = True
    ) -> list[LSPLocation]:
        """获取引用（Find References）"""
        if not self._initialized:
            return []

        future = self._send(
            "textDocument/references",
            {
                **self._position_to_params(file_path, line, character),
                "context": {"includeDeclaration": include_declaration},
            }
        )

        if not future:
            return []

        try:
            result = await asyncio.wait_for(future, timeout=10)
            if not result:
                return []

            locations = []
            for item in result:
                uri = item.get("uri", "")
                start = item.get("range", {}).get("start", {})
                end = item.get("range", {}).get("end", {})
                locations.append(LSPLocation(
                    file_path=self._uri_to_path(uri),
                    start=LSPPosition(start.get("line", 0), start.get("character", 0)),
                    end=LSPPosition(end.get("line", 0), end.get("character", 0)),
                ))
            return locations
        except (asyncio.TimeoutError, Exception):
            return []

    async def get_document_symbols(self, file_path: str) -> list[dict]:
        """获取文档符号（Outline/文件结构）"""
        if not self._initialized:
            return []

        future = self._send(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": self._path_to_uri(file_path)}}
        )

        if not future:
            return []

        try:
            result = await asyncio.wait_for(future, timeout=10)
            return result if isinstance(result, list) else []
        except (asyncio.TimeoutError, Exception):
            return []

    async def shutdown(self):
        """发送 shutdown 请求"""
        if self._initialized:
            future = self._send("shutdown")
            if future:
                try:
                    await asyncio.wait_for(future, timeout=5)
                except Exception:
                    pass
            self._initialized = False

    async def stop(self):
        """停止 LSP 服务器"""
        self._initialized = False

        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None

        if self.process:
            try:
                # 发送 exit 通知
                self._send("exit", {}, is_notify=True)
                await asyncio.sleep(0.1)
            except Exception:
                pass

            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception:
                pass

            self.process = None

        # 清理 pending futures
        for future in self.pending.values():
            future.cancel()
        self.pending.clear()

    def is_running(self) -> bool:
        """检查服务器是否正在运行"""
        return self._initialized and self.process is not None and self.process.poll() is None


class LSPManager:
    """
    LSP 管理器，管理多个语言的 LSP 客户端

    使用方式：
    ```python
    manager = LSPManager()
    await manager.start_for_file("src/main.py")  # 根据文件类型启动对应 LSP
    definitions = await manager.get_definitions("src/main.py", 10, 5)
    await manager.stop_all()
    ```
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化 LSP 管理器

        Args:
            config: LSP 配置，格式为 {"python": {"command": "..."}, "go": {...}}
        """
        self.config: dict[str, Any] = config or {}
        self.clients: dict[str, LSPClient] = {}

    def set_config(self, config: dict[str, Any]):
        """设置 LSP 配置"""
        self.config = config

    def _detect_language(self, file_path: str) -> str | None:
        """根据文件扩展名检测语言"""
        ext = os.path.splitext(file_path)[1].lower()
        mapping = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".java": "java",
            ".c": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".kts": "kotlin",
            ".scala": "scala",
            ".lua": "lua",
            ".r": "r",
            ".rkt": "racket",
            ".sh": "bash",
            ".bash": "bash",
            ".zsh": "bash",
            ".ps1": "powershell",
            ".psm1": "powershell",
            ".ex": "elixir",
            ".exs": "elixir",
            ".erl": "erlang",
            ".nix": "nix",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".xml": "xml",
            ".html": "html",
            ".css": "css",
            ".scss": "scss",
            ".less": "less",
            ".vue": "vue",
            ".svelte": "svelte",
        }
        return mapping.get(ext)

    async def start_for_file(self, file_path: str, cwd: str | None = None) -> LSPClient | None:
        """
        根据文件类型启动对应的 LSP 服务器

        Args:
            file_path: 文件路径
            cwd: 工作目录

        Returns:
            LSP 客户端或 None
        """
        language = self._detect_language(file_path)
        if not language:
            return None

        return await self.start(language, cwd)

    async def start(self, language: str, cwd: str | None = None) -> LSPClient | None:
        """
        启动指定语言的 LSP 服务器

        Args:
            language: 语言标识
            cwd: 工作目录

        Returns:
            LSP 客户端或 None
        """
        if language in self.clients and self.clients[language].is_running():
            return self.clients[language]

        config = self.config.get(language)
        if not config:
            return None

        client = LSPClient()
        try:
            info = await client.start(language, config, cwd=cwd)
            if info:
                self.clients[language] = client
                return client
        except Exception:
            pass

        return None

    async def get_definitions(self, file_path: str, line: int, character: int) -> list[LSPLocation]:
        """获取定义位置"""
        client = await self.start_for_file(file_path)
        if not client:
            return []
        return await client.get_definitions(file_path, line, character)

    async def get_hover(self, file_path: str, line: int, character: int) -> str | None:
        """获取 Hover 信息"""
        client = await self.start_for_file(file_path)
        if not client:
            return None
        return await client.get_hover(file_path, line, character)

    async def get_type_definition(self, file_path: str, line: int, character: int) -> list[LSPLocation]:
        """获取类型定义"""
        client = await self.start_for_file(file_path)
        if not client:
            return []
        return await client.get_type_definition(file_path, line, character)

    async def get_references(self, file_path: str, line: int, character: int) -> list[LSPLocation]:
        """获取引用"""
        client = await self.start_for_file(file_path)
        if not client:
            return []
        return await client.get_references(file_path, line, character)

    async def get_document_symbols(self, file_path: str) -> list[dict]:
        """获取文档符号"""
        client = await self.start_for_file(file_path)
        if not client:
            return []
        return await client.get_document_symbols(file_path)

    async def stop(self, language: str):
        """停止指定语言的 LSP 服务器"""
        if language in self.clients:
            await self.clients[language].stop()
            del self.clients[language]

    async def stop_all(self):
        """停止所有 LSP 服务器"""
        for language in list(self.clients.keys()):
            await self.stop(language)


def load_lsp_config(config_path: str | None = None) -> dict[str, Any]:
    """
    从配置文件加载 LSP 配置

    Args:
        config_path: 配置文件路径，默认为 crush.json

    Returns:
        LSP 配置字典
    """
    import json

    # 查找配置文件
    if not config_path:
        candidates = [
            ".crush.json",
            "crush.json",
            os.path.expanduser("~/.config/crush/crush.json"),
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                config_path = candidate
                break

    if not config_path or not os.path.exists(config_path):
        return {}

    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
            return config.get("lsp", {})
    except Exception:
        return {}
