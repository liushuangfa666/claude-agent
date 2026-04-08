"""
记忆工具 - RememberTool 和 RecallTool

Remember: 保存重要信息到记忆系统
Recall: 从记忆系统检索相关信息
"""
from __future__ import annotations

import logging
import re

from ..tool import BaseTool, ToolResult

try:
    from .memory_store import MemoryStore
    from .types import MemoryType
except ImportError:
    from memory.memory_store import MemoryStore
    from memory.types import MemoryType

logger = logging.getLogger(__name__)

# 全局 MemoryStore 实例
_memory_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    """获取全局 MemoryStore 实例"""
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store


class RememberTool(BaseTool):
    """保存重要信息到记忆系统"""

    name = "Remember"
    description = "保存重要信息到记忆系统，供后续会话参考使用"

    input_schema = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "要记忆的内容"
            },
            "memory_type": {
                "type": "string",
                "enum": ["user", "feedback", "project", "reference"],
                "description": "记忆类型"
            },
            "name": {
                "type": "string",
                "description": "记忆名称（简短描述）"
            },
            "description": {
                "type": "string",
                "description": "用于检索的详细描述"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "标签列表"
            }
        },
        "required": ["content", "memory_type"]
    }

    def __init__(self):
        super().__init__()
        self._store = get_memory_store()

    async def call(self, args: dict, context: dict) -> ToolResult:
        content = args["content"]
        memory_type_str = args["memory_type"]
        name = args.get("name", "")
        description = args.get("description", name)
        tags = args.get("tags", [])

        # 转换 memory_type
        try:
            memory_type = MemoryType(memory_type_str)
        except ValueError:
            return ToolResult(
                success=False,
                data=None,
                error=f"无效的记忆类型: {memory_type_str}，可选值: user, feedback, project, reference"
            )

        # 检查敏感信息
        if self._contains_sensitive_info(content):
            return ToolResult(
                success=False,
                data=None,
                error="内容包含敏感信息（如 API keys、密码等），不建议保存到记忆系统"
            )

        # 生成文件名
        if not name:
            # 从内容中提取前几个词作为名称
            name = content[:50].strip()

        try:
            file_path = self._store.write_memory(
                content=content,
                memory_type=memory_type,
                name=name,
                description=description,
                tags=tags
            )

            return ToolResult(
                success=True,
                data={
                    "memory_id": file_path.stem,
                    "file_path": str(file_path),
                    "memory_type": memory_type.value,
                    "name": name
                }
            )
        except Exception as e:
            logger.error(f"Failed to write memory: {e}")
            return ToolResult(success=False, data=None, error=str(e))

    def _contains_sensitive_info(self, content: str) -> bool:
        """检查内容是否包含敏感信息"""
        sensitive_patterns = [
            r'api[_-]?key',
            r'secret',
            r'password',
            r'token',
            r'Bearer\s+[\w\-]',
            r'ghp_[a-zA-Z0-9]{36}',
            r'sk-[a-zA-Z0-9]{20,}',
        ]

        content_lower = content.lower()
        for pattern in sensitive_patterns:
            if re.search(pattern, content_lower, re.IGNORECASE):
                return True
        return False


