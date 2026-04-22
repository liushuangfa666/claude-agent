# Claude Agent 需求文档

> 本文档记录项目的功能需求、优先级和实现状态。

---

## 概述

本项目是参考 Claude Code 架构设计的 Agent 实现，目标是一个功能完善的 CLI/Web AI 助手，支持多工具集成、权限控制、插件系统和 Hook 机制。

---

## 一、核心功能需求

### 1.1 Agent 核心循环

**状态**: ✅ 已完成

**需求**:
- 流式输出支持
- 并行工具执行
- 错误恢复机制
- 多轮对话支持

**实现文件**: `scripts/agent.py`

---

### 1.2 工具系统

**状态**: ✅ 已完成

**需求**:

| 工具 | 描述 | 优先级 |
|------|------|--------|
| Read | 读取文件内容 | P0 |
| Write | 创建/覆写文件 | P0 |
| Edit | 精准文本替换 | P0 |
| Bash | 执行 shell 命令 | P0 |
| Grep | 文本搜索 | P1 |
| Glob | 文件模式匹配 | P1 |
| Agent | 启动子代理 | P1 |
| TaskCreate/List/Update | 任务管理 | P1 |
| Skill/SkillList/SkillInfo | 技能管理 | P1 |
| TeamCreate/List/SendMessage | 团队协作 | P2 |
| WorktreeCreate/List/Remove | Git worktree | P2 |
| WebFetch/WebSearch | Web 工具 | P2 |
| EnterPlanMode/ExitPlanMode | 计划模式 | P2 |
| TodoWrite | Todo 工具 | P3 |

**实现文件**:
- 基础工具: `scripts/tools.py`
- 高级工具: `scripts/tools_advanced.py`
- 工具基类: `scripts/tool.py`

---

### 1.3 权限系统

**状态**: ✅ 已完成

**需求**:
- 模式匹配规则 (`ToolName(args)` 格式)
- 三级行为: `allow` / `deny` / `ask`
- 自动拒绝追踪（连续拒绝后自动拒绝）
- 路径保护

**实现文件**: `scripts/permission.py`

---

### 1.4 Hook 系统

**状态**: ✅ 已完成

**需求**:

| 事件类型 | 描述 | 状态 |
|---------|------|------|
| SessionStart | 会话开始 | ✅ |
| SessionEnd | 会话结束 | ✅ |
| UserPromptSubmit | 用户提交消息 | ✅ |
| PreToolUse | 工具执行前 | ✅ |
| PostToolUse | 工具执行后 | ✅ |
| PostToolUseFailure | 工具执行失败 | ✅ |
| PreCompact | 压缩前 | ✅ |
| PostCompact | 压缩后 | ✅ |
| LLMStart | LLM 开始调用 | ✅ |
| LLMComplete | LLM 完成调用 | ✅ |
| ToolUseBlocked | 工具被阻止 | ✅ |
| ToolUseDenied | 工具被拒绝 | ✅ |
| PreAgentCreate | 子代理创建前 | ✅ |
| PostAgentCreate | 子代理创建后 | ✅ |

**实现文件**:
- 基础 Hook: `scripts/hooks.py`
- 增强 Hook: `scripts/hooks/enhanced.py`

---

### 1.5 插件系统

**状态**: ✅ 已完成

**需求**:
- 插件安装/卸载/启用/禁用
- 动态工具注册
- 动态 Hook 注册
- 插件元数据管理

**实现文件**: `scripts/plugins.py`

---

## 二、后台任务系统

### 2.1 TaskType 枚举

**状态**: ✅ 已完成

**需求**:
```python
class TaskType(str, Enum):
    BASH = "bash"      # ✅ 已实现
    AGENT = "agent"    # ✅ 已实现
    WORKFLOW = "workflow"  # 🔲 未实现
```

---

### 2.2 后台任务执行

**状态**: ✅ 已完成 (Agent 类型)

**需求**:
- Bash 任务后台执行
- Agent 任务后台执行
- 任务状态跟踪
- 任务输出获取
- 任务停止支持

**实现文件**: `scripts/task/runner.py`

---

## 三、技能系统 (Skills)

### 3.1 Slash Command

**状态**: ✅ 已完成

**需求**:
- 格式: `/skill-name arg1 arg2`
- INLINE 模式: 展开到当前对话
- FORK 模式: 子代理独立执行

**实现文件**:
- 解析器: `scripts/skill/slash_parser.py`
- 集成: `scripts/agent.py`

---

### 3.2 Skill 执行模式

**状态**: ✅ 已完成

**需求**:
```python
class SkillExecutionMode(str, Enum):
    INLINE = "inline"  # prompt 展开到当前对话
    FORK = "fork"      # 子代理独立运行
```

---

### 3.3 Skill 加载与发现

**状态**: ✅ 已完成

