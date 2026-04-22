# Claude Agent 测试文档

> 本文档记录项目的测试策略、测试用例和测试覆盖情况。

---

## 测试概览

| 指标 | 数值 |
|------|------|
| 总测试数 | 325 |
| 通过数 | 321 |
| 跳过数 | 4 |
| 失败数 | 0 |

---

## 测试框架

### 工具

- **测试框架**: `pytest`
- **异步测试**: `pytest-asyncio`
- **代码检查**: `ruff`

### 配置

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

---

## 测试结构

```
tests/
├── test_agent.py          # Agent、工具注册、权限测试
├── test_tools.py          # 基础工具测试
├── test_advanced_tools.py # 高级工具测试
├── test_hooks.py          # Hook 系统测试
├── test_compact.py        # 上下文压缩测试
├── test_mcp.py            # MCP 相关测试
├── test_memory.py         # 记忆系统测试
├── test_multi_agent.py    # 多智能体测试
├── test_plan.py           # 计划模式测试
├── test_security.py      # 安全相关测试
├── test_subagent.py       # 子代理测试
├── test_task.py           # 任务系统测试
├── test_web.py            # Web 服务测试
└── test_worktree.py       # Worktree 测试
```

---

## 测试详情

### 1. test_agent.py

**测试文件**: `tests/test_agent.py`

| 测试类 | 测试数 | 描述 |
|--------|--------|------|
| TestAgentConfig | 2 | Agent 配置测试 |
| TestToolRegistry | 2 | 工具注册表测试 |
| TestReadToolValidation | 2 | Read 工具输入验证 |
| TestBashToolDestructive | 2 | Bash 工具破坏性检测 |
| TestWriteToolDestructive | 2 | Write 工具破坏性检测 |
| TestPermissionEngine | 4 | 权限引擎测试 |
| TestContextBuilder | 2 | 上下文构建测试 |
| TestSystemPromptBuilder | 1 | 系统提示词构建测试 |

**关键测试用例**:

```python
def test_tool_registration():
    """测试工具注册和查找"""
    registry = ToolRegistry()
    registry.register(ReadTool())
    tool = registry.find("Read")
    assert tool is not None
    assert tool.name == "Read"

def test_permission_engine_glob_matching():
    """测试 glob 模式匹配"""
    engine = PermissionEngine()
    engine.allow("Bash(git *)")
    engine.deny("Bash(rm *)")

    result = engine.check("Bash", {"command": "git status"})
    assert result.behavior == "allow"

    result = engine.check("Bash", {"command": "rm -rf /"})
    assert result.behavior == "deny"
```

---

### 2. test_tools.py

**测试文件**: `tests/test_tools.py`

| 测试类 | 测试数 | 描述 |
|--------|--------|------|
| TestReadTool | 2 | Read 工具 |
| TestWriteTool | 2 | Write 工具 |
| TestEditTool | 4 | Edit 工具（含错误恢复） |
| TestBashTool | 2 | Bash 工具 |
| TestGlobTool | 1 | Glob 工具 |

**关键测试用例**:

```python
def test_edit_exact_match():
    """测试 Edit 工具精确匹配"""
    # 创建一个测试文件
    content = "Hello World"
    tool = EditTool()
    result = tool.call({
        "file_path": test_file,
        "oldText": "World",
        "newText": "Claude"
    })
    assert result.success == True

def test_edit_recovery_whitespace():
    """测试 Edit 工具空白字符恢复"""
    tool = EditTool()
    result = tool.call({
        "file_path": test_file,
        "oldText": "  Hello  ",  # 额外空格
        "newText": "Hi"
    })
    assert result.success == True
```

---

### 3. test_advanced_tools.py

**测试文件**: `tests/test_advanced_tools.py`

| 测试类 | 测试数 | 描述 |
|--------|--------|------|
| TestTaskTools | 4 | Task 工具测试 |
| TestTodoWriteTool | 1 | Todo 工具测试 |
| TestWebFetchTool | 2 | WebFetch 工具测试 |
| TestWorktreeTools | 3 | Worktree 工具测试 |

---

### 4. test_hooks.py

**测试文件**: `tests/test_hooks.py`