class RecallTool(BaseTool):
    """从记忆系统检索相关信息"""

    name = "Recall"
    description = "从记忆系统检索与当前任务相关的信息"

    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "查询内容"
            },
            "memory_type": {
                "type": "string",
                "enum": ["user", "feedback", "project", "reference"],
                "description": "记忆类型（可选，不填则搜索所有类型）"
            },
            "limit": {
                "type": "integer",
                "default": 5,
                "description": "返回结果数量限制"
            }
        },
        "required": ["query"]
    }

    def __init__(self):
        super().__init__()
        self._store = get_memory_store()

    async def call(self, args: dict, context: dict) -> ToolResult:
        query = args["query"]
        memory_type_str = args.get("memory_type")
        limit = args.get("limit", 5)

        memory_type = None
        if memory_type_str:
            try:
                memory_type = MemoryType(memory_type_str)
            except ValueError:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"无效的记忆类型: {memory_type_str}"
                )

        try:
            # 搜索记忆
            headers = self._store.search_memories(query, limit=limit)

            if memory_type:
                headers = [h for h in headers if str(h.memory_type.value) == memory_type_str]

            results = []
            for header in headers:
                _, content = self._store.read_memory(header)
                results.append({
                    "memory_id": header.stem if hasattr(header, 'stem') else header.filename,
                    "name": header.name or header.filename,
                    "description": header.description or "",
                    "type": str(header.memory_type.value) if header.memory_type else "unknown",
                    "content": content[:500],  # 限制内容长度
                    "created": header.created.isoformat() if header.created else None,
                    "mtime": header.mtime.isoformat() if header.mtime else None
                })

            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "count": len(results),
                    "results": results
                }
            )
        except Exception as e:
            logger.error(f"Failed to recall memories: {e}")
            return ToolResult(success=False, data=None, error=str(e))


class ListMemoriesTool(BaseTool):
    """列出记忆系统中的所有记忆"""

    name = "ListMemories"
    description = "列出记忆系统中的记忆，支持按类型筛选"

    input_schema = {
        "type": "object",
        "properties": {
            "memory_type": {
                "type": "string",
                "enum": ["user", "feedback", "project", "reference"],
                "description": "记忆类型（可选，不填则列出所有）"
            },
            "limit": {
                "type": "integer",
                "default": 50,
                "description": "返回结果数量限制"
            }
        },
        "required": []
    }

    def __init__(self):
        super().__init__()
        self._store = get_memory_store()

    async def call(self, args: dict, context: dict) -> ToolResult:
        memory_type_str = args.get("memory_type")
        limit = args.get("limit", 50)

        memory_type = None
        if memory_type_str:
            try:
                memory_type = MemoryType(memory_type_str)
            except ValueError:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"无效的记忆类型: {memory_type_str}"
                )

        try:
            headers = self._store.list_memories(memory_type=memory_type, limit=limit)

            results = []
            for header in headers:
                results.append({
                    "memory_id": header.stem if hasattr(header, 'stem') else header.filename,
                    "name": header.name or header.filename,
                    "description": header.description or "",
                    "type": str(header.memory_type.value) if header.memory_type else "unknown",
                    "created": header.created.isoformat() if header.created else None,
                    "mtime": header.mtime.isoformat() if header.mtime else None
                })

            return ToolResult(
                success=True,
                data={
                    "count": len(results),
                    "results": results
                }
            )
        except Exception as e:
            logger.error(f"Failed to list memories: {e}")
            return ToolResult(success=False, data=None, error=str(e))


class DeleteMemoryTool(BaseTool):
    """删除指定记忆"""

    name = "DeleteMemory"
    description = "从记忆系统中删除指定的记忆"

    input_schema = {
        "type": "object",
        "properties": {
            "memory_id": {
                "type": "string",
                "description": "要删除的记忆 ID（文件名）"
            }
        },
        "required": ["memory_id"]
    }

    def __init__(self):
        super().__init__()
        self._store = get_memory_store()

    async def call(self, args: dict, context: dict) -> ToolResult:
        memory_id = args["memory_id"]

        try:
            success = self._store.delete_memory_by_id(memory_id)
            if success:
                return ToolResult(
                    success=True,
                    data={"memory_id": memory_id, "deleted": True}
                )
            else:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"未找到记忆: {memory_id}"
                )
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return ToolResult(success=False, data=None, error=str(e))


# 注册工具
def register_memory_tools():
    """注册所有记忆工具到全局注册表"""
    from ..tool import get_registry

    tools = [
        RememberTool(),
        RecallTool(),
        ListMemoriesTool(),
        DeleteMemoryTool(),
    ]

    for tool in tools:
        get_registry().register(tool)


# 自动注册
register_memory_tools()
