# Claude Agent 开发路线图

> 本文档是项目的总体开发规划，汇总需求、进度和计划。

---

## 项目概述

**项目名称**: Claude Agent
**架构参考**: Claude Code
**目标**: 实现一个功能完善的 CLI/Web AI 助手
**当前版本**: 0.1.0

---

## 功能模块

### 1. 核心 Agent

| 功能 | 状态 | 说明 |
|------|------|------|
| Agent 核心循环 | ✅ 已完成 | 流式输出、并行工具执行、错误恢复 |
| 工具系统 | ✅ 已完成 | Read/Write/Edit/Bash/Grep/Glob 等 |
| 权限系统 | ✅ 已完成 | allow/deny/ask 三级控制 |
| Hook 系统 | ✅ 已完成 | 33 种事件类型 |
| 插件系统 | ✅ 已完成 | 动态安装/卸载 |

### 2. 后台任务

| 功能 | 状态 | 说明 |
|------|------|------|
| Bash 任务 | ✅ 已完成 | 后台执行 shell 命令 |
| Agent 任务 | ✅ 已完成 | 后台执行子代理 |
| TaskOutput 流式 | ✅ 已完成 | 实时获取任务输出 |

### 3. 技能系统 (Skills)

| 功能 | 状态 | 说明 |
|------|------|------|
| Skill 加载器 | ✅ 已完成 | 从目录发现和加载 |
| Slash Commands | ✅ 已完成 | /skill-name args 格式 |
| INLINE 模式 | ✅ 已完成 | 展开到当前对话 |
| FORK 模式 | ✅ 已完成 | 子代理独立执行 |
| SkillListTool | ✅ 已完成 | 列出所有技能 |
| SkillInfoTool | ✅ 已完成 | 获取技能详情 |

### 4. MCP 支持

| 功能 | 状态 | 说明 |
|------|------|------|
| MCP 客户端 | ✅ 已完成 | 支持 stdio/SSE/HTTP/WebSocket |
| MCP 服务器管理 | ✅ 已完成 | 多服务器管理 |
| channelNotification | ✅ 已完成 | 服务器主动推送 |

### 5. 多智能体

| 功能 | 状态 | 说明 |
|------|------|------|
| 复杂度路由 | ✅ 已完成 | L1/L2/L3 分层 |
| 任务分解 | ✅ 已完成 | Decomposer 实现 |
| 执行器 | ✅ 已完成 | 带约束执行 |
| 审核器 | ✅ 已完成 | 结果审核 |

### 6. 计划模式

| 功能 | 状态 | 说明 |
|------|------|------|
| 进入/退出 | ✅ 已完成 | PlanModeManager |
| 步骤管理 | ✅ 已完成 | 批准/拒绝/执行 |
| 执行验证 | ✅ 已完成 | VerifyPlanExecutionTool |
| 回滚支持 | ✅ 已完成 | RollbackManager |

### 7. 会话与记忆

| 功能 | 状态 | 说明 |
|------|------|------|
| 会话管理 | ✅ 已完成 | 创建/恢复/派生 |
| 记忆存储 | ✅ 已完成 | MemoryStore |
| 记忆检索 | ✅ 已完成 | MemoryRetriever |

---

## 开发阶段

### Phase 1: 核心补充 (2026-04-08) ✅ 已完成

| 功能 | 状态 |
|------|------|
| `_run_agent_task` 实现 | ✅ |
| Skill Slash Command 系统 | ✅ |
| SkillListTool / SkillInfoTool | ✅ |

### Phase 2: 重要功能 (2026-04-08) ✅ 已完成

| 功能 | 状态 |
|------|------|
| MCP channelNotification | ✅ |
| 增强 Hook 事件 (LLMStart/Complete 等) | ✅ |
| TaskOutput 流式输出 | ✅ |

### Phase 3: 新工具 (已完成)

| 功能 | 优先级 | 说明 |
|------|--------|------|
| REPLTool | P2 | 交互式 REPL |
| ConfigTool | P2 | 运行时配置 |
| ToolSearchTool | P2 | 工具发现 |
| MonitorTool | P2 | 系统监控 |

### Phase 4: 架构优化 (已完成)

| 功能 | 优先级 | 说明 |
|------|--------|------|
| StructuredIO 集成 | P3 | 集成到主循环 |
| MCP OAuth | P3 | OAuth 认证 |
| SSH/Daemon | P3 | SSH 守护进程 |

---

## 文档索引

| 文档 | 说明 |
|------|------|
| `docs/REQUIREMENTS.md` | 详细功能需求清单 |
| `docs/DEVELOPMENT.md` | 开发历史和实现细节 |
| `docs/TESTING.md` | 测试策略和用例 |
| `docs/ROADMAP.md` | 本文档 - 总体路线图 |

---

## 测试覆盖率

| 指标 | 数值 |
|------|------|
| 总测试数 | 533 |
| 通过数 | 533 |
| 跳过数 | 4 |

运行命令: `pytest -v`

---

## 下一步

1. **持续**: 补充测试用例，提高覆盖率
2. **探索**: 新功能提案和优化
