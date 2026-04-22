# Claude Agent - AGENTS.md

Reference implementation of Claude Code's agent architecture in Python.

## Project Structure

```
claude-agent/
├── scripts/
│   ├── agent.py          # Core agent loop, streaming, LLM integration
│   ├── tool.py           # BaseTool interface, ToolRegistry
│   ├── tools.py          # Built-in tools: Read, Bash, Write, Grep, Glob, Edit
│   ├── permission.py     # Pattern-matching permission engine
│   ├── context.py         # Layered context injection (git, cwd, date)
│   ├── system_prompt.py   # Prompt engineering
│   ├── web_server.py      # HTTP server with SSE streaming
│   ├── cmd.py             # CLI entry point
│   ├── run.py             # Interactive/repl entry point
│   └── compat.py          # Cross-platform import fixes
├── web/
│   └── index.html         # Web dashboard UI
├── start_web.py           # Web server launcher
└── SKILL.md               # Skill documentation
```

## Running the Agent

```bash
# Web dashboard (default port 18780)
python start_web.py

# Web dashboard on custom port
python start_web.py --port 18779

# Interactive CLI mode
python scripts/run.py

# Single message via CLI
python scripts/run.py "帮我看看当前目录"

# CLI session management
python scripts/run.py --session my_session "hello"  # 指定会话
python scripts/run.py --resume session_id           # 恢复会话
python scripts/run.py --fork session_id             # Fork 会话
python scripts/run.py --worktree feature            # 使用 worktree

# CLI subcommands
python scripts/cmd.py start
python scripts/cmd.py status
python scripts/cmd.py chat "hello"
python scripts/cmd.py list                           # 列出所有会话
```

## Architecture

### Core Flow (agent.py)

1. Build system prompt (tools + context)
2. Send messages to LLM
3. Parse response (text or tool calls)
4. Check permissions before executing tools
5. Execute tools, stream progress events
6. Loop until task completion

### Tool Interface (tool.py)

Every tool inherits `BaseTool` and must define:
- `name` - tool identifier
- `description` - what it does
- `input_schema` - JSON Schema for validation
- `call(args, context)` - async execution logic

```python
from tool import BaseTool, ToolResult

class MyTool(BaseTool):
    name = "MyTool"
    description = "Does something"
    input_schema = {
        "type": "object",
        "properties": {"arg1": {"type": "string"}},
        "required": ["arg1"]
    }

    async def call(self, args, context) -> ToolResult:
        return ToolResult(success=True, data={"result": args["arg1"]})
```

### Permission Engine (permission.py)

Pattern-based rules: `ToolName(args)` format with glob matching.

```python
from permission import PermissionEngine
engine = PermissionEngine()
engine.allow("Bash(git *)")
engine.deny("Bash(rm *)")
engine.deny("Edit(*.env)")
result = engine.check("Bash", {"command": "rm -rf /tmp"})
# result.behavior: "allow" | "deny" | "ask"
```

## Multi-Agent System

The agent supports a **multi-layer agent orchestration** based on task complexity:

| Level | Description | Use Case |
|-------|-------------|----------|
| L1 | Single agent direct execution | Simple, single-step tasks |
| L2 | Decompose → Review → Execute | Multi-file, multi-step tasks |
| L3 | Subdomain parallel + Global review | Complex cross-domain tasks |

See [`docs/MULTI_AGENT_DESIGN.md`](docs/MULTI_AGENT_DESIGN.md) for the complete design specification.

## Built-in Tools

| Tool | Purpose | Key Params |
|------|---------|------------|
| Read | Read file content | `file_path`, `max_lines` (default 100), `offset` |
| Bash | Execute shell commands | `command`, `timeout` (default 30s), `cwd` |
| Write | Create/overwrite file | `file_path`, `content`, `append` (default false) |
| Grep | Search text in files | `pattern`, `path`, `recursive`, `ignore_case` |
| Glob | Search files by pattern | `pattern` (e.g., `**/*.py`), `cwd`, `max_results` |
| Edit | Precise text replacement | `file_path`, `oldText`, `newText` |
| Agent | Launch subagent | `description`, `prompt`, `subagent_type`, `run_in_background` |
| TaskCreate | Create task | `subject`, `description` |
| TaskList | List tasks | - |
| TaskUpdate | Update task | `taskId`, `status`, etc. |
| TeamCreate | Create team | `name`, `members` |
| TeamList | List teams | `team_name` (optional) |
| TeamSendMessage | Send team message | `team_name`, `to`, `content` |
| WorktreeCreate | Create Git worktree | `name`, `branch` |
| WorktreeList | List worktrees | - |

