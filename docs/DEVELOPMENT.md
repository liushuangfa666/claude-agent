# Claude Agent 开发记录

> 本文档记录项目的开发历史、功能变更和实现细节。

---

## 开发概览

| 项目 | 信息 |
|------|------|
| 项目名称 | Claude Agent |
| 项目类型 | Python CLI/Web AI 助手 |
| 架构参考 | Claude Code |
| 当前版本 | 0.1.0 |

---

## 开发阶段

### Phase 1: 核心框架 (已完成)

**时间**: 2024 年初

**完成内容**:
1. Agent 核心循环 (`scripts/agent.py`)
2. 工具系统 (`scripts/tool.py`, `scripts/tools.py`)
3. 权限系统 (`scripts/permission.py`)
4. Hook 系统 (`scripts/hooks.py`)

---

### Phase 2: 高级功能 (已完成)

**时间**: 2024 年中

**完成内容**:
1. 插件系统 (`scripts/plugins.py`)
2. MCP 支持 (`scripts/mcp/`)
3. 多智能体系统 (`scripts/multi_agent/`)
4. 计划模式 (`scripts/plan_mode.py`)
5. 会话管理 (`scripts/session/`)
6. 记忆系统 (`scripts/memory/`)

---

### Phase 3: 新工具 (已完成)

**时间**: 2026 年 4 月

**完成内容**:

#### 1. REPLTool - 交互式 REPL

**功能**: 在当前会话中执行多轮命令输入

**实现文件**: `scripts/tools_advanced.py`

**工具类**: `REPLTool`

**功能说明**:
- 支持 Python/Bash/Node.js/Lua 多种解释器
- 实时返回命令输出
- 包含执行时间和退出码

**参数**:
```python
{
    "command": str,           # 要执行的命令
    "language": str,          # 解释器类型: python/bash/node/lua
    "session_id": str        # 会话 ID（可选）
}
```

---

#### 2. ConfigTool - 运行时配置

**功能**: 查看和修改运行时配置

**实现文件**: `scripts/tools_advanced.py`

**工具类**: `ConfigGetTool`, `ConfigSetTool`, `ConfigListTool`

**功能说明**:
- `ConfigGet`: 获取单个配置项
- `ConfigSet`: 设置配置项（支持类型转换）
- `ConfigList`: 列出所有配置项

**默认配置项**:
```python
{
    "log_level": "info",
    "max_tokens": 4096,
    "temperature": 0.7,
    "stream": True,
    "compact_threshold": 0.8,
    "auto_approve": False,
}
```

---

#### 3. ToolSearchTool - 工具发现

**功能**: 搜索和查找已注册的工具

**实现文件**: `scripts/tools_advanced.py`

**工具类**: `ToolSearchTool`, `ToolListAllTool`

**功能说明**:
- `ToolSearch`: 按名称或描述搜索工具
- `ToolListAll`: 列出所有已注册的工具

**参数**:
```python
# ToolSearch
{
    "query": str,           # 搜索关键词
    "type": str             # 搜索类型: name/description/all
}

# ToolListAll
{
    "include_disabled": bool  # 是否包含已禁用工具
}
```

---

#### 4. MonitorTool - 系统监控

**功能**: 监控系统 CPU、内存、磁盘、进程等指标

**实现文件**: `scripts/tools_advanced.py`

**工具类**: `MonitorCPUTool`, `MonitorMemoryTool`, `MonitorDiskTool`, `MonitorProcessTool`, `MonitorSystemTool`

**功能说明**:
- `MonitorCPU`: CPU 使用率（支持多核）
- `MonitorMemory`: 内存和交换分区使用
- `MonitorDisk`: 磁盘使用情况
- `MonitorProcess`: 进程信息（支持 top N）
- `MonitorSystem`: 综合系统信息

**依赖**: `psutil` 库

**使用示例**:
```python
# 获取 CPU 使用率
result = await tool.call({"interval": 1.0}, {})

# 获取内存信息
result = await tool.call({}, {})

# 获取 CPU 最高的 5 个进程
result = await tool.call({"top": 5}, {})

# 综合系统信息
result = await tool.call({}, {})
```

---

### Phase 4: 架构优化 (已完成)

**时间**: 2026 年 4 月

