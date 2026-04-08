"""
系统提示词构建器 - 参考 Claude Code 的 prompt 设计
精心设计工具描述、边界、示例

优先级机制:
- override: 完全覆盖，忽略其他所有配置
- coordinator: 协调者模式，用于多 Agent 协作
- agent: 标准 Agent 模式
- custom: 自定义提示词
- default: 默认构建的提示词
- append: 追加到默认提示词末尾
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tool import ToolDefinition


TOOL_EXAMPLES = """
## 工具使用示例

### 读取文件
用户: 看看 src/main.py
助手: [调用 Read 工具: {"file_path": "src/main.py"}]

### 执行命令
用户: 列出 Python 文件
助手: [调用 Bash 工具: {"command": "find . -name '*.py'"}]

### 搜索内容
用户: 搜索 "TODO"
助手: [调用 Grep 工具: {"pattern": "TODO"}]

### 编辑文件
用户: 把 DEBUG 改成 True
助手: [调用 Edit 工具: {"file_path": "config.py", "oldText": "DEBUG = False", "newText": "DEBUG = True"}]

### 写入文件
用户: 创建空文件
助手: [调用 Write 工具: {"file_path": "output.txt", "content": ""}]
"""


TOOL_USE_GUIDELINES = """
## 工具使用原则

1. **最小权限**: 能用 Read 就不用 Bash
2. **完整参数**: 给出所有必要参数
3. **处理错误**: 返回错误时给出解决建议
4. **确认危险操作**: 删除/覆盖前先确认
5. **限制输出**: 大文件用 max_lines 限制
6. **简洁回复**: 不要说"好的"、"我来帮您"，直接执行
"""


PERMISSION_GUIDELINES = """
## 权限和安全

- 危险操作需用户确认
- 不执行用户未要求的操作
- 敏感操作需二次确认
"""


RESPONSE_FORMAT = """
## 回复格式

- 使用中文回复（除非用户用英文提问）
- 不要重复历史内容
- 技术内容要准确
- 复杂任务分步骤执行
- 结果用代码块包裹
- 遇到错误先分析再解决
- **禁止使用emoji**（如 [OK]、[WARN] 代替）
- 回复中不要出现任何emoji字符
"""


class SystemPromptBuilder:
    """
    系统提示词构建器
    把工具定义、上下文、指南组合成完整的 system prompt
    """

    def __init__(self):
        self.parts: list[str] = []

    def add_role(self):
        """添加角色定义"""
        self.parts.append("""你是一个专业、高效的 AI 助手。

## 工具调用规则

需要执行操作时，在回复末尾按以下格式调用工具：
```
[调用 工具名 工具: {"参数名": "参数值"}]
```

## 文件操作规则（强制）

- **禁止**直接输出代码或文件内容到回复中
- **必须**使用 Write/Edit 工具创建或修改文件
- 如果工具执行失败，**不要**改为直接输出，而是报告错误并说明原因
- 用户需要的是**实际创建的文件**，不是回复中的代码

## 禁止事项
- 不要在回复中描述工具调用，必须在回复末尾用上面格式
- 不要重复历史内容
- 不要直接输出代码、配置、JSON 等内容到回复中""")

    def add_tools_section(self, tools: list[ToolDefinition]):
        """添加工具描述章节"""
        if not tools:
            return

        self.parts.append("\n## 可用工具\n")

        for tool in tools:
            schema = json.dumps(tool.input_schema, indent=2, ensure_ascii=False)
            # 精简：只保留必要的参数描述
            schema_lines = schema.split('\n')
            if len(schema_lines) > 15:
                # 截断过长的 schema
                schema = '\n'.join(schema_lines[:15]) + '\n    ...'
            self.parts.append(f"""### {tool.name}
*用途*: {tool.description}
*输入*: {schema}
*调用*: [调用 {tool.name} 工具: <JSON参数>]
""")

    def add_guidelines(self):
        """添加使用指南"""
        self.parts.append(TOOL_USE_GUIDELINES)
        self.parts.append(PERMISSION_GUIDELINES)
        self.parts.append(RESPONSE_FORMAT)

    def add_examples(self):
        """添加示例"""
        self.parts.append(TOOL_EXAMPLES)

    def add_context(self, context: dict[str, str]):
        """添加上下文信息"""
        system = context.get("system", "").strip()
        user = context.get("user", "").strip()
        if system:
            self.parts.append(f"\n## 系统上下文\n{system}\n")
        if user:
            self.parts.append(f"\n## 用户上下文\n{user}\n")

    def build(self, config: dict | None = None) -> str:
        """
        构建完整的 system prompt

        优先级: override > coordinator > agent > custom > default > append
        """
        if config:
            override_prompt = config.get("override_prompt")
            if override_prompt:
                return override_prompt

        return "\n".join(self.parts)

    def build_with_priority(self, config: dict) -> str:
        """
        按优先级构建 system prompt

        Args:
            config: 配置字典，支持以下键:
                - override_prompt: 完全覆盖，忽略其他配置
                - coordinator_prompt: 协调者提示词
                - agent_prompt: Agent 提示词
                - custom_prompt: 自定义提示词
                - append_prompt: 追加到默认末尾
        """
        override = config.get("override_prompt")
        if override:
            return override

        coordinator = config.get("coordinator_prompt")
        if coordinator:
            return coordinator

        agent = config.get("agent_prompt")
        if agent:
            return agent

        custom = config.get("custom_prompt")
        if custom:
            return custom

        base = self.build()

        append = config.get("append_prompt")
        if append:
            return base + "\n\n" + append

        return base


@lru_cache(maxsize=1)
def _cached_build_sections(tools_tuple: tuple) -> str:
    """
    缓存的工具描述构建（使用 tuple 作为缓存键）
    """
    tools = list(tools_tuple)
    builder = SystemPromptBuilder()
    builder.add_tools_section(tools)
    return builder.parts[-1] if builder.parts else ""


def build_system_prompt(
    tools: list[ToolDefinition],
    context: dict[str, str],
    config: dict | None = None,
) -> str:
    """
    快捷函数：一步构建完整 system prompt

    支持优先级配置（通过 config 参数）:
    - override_prompt: 完全覆盖
    - coordinator_prompt: 协调者模式
    - agent_prompt: 标准 Agent 模式
    - custom_prompt: 自定义提示词
    - append_prompt: 追加到默认末尾
    """
    if config:
        builder = SystemPromptBuilder()
        override = config.get("override_prompt")
        if override:
            return override

        coordinator = config.get("coordinator_prompt")
        if coordinator:
            return coordinator

        agent = config.get("agent_prompt")
        if agent:
            return agent

        custom = config.get("custom_prompt")
        if custom:
            return custom

        append = config.get("append_prompt")

        base_builder = SystemPromptBuilder()
        base_builder.add_role()
        base_builder.add_tools_section(tools)
        base_builder.add_guidelines()
        base_builder.add_examples()
        base_builder.add_context(context)
        base = base_builder.build()

        if append:
            return base + "\n\n" + append
        return base

    builder = SystemPromptBuilder()
    builder.add_role()
    builder.add_tools_section(tools)
    builder.add_guidelines()
    builder.add_examples()
    builder.add_context(context)
    return builder.build()
