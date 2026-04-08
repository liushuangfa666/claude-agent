"""
LSP 工具 - 提供语言服务器协议功能

让 AI Agent 能够：
- 获取代码定义位置（Go to Definition）
- 获取类型信息（Hover）
- 获取类型定义（Go to Type Definition）
- 获取引用（Find References）
- 获取文件结构（Document Symbols）
"""
from __future__ import annotations

try:
    from .lsp import LSPLocation, LSPManager, load_lsp_config
    from .tool import BaseTool, ToolResult
except ImportError:
    from lsp import LSPManager, load_lsp_config
    from tool import BaseTool, ToolResult


_lsp_manager: LSPManager | None = None


def get_lsp_manager() -> LSPManager:
    """获取全局 LSP 管理器（单例）"""
    global _lsp_manager
    if _lsp_manager is None:
        config = load_lsp_config()
        _lsp_manager = LSPManager(config)
    return _lsp_manager


class LSPDefinitionTool(BaseTool):
    """获取代码定义位置（Go to Definition）"""

    name = "LSPDefinition"
    description = "获取光标位置符号的定义位置，用于跳转到函数、变量、类的定义处"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件路径"
            },
            "line": {
                "type": "integer",
                "description": "行号（0-based）"
            },
            "character": {
                "type": "integer",
                "description": "列号（0-based）"
            }
        },
        "required": ["file_path", "line", "character"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        file_path = args["file_path"]
        line = args["line"]
        character = args["character"]

        try:
            manager = get_lsp_manager()
            locations = await manager.get_definitions(file_path, line, character)

            if not locations:
                return ToolResult(success=True, data={"definitions": [], "message": "未找到定义"})

            result = {
                "definitions": [
                    {
                        "file_path": loc.file_path,
                        "line": loc.start.line + 1,  # 转换为 1-based
                        "column": loc.start.character + 1,
                    }
                    for loc in locations
                ]
            }
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class LSPHoverTool(BaseTool):
    """获取 Hover 信息（类型、文档字符串）"""

    name = "LSPHover"
    description = "获取光标位置符号的类型信息和文档，用于显示变量类型、函数签名等"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件路径"
            },
            "line": {
                "type": "integer",
                "description": "行号（0-based）"
            },
            "character": {
                "type": "integer",
                "description": "列号（0-based）"
            }
        },
        "required": ["file_path", "line", "character"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        file_path = args["file_path"]
        line = args["line"]
        character = args["character"]

        try:
            manager = get_lsp_manager()
            hover = await manager.get_hover(file_path, line, character)

            if not hover:
                return ToolResult(success=True, data={"hover": None, "message": "未找到 hover 信息"})

            return ToolResult(success=True, data={"hover": hover})
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class LSPTypeDefinitionTool(BaseTool):
    """获取类型定义（Go to Type Definition）"""

    name = "LSPTypeDefinition"
    description = "获取变量或表达式的类型定义位置，用于跳转到类型的定义处"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件路径"
            },
            "line": {
                "type": "integer",
                "description": "行号（0-based）"
            },
            "character": {
                "type": "integer",
                "description": "列号（0-based）"
            }
        },
        "required": ["file_path", "line", "character"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        file_path = args["file_path"]
        line = args["line"]
        character = args["character"]

        try:
            manager = get_lsp_manager()
            locations = await manager.get_type_definition(file_path, line, character)

            if not locations:
                return ToolResult(success=True, data={"type_definitions": [], "message": "未找到类型定义"})

            result = {
                "type_definitions": [
                    {
                        "file_path": loc.file_path,
                        "line": loc.start.line + 1,
                        "column": loc.start.character + 1,
                    }
                    for loc in locations
                ]
            }
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class LSPReferencesTool(BaseTool):
    """获取引用（Find References）"""

    name = "LSPReferences"
    description = "查找符号的所有引用位置，用于显示变量、函数的所有使用处"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件路径"
            },
            "line": {
                "type": "integer",
                "description": "行号（0-based）"
            },
            "character": {
                "type": "integer",
                "description": "列号（0-based）"
            },
            "include_declaration": {
                "type": "boolean",
                "description": "是否包含声明位置",
                "default": True
            }
        },
        "required": ["file_path", "line", "character"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        file_path = args["file_path"]
        line = args["line"]
        character = args["character"]
        include_declaration = args.get("include_declaration", True)

        try:
            manager = get_lsp_manager()
            locations = await manager.get_references(file_path, line, character, include_declaration)

            if not locations:
                return ToolResult(success=True, data={"references": [], "message": "未找到引用"})

            result = {
                "references": [
                    {
                        "file_path": loc.file_path,
                        "line": loc.start.line + 1,
                        "column": loc.start.character + 1,
                    }
                    for loc in locations
                ]
            }
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class LSPSymbolsTool(BaseTool):
    """获取文档符号（文件结构/Outline）"""

    name = "LSPSymbols"
    description = "获取文件的结构信息，包括类、函数、变量等符号，用于显示代码大纲"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件路径"
            }
        },
        "required": ["file_path"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        file_path = args["file_path"]

        try:
            manager = get_lsp_manager()
            symbols = await manager.get_document_symbols(file_path)

            if not symbols:
                return ToolResult(success=True, data={"symbols": [], "message": "未找到符号"})

            # 格式化输出
            result = {
                "symbols": [
                    {
                        "name": s.get("name", ""),
                        "kind": s.get("kind", ""),
                        "detail": s.get("detail", ""),
                        "line": (s.get("range", {}).get("start", {}).get("line", 0)) + 1,
                    }
                    for s in symbols
                ]
            }
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class LSPInitTool(BaseTool):
    """初始化 LSP 服务器"""

    name = "LSPInit"
    description = "为指定文件初始化 LSP 服务器，建立代码理解上下文"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件路径（根据扩展名启动对应 LSP）"
            },
            "cwd": {
                "type": "string",
                "description": "工作目录，默认当前目录"
            }
        },
        "required": ["file_path"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        file_path = args["file_path"]
        cwd = args.get("cwd")

        try:
            manager = get_lsp_manager()
            client = await manager.start_for_file(file_path, cwd=cwd)

            if client is None:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"未找到 {file_path} 对应的 LSP 配置，请在 crush.json 中配置"
                )

            return ToolResult(
                success=True,
                data={"status": "LSP server started", "file_path": file_path}
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


# LSP Kind 映射表
LSP_SYMBOL_KINDS = {
    1: "File",
    2: "Module",
    3: "Namespace",
    4: "Package",
    5: "Class",
    6: "Method",
    7: "Property",
    8: "Field",
    9: "Constructor",
    10: "Enum",
    11: "Interface",
    12: "Function",
    13: "Variable",
    14: "Constant",
    15: "String",
    16: "Number",
    17: "Boolean",
    18: "Array",
    19: "Object",
    20: "Key",
    21: "Null",
    22: "EnumMember",
    23: "Struct",
    24: "Event",
    25: "Operator",
    26: "TypeParameter",
}