## Slash Commands

The agent supports `/skill-name args` format for invoking skills:

```bash
/skill-name arg1 arg2
```

**Execution Modes:**
- **INLINE** (default): Skill content is expanded and injected into the conversation as context
- **FORK**: Skill is executed as a separate subagent

**Built-in Skill Tools:**

| Tool | Purpose | Key Params |
|------|---------|-------------|
| Skill | Execute a skill | `skill`, `args` |
| SkillList | List all available skills | - |
| SkillInfo | Get skill details | `skill` |

## Edit Tool Error Recovery

The Edit tool has automatic error recovery when `oldText` doesn't match:

1. **Strip whitespace** - removes leading/trailing whitespace before matching
2. **Normalize whitespace** - converts tabs/spaces interchangeably
3. **Fuzzy line matching** - finds most similar line sequence

Recovery results include a `warning` field explaining what was auto-fixed. If all strategies fail, returns similar lines as candidates.

## SSE Streaming Events (web_server.py)

When calling `/api/chat` with `stream: true`, events are:

| Type | Description | Key Fields |
|------|-------------|------------|
| `thinking` | LLM processing | `content` |
| `text` | LLM text response | `content` |
| `tool_start` | Tool execution begins | `tool`, `args` |
| `tool_progress` | Edit 3-phase progress | `tool`, `content`, `recovered` |
| `tool_recovered` | Auto-recovery succeeded | `tool`, `warning` |
| `tool_result` | Tool completed | `tool`, `success`, `data` |
| `tool_error` | Tool failed | `tool`, `error` |
| `done` | Conversation complete | `content` (final text) |

## LLM Tool Call Format

The agent expects LLM responses in this format:
```
[调用 工具名 工具: {"param": "value"}]
```

Example:
```
[调用 Read 工具: {"file_path": "README.md", "max_lines": 100}]
```

The agent also parses structured `tool_use` blocks from Anthropic/OpenAI format responses.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Send message, `stream: true` for SSE |
| `/api/session` | POST | Get session history |
| `/api/status` | GET | Service status |
| `/api/stats` | GET | Token usage statistics |
| `/api/usage` | GET | Usage with time range filter |
| `/api/history` | GET | Conversation history |
| `/api/sessions` | GET | All sessions |

## Cross-Platform Handling

- **Windows paths**: `D:\path` automatically converted to `/mnt/d/path` in WSL
- **Command translation**: Linux commands (ls, grep, cat) translated to Windows equivalents (dir, findstr, type)
- **UNC paths**: `\\server\share` converted to `/mnt/unc/server/share`

## API Configuration

LLM settings in `agent.py`:
```python
LLM_PROVIDER = "minimax"
LLM_API_URL = "https://api.minimaxi.com/anthropic/v1/messages"
LLM_MODEL = "MiniMax-M2.7"
```

To use a different provider, modify these constants or inject via `AgentConfig`.

## Non-Obvious Patterns

1. **Edit tool parameter names**: Uses `oldText`/`newText` (camelCase), not snake_case
2. **Tool results format**: Return `ToolResult(success=bool, data=any, error=Optional[str])`
3. **Glob patterns**: Use `**/*.py` for recursive, `*.py` for single directory
4. **Bash timeout**: Default 30s, dangerous commands not auto-killed
5. **System prompt building**: Automatically prepends git status and cwd info as context
6. **Tool call parsing**: Falls back to regex extraction from thinking blocks if structured blocks missing
7. **Write append mode**: `append: true` creates file if missing, appends if exists

---

## Development Setup

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest -v

# Lint code
ruff check .

# Format code
ruff format .
```

Or use `make`:
```bash
make install   # Install dependencies
make test      # Run tests
make lint      # Check linting
make format    # Auto-format code
make clean     # Clean cache files
```

## Project Configuration

- `pyproject.toml` - pytest and ruff configuration
- `Makefile` - Development commands
- `tests/` - Test suite with pytest

## CI/CD

GitHub Actions CI runs on push/PR to `main`:
1. Install dependencies
2. Run `pytest`
3. Run `ruff check .`

**Note**: The CI workflow file (`.github/workflows/ci.yml`) must be created via GitHub web UI if push API fails.