**需求**:
- 从 `.crush/skills/<name>/` 加载
- 从 `~/.config/crush/skills/<name>/` 加载
- Skill frontmatter 解析
- 内联命令展开 (`!`command``)

**实现文件**: `scripts/skill/loader.py`, `scripts/skill/parser.py`

---

## 四、MCP 支持

### 4.1 MCP 客户端

**状态**: ✅ 已完成

**需求**:
- STDIO 传输
- SSE 传输
- HTTP 传输
- WebSocket 传输

**实现文件**: `scripts/mcp/mcp_client.py`

---

### 4.2 MCP 服务器管理

**状态**: ✅ 已完成

**需求**:
- 多服务器管理
- 工具包装
- 配置验证

**实现文件**: `scripts/mcp/mcp_manager.py`

---

### 4.3 MCP channelNotification

**状态**: ✅ 已完成

**需求**:
- 服务器主动推送通知
- notification 处理器

**实现文件**: `scripts/mcp/mcp_client.py`

---

## 五、多智能体系统

### 5.1 复杂度路由

**状态**: ✅ 已完成

**需求**:
- L1: 单代理直接执行
- L2: 分解 → 审核 → 执行
- L3: 子域并行 + 全局审核

**实现文件**: `scripts/multi_agent/router.py`

---

### 5.2 任务分解

**状态**: ✅ 已完成

**实现文件**: `scripts/multi_agent/decomposer.py`

---

## 六、计划模式

### 6.1 核心功能

**状态**: ✅ 已完成

**需求**:
- 进入/退出计划模式
- 步骤添加/批准/拒绝
- 执行验证
- 回滚支持

**实现文件**: `scripts/plan_mode.py`, `scripts/plan/`

---

## 七、会话与记忆

### 7.1 会话管理

**状态**: ✅ 已完成

**需求**:
- 会话创建/恢复/派生
- 多会话支持
- 元数据管理

**实现文件**: `scripts/session/manager.py`

---

### 7.2 记忆系统

**状态**: ✅ 已完成

**需求**:
- 记忆存储
- 记忆检索
- LLM 辅助选择
- 新鲜度检查

**实现文件**: `scripts/memory/memory_retriever.py`

---

## 八、Web 服务

### 8.1 HTTP API

**状态**: ✅ 已完成

**端点**:
- `POST /api/chat` - 发送消息
- `GET /api/session` - 获取会话
- `GET /api/status` - 服务状态
- `GET /api/stats` - Token 统计
- `GET /api/sessions` - 所有会话

**实现文件**: `scripts/web_server.py`

---

### 8.2 SSE 流式输出

**状态**: ✅ 已完成

**事件类型**:
- `thinking` - LLM 处理中
- `text` - 文本回复
- `tool_start` - 工具开始
- `tool_progress` - 执行进度
- `tool_result` - 工具结果
- `tool_error` - 工具错误
- `done` - 完成

---

## 九、待开发功能

### 9.1 高优先级

| 功能 | 描述 | 状态 |
|------|------|------|
| Task - Agent 任务 | 后台 Agent 任务执行 | ✅ 已完成 |
| Skill Slash Commands | /skill-name 命令 | ✅ 已完成 |
| MCP channelNotification | 服务器通知 | ✅ 已完成 |

### 9.2 中优先级

| 功能 | 描述 | 状态 |
|------|------|------|
| REPLTool | 交互式 REPL | 🔲 待开发 |
| ConfigTool | 运行时配置 | 🔲 待开发 |
| ToolSearchTool | 工具发现 | 🔲 待开发 |
| MonitorTool | 系统监控 | 🔲 待开发 |
| Enhanced Hook Events | 增强 Hook 事件 (LLMStart/Complete等) | ✅ 已完成 |
| TaskOutput 增强 | 流式输出支持 | ✅ 已完成 |

### 9.3 低优先级

| 功能 | 描述 | 状态 |
|------|------|------|
| StructuredIO 集成 | 集成到主循环 | 🔲 待开发 |
| MCP OAuth | OAuth 认证 | 🔲 待开发 |
| SSH/Daemon | SSH 守护进程 | 🔲 待开发 |

---

## 十、非功能性需求

### 10.1 性能

- LLM API 调用超时控制
- 工具并行执行
- 上下文压缩

### 10.2 安全

- 路径遍历保护
- 危险操作标记
- 权限引擎

### 10.3 可扩展性

- 插件系统
- 自定义 Hook
- 工具注册表

---

## 附录

### A. 配置文件

- `crush.json` - LLM 配置
- `claude.json` - IDE 配置
- `~/.claude-agent/` - 用户数据目录

### B. 环境变量

- `CRUSH_API_KEY` - API 密钥
- `CRUSH_API_URL` - API 地址
- `CRUSH_MODEL` - 模型名称