| 测试类 | 测试数 | 描述 |
|--------|--------|------|
| TestHookEvents | 2 | Hook 事件测试 |
| TestHookResult | 2 | Hook 结果测试 |
| TestHookConfig | 2 | Hook 配置测试 |
| TestHook | 6 | 基本 Hook 测试 |
| TestEnhancedHookManager | 10 | 增强 Hook 管理器测试 |
| TestHookCondition | 5 | Hook 条件测试 |
| TestHttpHook | 4 | HTTP Hook 测试 |
| TestLoadHttpHooksFromConfig | 4 | HTTP Hook 配置加载测试 |
| TestLoadFromConfig | 4 | Hook 配置加载测试 |

**关键测试用例**:

```python
def test_enhanced_hook_manager_trigger():
    """测试增强 Hook 管理器触发"""
    manager = EnhancedHookManager()
    executed = []

    async def callback(context):
        executed.append(True)
        return HookResult(success=True)

    manager.register("PreToolUse", callback)
    result = await manager.trigger("PreToolUse", {"tool": "Read"})
    assert result.success == True
    assert len(executed) == 1
```

---

### 5. test_compact.py

**测试文件**: `tests/test_compact.py`

| 测试类 | 测试数 | 描述 |
|--------|--------|------|
| TestTokenCounter | 4 | Token 计数测试 |
| TestCompactConfig | 2 | 压缩配置测试 |
| TestCompactManager | 6 | 压缩管理器测试 |
| TestCompactionResult | 2 | 压缩结果测试 |
| TestReactiveCompact | 3 | 响应式压缩测试 |
| TestCompactIntegration | 2 | 压缩集成测试 |

---

### 6. test_mcp.py

**测试文件**: `tests/test_mcp.py`

| 测试类 | 测试数 | 描述 |
|--------|--------|------|
| TestMCPClient | 5 | MCP 客户端测试 |
| TestMCPServerManager | 3 | MCP 服务器管理测试 |
| TestMCPTool | 2 | MCP 工具测试 |
| TestMCPConfig | 3 | MCP 配置测试 |

---

### 7. test_memory.py

**测试文件**: `tests/test_memory.py`

| 测试类 | 测试数 | 描述 |
|--------|--------|------|
| TestMemoryStore | 5 | 记忆存储测试 |
| TestSessionMemory | 3 | 会话记忆测试 |
| TestLLMChooser | 2 | LLM 选择器测试 |
| TestFreshnessChecker | 2 | 新鲜度检查器测试 |

---

### 8. test_multi_agent.py

**测试文件**: `tests/test_multi_agent.py`

| 测试类 | 测试数 | 描述 |
|--------|--------|------|
| TestHybridRouter | 4 | 混合路由器测试 |
| TestL2Decomposer | 3 | L2 分解器测试 |
| TestL3Decomposer | 2 | L3 分解器测试 |
| TestReviewer | 3 | 审核器测试 |
| TestExecutor | 3 | 执行器测试 |
| TestLayerSession | 4 | 层会话测试 |

---

### 9. test_plan.py

**测试文件**: `tests/test_plan.py`

| 测试类 | 测试数 | 描述 |
|--------|--------|------|
| TestVerifyPlanExecutionTool | 4 | 验证计划执行工具测试 |
| TestPlanStepCondition | 5 | 步骤条件测试 |
| TestInterviewPhase | 2 | 澄清阶段测试 |
| TestRollbackManager | 3 | 回滚管理器测试 |

---

### 10. test_security.py

**测试文件**: `tests/test_security.py`

| 测试类 | 测试数 | 描述 |
|--------|--------|------|
| TestAutoClassifier | 2 | 自动分类器测试 |
| TestPathSecurityValidation | 8 | 路径安全验证测试 |

**关键测试用例**:

```python
def test_path_traversal_detected():
    """测试路径遍历检测"""
    validator = PathSecurityValidator()

    # 恶意路径
    assert validator.is_safe("../../../etc/passwd") == False
    assert validator.is_safe("C:\\Windows\\System32\\config\\sam") == False

    # 安全路径
    assert validator.is_safe("src/app/main.py") == True
```

---

### 11. test_subagent.py

**测试文件**: `tests/test_subagent.py`

| 测试类 | 测试数 | 描述 |
|--------|--------|------|
| TestSubagentType | 3 | 子代理类型测试 |
| TestToolFilter | 6 | 工具过滤测试 |
| TestSubagentPrompts | 4 | 子代理提示词测试 |
| TestSubagentRegistry | 3 | 子代理注册表测试 |

---

### 12. test_worktree.py

**测试文件**: `tests/test_worktree.py`

| 测试类 | 测试数 | 描述 |
|--------|--------|------|
| TestWorktreeInfo | 2 | Worktree 信息测试 |
| TestWorktreeManager | 5 | Worktree 管理器测试 |
| TestWorktreeBase | 1 | Worktree 基础测试 |

