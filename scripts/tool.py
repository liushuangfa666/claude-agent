"""
Tool 接口 - 参考 Claude Code 的 Tool.ts 设计
每个工具都有：name, description, input_schema, validate(), call()
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    data: Any
    error: str | None = None
    new_messages: list[dict] = field(default_factory=list)
    auth_required: tuple = None  # (tool_name, args, reason) 当需要授权时


@dataclass
class ToolDefinition:
    """工具定义（对应 Claude Code 的 Tool type）"""
    name: str
    description: str                          # 工具用途描述
    input_schema: dict                       # JSON Schema 格式
    aliases: list[str] = field(default_factory=list)
    is_enabled: Callable[[], bool] = lambda: True
    is_concurrency_safe: Callable[[Any], bool] = lambda _: False
    is_read_only: Callable[[Any], bool] = lambda _: False
    is_destructive: Callable[[Any], bool] = lambda _: False  # 危险操作标记
    is_search_or_read: Callable[[Any], dict] = lambda _: {"is_search": False, "is_read": False}
    requires_user_interaction: Callable[[], bool] = lambda: False

    def match_name(self, name: str) -> bool:
        """检查是否匹配工具名（支持别名）"""
        return self.name == name or name in self.aliases


class BaseTool(ABC):
    """工具基类，所有工具继承此类"""

    # 子类覆盖
    name: str = ""
    description: str = ""
    input_schema: dict = {"type": "object", "properties": {}, "required": []}

    def __init__(self):
        self._def = ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
        )

    def definition(self) -> ToolDefinition:
        return self._def

    def validate_input(self, raw_input: Any) -> tuple[bool, str | None]:
        """
        校验输入是否符合 schema。
        返回 (是否合法, 错误信息)
        """
        if not isinstance(raw_input, dict):
            return False, f"输入必须是 object，得到 {type(raw_input).__name__}"

        # 检查必填字段
        required = self.input_schema.get("required", [])
        for field_name in required:
            if field_name not in raw_input:
                return False, f"缺少必填字段: {field_name}"

        # 检查字段类型
        properties = self.input_schema.get("properties", {})
        for key, value in raw_input.items():
            if key in properties:
                expected_type = properties[key].get("type")
                if not self._check_type(value, expected_type):
                    return False, f"字段 {key} 期望 {expected_type}，得到 {type(value).__name__}"

        return True, None

    def _check_type(self, value: Any, expected: str) -> bool:
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected_cls = type_map.get(expected)
        if expected_cls is None:
            return True
        return isinstance(value, expected_cls)

    @abstractmethod
    async def call(self, args: dict, context: dict) -> ToolResult:
        """实际执行逻辑，子类实现"""
        ...

    def is_destructive(self, args: dict) -> bool:
        """是否危险操作（删除/覆盖等）"""
        return False

    def get_activity_description(self, args: dict) -> str:
        """旋转器显示的活动描述"""
        return f"Running {self.name}"

    def to_auto_classifier_input(self, args: dict) -> str:
        """安全分类器的输入"""
        return ""


class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_by_alias(self, alias: str) -> BaseTool | None:
        for tool in self._tools.values():
            if tool.definition().match_name(alias):
                return tool
        return None

    def find(self, name_or_alias: str) -> BaseTool | None:
        return self.get(name_or_alias) or self.get_by_alias(name_or_alias)

    def all(self) -> list[ToolDefinition]:
        return [t.definition() for t in self._tools.values() if t.definition().is_enabled()]


# 全局注册表
_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    return _registry


def register(tool: BaseTool):
    _registry.register(tool)
