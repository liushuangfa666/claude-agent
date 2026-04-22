"""
记忆系统测试
"""
import tempfile
import shutil
from pathlib import Path

import pytest


class TestMemoryStore:
    """MemoryStore 测试"""

    @pytest.fixture
    def temp_store(self):
        """创建临时内存存储"""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from scripts.memory.memory_store import MemoryStore
        from scripts.memory.types import MemoryType

        # 使用临时目录
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore()
            original_dir = store.MEMORY_DIR
            store.MEMORY_DIR = Path(tmpdir) / ".crush" / "memory"
            store.MEMORY_INDEX_FILE = store.MEMORY_DIR / "MEMORY.md"
            store._ensure_directories()
            yield store, store.MEMORY_DIR

    def test_write_and_read_memory(self, temp_store):
        """测试写入和读取记忆"""
        store, mem_dir = temp_store

        path = store.write_memory(
            content="Test content",
            memory_type=None,
            name="Test Memory",
            description="A test description",
        )

        assert path.exists()
        assert path.parent == mem_dir / "user"

    def test_list_memories(self, temp_store):
        """测试列出记忆"""
        store, _ = temp_store

        # 写入多个记忆
        store.write_memory("Content 1", name="Memory 1")
        store.write_memory("Content 2", name="Memory 2")

        headers = store.list_memories()
        assert len(headers) >= 2

    def test_search_memories(self, temp_store):
        """测试搜索记忆"""
        store, _ = temp_store

        store.write_memory(
            "Python developer",
            name="User Background",
            description="Python developer with experience"
        )

        results = store.search_memories("Python")
        assert len(results) >= 1

    def test_delete_memory(self, temp_store):
        """测试删除记忆"""
        store, _ = temp_store

        path = store.write_memory("To be deleted", name="Delete Me")
        stem = path.stem

        success = store.delete_memory_by_id(stem)
        assert success or not path.exists()

    def test_update_index(self, temp_store):
        """测试更新索引"""
        store, _ = temp_store

        store.write_memory("Indexed content", name="Indexed")

        index_file = store.MEMORY_INDEX_FILE
        assert index_file.exists()

        content = index_file.read_text(encoding="utf-8")
        assert "Indexed" in content or "# Memory Index" in content


class TestSessionMemory:
    """SessionMemory 测试"""

    def test_session_memory_save_load(self):
        """测试会话记忆保存和加载"""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from scripts.memory.session_memory import SessionMemory
        from scripts.memory.memory_store import MemoryStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore()
            store.SESSION_MEMORY_DIR = Path(tmpdir) / "session-memory"

            session = SessionMemory(session_id="test-123", store=store)
            session.update_current_state("Working on feature X")
            session.update_task_spec("Implement feature X")
            session.add_workflow_step("git commit -m 'feat: feature X'")

            session.save()

            # 加载验证
            loaded = SessionMemory.load("test-123", store)
            assert loaded is not None
            assert loaded._current_state == "Working on feature X"


class TestMemoryTools:
    """记忆工具测试"""

    def test_remember_tool_registered(self):
        """测试 Remember 工具已注册"""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from scripts.tool import get_registry

        registry = get_registry()
        remember_tool = registry.get("Remember")
        recall_tool = registry.get("Recall")

        assert remember_tool is not None
        assert recall_tool is not None

    def test_recall_tool_schema(self):
        """测试 Recall 工具 schema"""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from scripts.memory.tools import RecallTool

        tool = RecallTool()
        schema = tool.input_schema

        assert "query" in schema["required"]
        assert "properties" in schema
