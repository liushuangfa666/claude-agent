# MCP 使用指南

## 概述

Crush Agent 实现了 MCP (Model Context Protocol) 客户端，支持连接外部 MCP 服务器。

## MCP 服务器连接流程

```
1. 配置 MCP 服务器 (.mcp.json)
       ↓
2. load_mcp_config() 加载配置
       ↓
3. MCPServerManager 管理连接
       ↓
4. 连接到服务器 (stdio/http/sse/websocket)
       ↓
5. 获取工具列表并注册到 Agent
       ↓
6. Agent 可调用 mcp__server__tool 格式的工具
```

## 快速开始

### 1. 创建配置文件

在项目根目录或用户目录创建 `.mcp.json`:

```json
{
  "mcpVersion": "1.0",
  "mcpServers": {
    "github": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      }
    }
  }
}
```

### 2. 设置环境变量

```bash
export GITHUB_TOKEN="your-github-token"
```

### 3. 初始化 MCP

```python
from scripts.mcp import initialize_mcp, MCPServerManager

# 初始化并连接所有服务器
manager = await initialize_mcp()

# 获取已连接的服务器
servers = manager.get_connected_servers()
for name, info in servers.items():
    print(f"{name}: {len(info.tools)} tools")

# 获取所有可用工具
tools = manager.get_all_tools()
for tool in tools:
    print(f"  {tool.full_name}")
```

### 4. 调用 MCP 工具

```python
# 方式1: 通过 manager
result = await manager.call_tool(
    "github", 
    "create_issue", 
    {"owner": "user", "repo": "repo", "title": "Bug", "body": "..."}
)

# 方式2: 通过 MCPTool (集成到 Agent)
tool = manager.get_tool("github", "create_issue")
result = await tool.call(args, context)
```

## 传输类型

| 类型 | 说明 | 使用场景 |
|------|------|----------|
| `stdio` | 子进程通信 | 本地 MCP 服务器 |
| `http` | HTTP 请求 | 远程 MCP 服务 |
| `sse` | Server-Sent Events | 支持 SSE 的服务 |
| `websocket` | WebSocket | 实时双向通信 |

## 环境变量替换

配置文件中支持 `${VAR_NAME}` 语法:

```json
{
  "env": {
    "GITHUB_TOKEN": "${GITHUB_TOKEN}",
    "API_KEY": "${MCP_API_KEY}"
  }
}
```

## 故障排除

### 连接失败

1. 检查 MCP 服务器是否安装:
   ```bash
   npx -y @modelcontextprotocol/server-github --help
   ```

2. 检查环境变量是否设置:
   ```bash
   echo $GITHUB_TOKEN
   ```

3. 查看详细错误:
   ```python
   manager = MCPServerManager()
   try:
       await manager.connect_server("github")
   except Exception as e:
       print(f"Error: {e}")
   ```

### 工具调用失败

1. 检查工具参数是否正确
2. 检查认证是否有效
3. 查看服务器返回的错误信息

## 示例: 完整测试

```python
import asyncio
from scripts.mcp import initialize_mcp, MCPServerManager, shutdown_mcp

async def main():
    # 初始化
    print("Connecting to MCP servers...")
    manager = await initialize_mcp()
    
    # 列出已连接服务器
    servers = manager.get_connected_servers()
    print(f"Connected to {len(servers)} servers:")
    
    for name, info in servers.items():
        print(f"  - {name}: {info.status.value}")
        for tool in info.tools[:3]:  # 只显示前3个工具
            print(f"      {tool.name}")
        if len(info.tools) > 3:
            print(f"      ... and {len(info.tools) - 3} more")
    
    # 调用工具示例
    if "github" in manager.get_all_servers():
        try:
            result = await manager.call_tool("github", "list_repos", {})
            print(f"\\nRepos: {result}")
        except Exception as e:
            print(f"\\nTool call failed: {e}")
    
    # 关闭
    await shutdown_mcp()
    print("\\nMCP servers shut down.")

if __name__ == "__main__":
    asyncio.run(main())
```

## 查看可用 MCP 服务器

```bash
# 列出所有已配置的服务器
python -c "
import json
from pathlib import Path

config_paths = [
    Path('.mcp.json'),
    Path('.mcp/.mcp.json'),
    Path.home() / '.mcp.json',
]

for p in config_paths:
    if p.exists():
        print(f'Found: {p}')
        with open(p) as f:
            data = json.load(f)
            for name in data.get('mcpServers', {}):
                print(f'  - {name}')
"
```