**完成内容**:

#### 1. StructuredIO 集成

**功能**: 将 StructuredIO 集成到 Agent 主循环

**修改文件**: `scripts/agent.py`

**功能说明**:
- Agent 接受 `structured_io` 参数
- 在关键事件（thinking、text、tool_result、done）上发送 StructuredIO 消息
- 支持 NDJSON 结构化输出

**实现细节**:

```python
# Agent 初始化
def __init__(self, config: AgentConfig | None = None, structured_io: Any = None):
    self._structured_io = structured_io
    # ...

# run_stream 中的事件发送
async def _emit_structured_event(event_type: str, content: str = "", **kwargs):
    """通过 StructuredIO 发送事件（如果有配置）"""
    if self._structured_io:
        await self._structured_io.send_stream_event(event_type, content, **kwargs)
```

**StructuredIO 事件类型**:
- `thinking` - LLM 处理中
- `text` - 文本回复
- `tool_result` - 工具结果
- `done` - 完成

---

#### 2. MCP OAuth 认证

**功能**: 为 MCP 服务器添加 OAuth 认证支持

**实现文件**: `scripts/mcp/mcp_oauth.py`

**功能说明**:
- OAuth 2.0 认证流程
- 令牌管理和刷新
- 令牌撤销

**核心类**:
- `OAuthToken` - OAuth 令牌数据类
- `OAuthConfig` - OAuth 配置
- `OAuthTokenStore` - 令牌存储
- `OAuthFlow` - OAuth 认证流程
- `MCPOAuthManager` - MCP OAuth 管理器

**使用示例**:
```python
from scripts.mcp.mcp_oauth import get_oauth_manager

oauth_manager = get_oauth_manager()
oauth_manager.register_server(
    server_name="github",
    client_id="your_client_id",
    authorization_url="https://github.com/login/oauth/authorize",
    token_url="https://github.com/login/oauth/access_token",
)

# 执行 OAuth 流程
token = await oauth_manager.perform_mcp_oauth_flow("github")
```

---

#### 3. SSH/Daemon 守护进程

**功能**: 实现 SSH 守护进程支持远程连接

**实现文件**: `scripts/sshd.py`

**工具类**:
- `SSHDaemonStartTool` - 启动 SSH 守护进程
- `SSHDaemonStopTool` - 停止 SSH 守护进程
- `SSHDaemonStatusTool` - 获取运行状态

**功能说明**:
- SSH 模式（需要 paramiko）：完整的 SSH 协议支持
- TCP 模式（无依赖）：简单的基于文本的协议
- 支持用户名/密码认证

**使用示例**:
```python
# 启动 SSH 守护进程
result = await tool.call({
    "host": "0.0.0.0",
    "port": 2222,
    "username": "claude",
    "password": "secret"
}, {})

# 检查状态
result = await tool.call({}, {})

# 停止
result = await tool.call({}, {})
```

**注意**: TCP 模式不安全，仅用于开发测试。生产环境应使用 SSH 模式（安装 paramiko）。

---

#### 5. `_run_agent_task` 后台任务

**问题**: `scripts/task/runner.py:96-102` 中 `_run_agent_task` 抛出 `NotImplementedError`

**解决方案**:
- 使用 `SubagentExecutor.execute_background()` 启动后台子代理
- 通过 `agent_info.prompt` 获取任务描述
- 添加 `_wait_for_agent_result` 方法轮询子代理状态

**修改文件**:
- `scripts/task/runner.py`

**实现细节**:

```python
async def _run_agent_task(
    self,
    bg_task: BackgroundTask,
    session_id: str,
) -> None:
    """运行 Agent 任务"""
    from scripts.subagent.executor import get_subagent_executor
    from scripts.subagent.types import SubagentType

    executor = get_subagent_executor()

    await self._update_task_status(bg_task.task.id, session_id, TaskStatus.IN_PROGRESS)
    self._running_tasks[bg_task.task.id] = bg_task

    try:
        prompt = bg_task.task.metadata.get("prompt", "")
        description = bg_task.task.metadata.get("description", "")
        subagent_type_str = bg_task.task.metadata.get("subagent_type", "GeneralPurpose")

        try:
            subagent_type = SubagentType.from_string(subagent_type_str)
        except ValueError:
            subagent_type = SubagentType.GENERAL_PURPOSE

        agent_info = await executor.execute_background(
            prompt=prompt,
            subagent_type=subagent_type,
            description=description,
        )

        bg_task.future = asyncio.create_task(
            self._wait_for_agent_result(agent_info.agent_id, bg_task, session_id)
        )

    except Exception as e:
        bg_task.error = str(e)
        await self._update_task_status(bg_task.task.id, session_id, TaskStatus.FAILED)
```