---

## Phase 1 新功能测试

### 1.1 `_run_agent_task` 测试

**测试文件**: `tests/test_task.py`

**测试用例**:

```python
async def test_run_agent_task():
    """测试 Agent 类型后台任务"""
    from scripts.task.runner import BackgroundTaskRunner
    from scripts.task.models import Task, TaskType, BackgroundTask

    runner = BackgroundTaskRunner()
    task = Task(
        id="test-agent-task",
        subject="Test Agent Task",
        task_type=TaskType.AGENT,
        metadata={
            "prompt": "Say hello",
            "description": "Test task",
            "subagent_type": "GeneralPurpose"
        }
    )

    bg_task = await runner.run_task(task, "session-1")

    assert bg_task.task.status == TaskStatus.IN_PROGRESS
    assert bg_task.future is not None
```

---

### 1.2 Slash Command 测试

**测试文件**: `tests/test_skill.py` (需新建)

**测试用例**:

```python
def test_parse_slash_command():
    """测试 slash 命令解析"""
    from scripts.skill.slash_parser import parse_slash_command

    # 基本格式
    result = parse_slash_command("/help")
    assert result.skill_name == "help"
    assert result.arguments == ""

    # 带参数
    result = parse_slash_command("/test arg1 arg2")
    assert result.skill_name == "test"
    assert result.arguments == "arg1 arg2"

    # 普通消息
    result = parse_slash_command("normal message")
    assert result is None

def test_is_slash_command():
    """测试 slash 命令识别"""
    from scripts.skill.slash_parser import is_slash_command

    assert is_slash_command("/skill") == True
    assert is_slash_command("normal") == False
    assert is_slash_command("/") == False
    assert is_slash_command("//skill") == False
```

---

### 1.3 Skill 工具测试

**测试文件**: `tests/test_skill.py`

**测试用例**:

```python
async def test_skill_list_tool():
    """测试 SkillList 工具"""
    from scripts.skill.skill_tool import SkillListTool

    tool = SkillListTool()
    result = await tool.call({}, {})

    assert result.success == True
    assert "skills" in result.data
    assert "count" in result.data

async def test_skill_info_tool():
    """测试 SkillInfo 工具"""
    from scripts.skill.skill_tool import SkillInfoTool

    tool = SkillInfoTool()
    result = await tool.call({"skill": "code-review"}, {})

    # 假设 code-review skill 存在
    assert result.success == True
    assert result.data["name"] == "code-review"
```

---

## 运行测试

### 运行所有测试

```bash
pytest -v
```

### 运行特定测试文件

```bash
pytest tests/test_agent.py -v
```

### 运行特定测试类

```bash
pytest tests/test_agent.py::TestPermissionEngine -v
```

### 运行特定测试

```bash
pytest tests/test_agent.py::TestPermissionEngine::test_allow_pattern -v
```

### 运行带标记的测试

```bash
pytest -v -m "not slow"
```

### 生成覆盖率报告

```bash
pytest --cov=scripts --cov-report=html
```

---

## 测试覆盖率目标

| 模块 | 目标覆盖率 |
|------|-----------|
| agent.py | 80%+ |
| tool.py | 90%+ |
| tools.py | 85%+ |
| permission.py | 90%+ |
| hooks.py | 85%+ |
| 整体 | 80%+ |

---

## 持续集成

### pre-commit 检查

```bash
# 运行所有检查
ruff check .
ruff format --check .

# 自动修复
ruff check --fix .
ruff format .
```

### 测试命令

```bash
# 快速测试
pytest -x -q

# 详细测试
pytest -v --tb=long

# 带覆盖率
pytest --cov=scripts --cov-report=term-missing
```

---

## Mock 策略

### 外部依赖

- LLM API: 使用 mock
- 文件系统: 使用 `tmp_path` fixture
- 网络请求: 使用 `responses` 或 `aioresponses`

### 示例

```python
@pytest.fixture
def mock_llm_response():
    """Mock LLM API 响应"""
    return {
        "choices": [{
            "message": {
                "content": "Test response"
            }
        }]
    }

async def test_agent_with_mock(mocker, mock_llm_response):
    """使用 mock 测试 agent"""
    mocker.patch("scripts.agent.call_llm", return_value=mock_llm_response)
    agent = Agent(config)
    result = await agent.run("test message")
    assert "Test response" in result
```
