---
name: claude-agent
description: 参考 Claude Code 架构设计的 agent 实现。当需要构建一个结构化的 agent 系统时使用，包括：工具接口设计（schema 校验、权限引擎）、分层 context 注入、系统提示词工程、多轮对话循环。触发于"创建一个 agent"、"参考 Claude Code 重构"、"实现工具权限系统"等场景。
---

# Claude Agent

参考 Claude Code 架构设计的 agent 实现。

## 架构概览

```
Agent (agent.py)
├── ToolRegistry (tool.py)     # 工具注册表
│   ├── BaseTool              # 工具基类
│   ├── validate_input()      # 输入校验
│   └── call()                # 执行入口
├── PermissionEngine (permission.py)  # 权限规则引擎
│   ├── Pattern matching      # "Bash(git *)"
│   └── DenialTracking       # 拒绝追踪
├── ContextBuilder (context.py)      # 分层上下文
│   ├── git status
│   ├── cwd info
│   └── date
└── SystemPromptBuilder (system_prompt.py)  # 提示词构建
    ├── 角色定义
    ├── 工具描述
    ├── 使用指南
    └── 示例
```

## 核心模块

### scripts/agent.py

Agent 主循环，处理多轮对话。

```python
from agent import create_agent, AgentConfig
from tool import BashTool, ReadTool, WriteTool

# 创建 Agent（自动注册工具）
agent = create_agent(
    tools=[ReadTool(), BashTool(), WriteTool()],
    permission_engine=PermissionEngine.build_default_engine(),
)

# 运行
result = await agent.run("帮我看看 src/main.py 的内容")
print(result)
```

### scripts/tool.py

工具基类，所有工具继承 `BaseTool`。

```python
from tool import BaseTool, ToolResult

class ReadTool(BaseTool):
    name = "Read"
    description = "读取文件内容"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "文件路径"},
            "max_lines": {"type": "integer", "description": "最大行数", "default": 100},
        },
        "required": ["file_path"]
    }

    async def call(self, args, context) -> ToolResult:
        # args 已经过 schema 校验
        file_path = args["file_path"]
        # ... 读取逻辑
        return ToolResult(success=True, data=content)
```

### scripts/permission.py

权限引擎，支持规则匹配。

```python
from permission import PermissionEngine

engine = PermissionEngine()
engine.allow("Bash(git *)")      # git 操作允许
engine.deny("Bash(rm *)")        # rm 操作拒绝
engine.deny("Edit(*.env)")       # .env 修改拒绝

# 检查
result = engine.check("Bash", {"command": "rm -rf /tmp"})
# result.behavior == "deny"
```

### scripts/system_prompt.py

系统提示词构建器。

```python
from system_prompt import build_system_prompt
from tool import get_registry

tools = get_registry().all()
context = build_default_context()
prompt = build_system_prompt(tools, context)
```

### scripts/context.py

分层上下文注入。

```python
from context import build_default_context

context = build_default_context()
# {
#   "system": "2026-04-02 ...\n## git status\n...",
#   "user": "CWD: /home/...\nDirectory contents: ..."
# }
```

## 工具开发规范

每个工具必须：
1. 继承 `BaseTool`
2. 定义 `name`、`description`、`input_schema`
3. 实现 `call()` 方法

可选覆盖：
- `is_destructive(args)` → 返回 True 标记为危险操作
- `validate_input(args)` → 自定义校验逻辑
- `get_activity_description(args)` → 旋转器显示文本

## 权限规则语法

```
ToolName(field=value)
ToolName(*.py)          # glob 匹配
ToolName(git *)          # 前缀匹配
ToolName(rm -rf *)      # 完整命令匹配
```

## 工具结果渲染

`ToolResult` 支持返回结构化数据：

```python
return ToolResult(
    success=True,
    data={
        "files": ["a.py", "b.py"],
        "count": 2,
        "truncated": False
    },
    new_messages=[...]  # 额外消息
)
```

## 参考资料

- [Claude Code 源码分析](./references/) - 内置工具完整 schema

## HTTP 服务 + SSE 流式输出

### scripts/web_server.py

Agent HTTP 服务层，支持多会话管理和统计。

```python
from web_server import start_server

start_server(port=18780)
```

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/chat` | POST | 发送消息，`stream=true` 开启 SSE 流式输出 |
| `/api/session` | POST | 获取会话历史 |
| `/api/status` | GET | 服务状态 |
| `/api/stats` | GET | Token 统计 |

### SSE 流式调用

```javascript
const res = await fetch('/api/chat', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({message: "帮我看看 D:\\code 目录", stream: true})
});
const reader = res.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const {done, value} = await reader.read();
  if (done) break;
  const text = decoder.decode(value);
  text.split('\n').forEach(line => {
    if (line.startsWith('data: ')) {
      const event = JSON.parse(line.slice(6));
      if (event.type === 'done') { console.log('=== DONE ==='); break; }
      console.log(`[${event.type}]`, event.content || '');
    }
  });
}
```

### SSE 事件类型

| type | 说明 | 关键字段 |
|------|------|---------|
| `thinking` | LLM 思考/调试信息 | `content` |
| `text` | LLM 文本回复 | `content` |
| `tool_start` | 工具开始执行 | `tool`, `args` |
| `tool_progress` | 工具执行进度（Edit 三阶段） | `tool`, `content`, `recovered` |
| `tool_recovered` | 错误恢复成功 | `tool`, `warning` |
| `tool_result` | 工具执行结果 | `tool`, `success`, `data` |
| `tool_error` | 工具执行失败 | `tool`, `error` |
| `done` | 流结束 | - |