---

#### 2. Skill Slash Command 系统

**目标**: 支持 `/skill-name arg1 arg2` 格式的命令

**解决方案**:

1. **新建 `slash_parser.py`** - 专门解析 slash 命令
2. **修改 `agent.py`** - 在 `run_stream` 中添加 slash 命令检测

**新建文件**:
- `scripts/skill/slash_parser.py`

**修改文件**:
- `scripts/agent.py`

**实现细节**:

```python
# scripts/skill/slash_parser.py
@dataclass
class SlashCommand:
    skill_name: str
    arguments: str

def parse_slash_command(text: str) -> SlashCommand | None:
    """解析 slash 命令"""
    pattern = r'^/(\w+)(?:\s+(.*))?$'
    match = re.match(pattern, text.strip())
    if match:
        return SlashCommand(skill_name=match.group(1), arguments=match.group(2) or "")
    return None
```

```python
# scripts/agent.py - run_stream 方法中
# ========== Slash Command 检测 ==========
processed_message = await self._handle_slash_command(user_message)
if processed_message:
    if isinstance(processed_message, tuple):
        # FORK 模式：返回子代理执行结果
        fork_result = processed_message[1]
        _set_current_agent(None)
        yield StreamEvent(type="done", content=fork_result)
        return
    # INLINE 模式：使用展开后的消息
    user_message = processed_message
# ========== Slash Command 结束 ==========
```

**执行流程**:

```
用户输入 /skill-name args
        ↓
parse_slash_command() 解析
        ↓
SkillLoader 查找 skill
        ↓
skill.config.expand_content(args) 展开
        ↓
根据 context 决定:
  - INLINE: 注入到用户消息
  - FORK: 子代理执行
```

---

#### 3. SkillListTool 和 SkillInfoTool

**状态**: 早已实现并注册

**实现文件**: `scripts/skill/skill_tool.py`

**功能**:
- `SkillListTool` - 列出所有可用技能
- `SkillInfoTool` - 获取技能详细信息

---

## Phase 2: 重要功能 (2026-04-08)

### 1. MCP channelNotification 支持

**目标**: 支持 MCP 服务器主动推送通知

**修改文件**:
- `scripts/mcp/mcp_types.py` - 添加 `JsonRpcNotification.from_dict()`
- `scripts/mcp/mcp_client.py` - 添加 notification 处理器机制

**实现细节**:

```python
# MCPClient 新增方法
def set_notification_handler(self, handler: callable) -> None:
    """设置 notification 处理器"""
    self._notification_handler = handler
    if self._transport and self._transport.is_connected:
        self._start_notification_listener()
```

**使用示例**:
```python
client = MCPClient()
await client.connect(transport)

def on_notification(method: str, params: dict):
    print(f"Received: {method}, params: {params}")
    # 返回 False 停止监听
    return True

client.set_notification_handler(on_notification)
```

---

### 2. 增强 Hook 事件

**目标**: 添加 LLM 和工具相关的新事件

**新增事件**:
- `LLMStart` - LLM 开始调用
- `LLMComplete` - LLM 完成调用
- `ToolUseBlocked` - 工具被阻止
- `ToolUseDenied` - 工具被拒绝
- `PreAgentCreate` - 子代理创建前
- `PostAgentCreate` - 子代理创建后

**修改文件**:
- `scripts/hooks/enhanced.py` - 添加 6 个新事件（27 → 33）
- `scripts/agent.py` - 触发 LLMStart 和 LLMComplete 事件

---

### 3. TaskOutput 增强

**目标**: 支持流式获取任务输出

**新增参数**:
- `stream`: 实时返回新增的输出
- `clear`: 获取后清除输出缓冲区
- `watch`: 持续监听输出变化

