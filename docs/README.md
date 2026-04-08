# Claude Agent

参考 Claude Code 架构设计的 Agent 实现，支持多工具集成、权限控制、插件系统和 Hook 机制。

## 安装

```bash
pip install -e .
```

## 快速开始

### Web 界面

```bash
python start_web.py
```

### 命令行交互

```bash
python scripts/run.py
```

### 单次对话

```bash
python scripts/run.py "帮我看看当前目录"
```

## 项目结构

```
claude-agent/
├── scripts/
│   ├── agent.py          # 核心 Agent 循环
│   ├── tool.py           # 工具基类和注册表
│   ├── tools.py          # 内置工具 (Read, Bash, Write, Grep, Glob, Edit)
│   ├── permission.py     # 权限引擎
│   ├── hooks.py          # Hook 系统
│   ├── plugins.py        # 插件系统
│   └── ...
├── tests/                # 测试套件
├── web/                  # Web 界面
└── start_web.py          # Web 服务入口
```

## 内置工具

| 工具 | 说明 |
|------|------|
| Read | 读取文件内容 |
| Bash | 执行 shell 命令 |
| Write | 创建/覆写文件 |
| Grep | 文本搜索 |
| Glob | 文件模式匹配 |
| Edit | 精确文本替换 |

## 配置

编辑 `crush.json` 配置 LLM 提供商、工具权限等。

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest -v

# 代码检查
ruff check .

# 自动格式化
ruff format .
```

## License

MIT
