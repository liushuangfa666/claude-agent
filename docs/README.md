# Claude Agent

参考 Claude Code 架构设计的 AI Agent，支持多工具集成、权限控制、插件系统和 Hook 机制。

## 系统要求

- Python >= 3.10
- Windows / macOS / Linux

## 安装

```bash
# 克隆仓库
git clone <repo-url>
cd claude-agent

# 安装依赖
pip install -e .
```

## 快速开始

### 1. 配置 API Key

编辑 `crush.json`：

```json
{
  "api_key": "your-api-key-here",
  "api_url": "https://api.minimaxi.com/anthropic/v1/messages",
  "model": "MiniMax-M2.7"
}
```

### 2. 启动 Web 界面（推荐）

```bash
python scripts/start_web.py
```

然后浏览器访问：**http://localhost:18780**

### 3. 命令行交互

```bash
# 交互模式
python scripts/run.py

# 单次对话
python scripts/run.py "帮我看看当前目录"
```

## 项目结构

```
claude-agent/
├── scripts/
│   ├── agent.py           # 核心 Agent 循环
│   ├── tool.py           # 工具基类和注册表
│   ├── tools.py          # 内置工具
│   ├── tools_advanced.py # 高级工具
│   ├── permission.py      # 权限引擎
│   ├── hooks.py          # Hook 系统
│   ├── plugins.py        # 插件系统
│   ├── mcp/              # MCP 客户端
│   ├── multi_agent/      # 多智能体
│   ├── plan/             # 计划模式
│   ├── session/          # 会话管理
│   ├── skill/            # 技能系统
│   ├── security/         # 安全模块
│   ├── server/           # HTTP 服务器
│   ├── web_server.py     # Web 服务入口
│   └── start_web.py       # 启动脚本
├── tests/                # 测试套件 (533 tests)
├── web/                  # Web UI 界面
└── docs/                 # 文档
```

## 内置工具

| 工具 | 说明 |
|------|------|
| Read | 读取文件 |
| Write | 写入文件 |
| Edit | 精确替换 |
| Bash | 执行命令 |
| Grep | 文本搜索 |
| Glob | 文件匹配 |
| WebFetch | 获取网页 |
| WebSearch | 网络搜索 |

## 高级功能

### MCP 支持
编辑 `scripts/mcp/example.mcp.json` 配置 MCP 服务器。

### 多 Agent 模式
```bash
python scripts/run.py --multi-agent
```

### 计划模式
输入 `/plan` 进入计划模式，逐步审批执行。

## 开发

```bash
# 运行测试
pytest -v

# 代码检查
ruff check .

# 格式化
ruff format .
```

## License

MIT
