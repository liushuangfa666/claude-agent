# Claude Agent

参考 Claude Code 架构设计的 Agent 实现，支持工具调用、权限引擎、SSE 流式输出。

## 特性

- 核心 Agent 循环，参考 Claude Code 架构
- 工具注册表 + JSON Schema 校验
- 模式匹配权限引擎
- 分层上下文注入
- 系统提示词构建
- HTTP 服务 + SSE 流式输出
- 跨平台支持（Windows/WSL/Linux）

## 安装

```bash
pip install -e .
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码检查
ruff check .
```

## 运行

```bash
# Web 界面
python start_web.py

# 命令行交互
python scripts/run.py
```
