import os
import tempfile

import pytest

from scripts.tools import BashTool, EditTool, GlobTool, ReadTool, WriteTool


class TestReadTool:
    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self):
        tool = ReadTool()
        result = await tool.call({"file_path": "/nonexistent/file.txt"}, {})
        assert result.success is False
        assert "不存在" in result.error

    @pytest.mark.asyncio
    async def test_read_file(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("hello\nworld")
            path = f.name

        try:
            tool = ReadTool()
            result = await tool.call({"file_path": path, "max_lines": 10}, {})
            assert result.success is True
            assert "hello" in result.data["content"]
            assert result.data["total_lines"] == 2
        finally:
            os.unlink(path)


class TestWriteTool:
    @pytest.mark.asyncio
    async def test_write_new_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            tool = WriteTool()
            result = await tool.call({"file_path": path, "content": "test content"}, {})
            assert result.success is True
            assert os.path.exists(path)
            with open(path) as f:
                assert f.read() == "test content"

    @pytest.mark.asyncio
    async def test_append_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            with open(path, "w") as f:
                f.write("initial")

            tool = WriteTool()
            result = await tool.call(
                {"file_path": path, "content": " appended", "append": True}, {}
            )
            assert result.success is True
            with open(path) as f:
                assert f.read() == "initial appended"


class TestGlobTool:
    @pytest.mark.asyncio
    async def test_glob_finds_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "a.txt"), "w").close()
            open(os.path.join(tmpdir, "b.txt"), "w").close()

            tool = GlobTool()
            result = await tool.call({"pattern": "*.txt", "cwd": tmpdir}, {})
            assert result.success is True
            assert result.data["count"] == 2


class TestEditTool:
    @pytest.mark.asyncio
    async def test_edit_exact_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("hello world")

            tool = EditTool()
            result = await tool.call(
                {"file_path": path, "oldText": "hello", "newText": "hi"}, {}
            )
            assert result.success is True

            with open(path) as f:
                content = f.read()
                assert content == "hi world"

    @pytest.mark.asyncio
    async def test_edit_no_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            with open(path, "w") as f:
                f.write("hello world")

            tool = EditTool()
            result = await tool.call(
                {"file_path": path, "oldText": "notfound", "newText": "replaced"}, {}
            )
            assert result.success is False
            assert "未找到匹配" in result.error

    @pytest.mark.asyncio
    async def test_edit_recovery_whitespace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("hello world")

            tool = EditTool()
            result = await tool.call(
                {"file_path": path, "oldText": "  hello  ", "newText": "hi"}, {}
            )
            assert result.success is True
            assert result.data.get("recovered") is True


class TestBashTool:
    @pytest.mark.asyncio
    async def test_bash_simple_command(self):
        tool = BashTool()
        result = await tool.call({"command": "echo hello"}, {})
        assert result.success is True
        assert "hello" in result.data.get("stdout", "")

    @pytest.mark.asyncio
    async def test_bash_timeout(self):
        import platform
        tool = BashTool()
        # Use ping which works on both Windows and Unix
        if platform.system() == "Windows":
            result = await tool.call({"command": "ping -n 10 127.0.0.1", "timeout": 1}, {})
        else:
            result = await tool.call({"command": "sleep 10", "timeout": 1}, {})
        assert result.success is False
        assert "超时" in result.error or "Timeout" in result.error or result.error is not None