**修改文件**:
- `scripts/task/task_tools.py` - 增强 `TaskOutputTool`

**使用示例**:
```python
# 普通模式
result = await tool.call({"task_id": "xxx"}, {})

# 流式模式
result = await tool.call({"task_id": "xxx", "stream": True}, {})
# 返回 new_output（新增内容）和 total_output（全部内容）

# 监听模式
result = await tool.call({"task_id": "xxx", "watch": True}, {})
```

---

## 项目结构

```
claude-agent/
├── scripts/
│   ├── agent.py              # 核心 Agent 循环
│   ├── tool.py               # 工具基类和注册表
│   ├── tools.py              # 基础工具
│   ├── tools_advanced.py     # 高级工具
│   ├── permission.py         # 权限引擎
│   ├── hooks.py              # Hook 系统
│   ├── plugins.py            # 插件系统
│   ├── context.py            # 上下文构建
│   ├── system_prompt.py      # 系统提示词
│   ├── compact/              # 上下文压缩
│   │   ├── token_budget.py
│   │   ├── compact_manager.py
│   │   └── reactive_compact.py
│   ├── hooks/
│   │   └── enhanced.py       # 增强 Hook
│   ├── mcp/
│   │   ├── mcp_client.py     # MCP 客户端
│   │   ├── mcp_manager.py    # MCP 服务器管理
│   │   ├── mcp_tool.py       # MCP 工具包装
│   │   └── mcp_config.py     # MCP 配置
│   ├── memory/
│   │   ├── memory_retriever.py
│   │   ├── memory_store.py
│   │   └── freshness.py
│   ├── multi_agent/
│   │   ├── router.py         # 复杂度路由
│   │   ├── decomposer.py    # 任务分解
│   │   ├── reviewer.py      # 审核器
│   │   └── executor.py       # 执行器
│   ├── plan/
│   │   ├── verification.py
│   │   ├── step_conditions.py
│   │   ├── interview.py
│   │   └── rollback.py
│   ├── session/
│   │   ├── manager.py
│   │   ├── store.py
│   │   └── metadata.py
│   ├── skill/
│   │   ├── skill.py          # Skill 数据模型
│   │   ├── loader.py         # Skill 加载器
│   │   ├── parser.py         # SKILL.md 解析器
│   │   ├── skill_tool.py     # Skill 工具
│   │   └── slash_parser.py   # Slash 命令解析器 (新增)
│   ├── subagent/
│   │   ├── executor.py       # 子代理执行器
│   │   ├── registry.py       # 子代理注册表
│   │   ├── types.py          # 子代理类型
│   │   └── tool_filter.py    # 工具过滤
│   ├── task/
│   │   ├── models.py         # Task 数据模型
│   │   ├── runner.py         # 后台任务运行器
│   │   ├── store.py          # 任务存储
│   │   └── task_tools.py     # Task 工具
│   ├── web_server.py         # Web 服务
│   ├── run.py                # CLI 入口
│   └── start_web.py          # Web 启动脚本
├── tests/                    # 测试套件
├── web/                      # Web 前端
└── docs/                     # 文档
```

---

## 代码规范

### Python 版本

- 要求: Python >= 3.10
- 类型提示: 必须使用

### 代码风格

- 使用 `ruff` 进行代码检查
- 行长度限制: 100 字符
- 遵循 PEP 8

### 测试规范

- 使用 `pytest` 框架
- 测试路径: `tests/`
- 异步测试: `pytest-asyncio`

---

## 依赖管理

### 核心依赖

```toml
[project]
requires-python = ">=3.10"
dependencies = [
    "anthropic>=0.18.0",
]
```

### 开发依赖

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.1.0",
]
```

---

## 部署

### 安装

```bash
pip install -e .
```

### 开发模式

```bash
pip install -e ".[dev]"
```

### 运行测试

```bash
pytest -v
```

### 代码检查

```bash
ruff check .
ruff format .
```

---

## 版本历史

### v0.1.0 (当前版本)

**日期**: 2026-04-08

**新增功能**:
- `_run_agent_task` 后台任务实现
- Skill Slash Command 系统
- `slash_parser.py` 模块

**Bug 修复**:
- 无

**Breaking Changes**:
- 无
