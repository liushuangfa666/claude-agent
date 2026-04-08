#!/usr/bin/env python3
"""
Claude Agent 启动入口

用法:
  python3 run.py                    # 交互模式
  python3 run.py "帮我看看当前目录"  # 单次对话
  python3 run.py --session my_session "你好"  # 指定会话
  python3 run.py --resume session_id  # 恢复会话
  python3 run.py --fork session_id   # Fork 会话
  python3 run.py --worktree feature   # 使用 worktree
"""
import argparse
import os
import sys

# 确保 scripts 在路径里
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

# 尝试从配置切换到 workspace（如果没有配置则保持当前目录）
try:
    from context import switch_to_workspace
    switch_to_workspace()
except ImportError:
    pass  # 忽略配置读取错误

import asyncio

try:
    from .agent import Agent, AgentConfig, create_agent
    from .lsp_tool import (
        LSPDefinitionTool,
        LSPHoverTool,
        LSPInitTool,
        LSPReferencesTool,
        LSPSymbolsTool,
        LSPTypeDefinitionTool,
    )
    from .permission import PermissionEngine
    from .session.manager import SessionManager
    from .tools import BashTool, EditTool, GlobTool, GrepTool, ReadTool, WriteTool

    # 高级工具
    from .tools_advanced import (
        AgentTool,
        TaskCreateTool,
        TaskGetTool,
        TaskListTool,
        TaskOutputTool,
        TaskStopTool,
        TaskUpdateTool,
        TodoWriteTool,
        WebFetchTool,
        WebSearchTool,
    )
except ImportError:
    from agent import Agent, AgentConfig, create_agent
    from lsp_tool import (
        LSPDefinitionTool,
        LSPHoverTool,
        LSPInitTool,
        LSPReferencesTool,
        LSPSymbolsTool,
        LSPTypeDefinitionTool,
    )
    from permission import PermissionEngine
    from session.manager import SessionManager
    from tools import BashTool, EditTool, GlobTool, GrepTool, ReadTool, WriteTool
    from tools_advanced import (
        AgentTool,
        TaskCreateTool,
        TaskGetTool,
        TaskListTool,
        TaskOutputTool,
        TaskStopTool,
        TaskUpdateTool,
        TodoWriteTool,
        WebFetchTool,
        WebSearchTool,
    )


def create_default_agent(
    session_manager: SessionManager | None = None,
    session_id: str | None = None,
    mcp_config_path: str | None = None,
    auth_callback=None,
) -> tuple[Agent, SessionManager, str | None]:
    """创建带默认工具的 Agent
    
    Returns:
        tuple: (agent, session_manager, session_id)
    """
    tools = [
        ReadTool(),
        BashTool(),
        WriteTool(),
        GrepTool(),
        GlobTool(),
        EditTool(),
        # LSP 工具
        LSPInitTool(),
        LSPDefinitionTool(),
        LSPHoverTool(),
        LSPTypeDefinitionTool(),
        LSPReferencesTool(),
        LSPSymbolsTool(),
        # 高级工具
        TaskCreateTool(),
        TaskGetTool(),
        TaskListTool(),
        TaskUpdateTool(),
        TaskOutputTool(),
        TaskStopTool(),
        WebFetchTool(),
        WebSearchTool(),
        AgentTool(),
        TodoWriteTool(),
    ]
    perm_engine = PermissionEngine.build_default_engine()
    config = AgentConfig(permission_engine=perm_engine, auth_callback=auth_callback)
    agent = create_agent(tools=tools, config=config)
    
    manager = session_manager or SessionManager()
    final_session_id = session_id
    
    return agent, manager, final_session_id


async def create_default_agent_async(
    session_manager: SessionManager | None = None,
    session_id: str | None = None,
    mcp_config_path: str | None = None,
    auth_callback=None,
    multi_agent_enabled: bool = False,
) -> tuple[Agent, SessionManager, str | None, list]:
    """创建带默认工具的 Agent（异步版本，支持 MCP 初始化）
    
    Returns:
        tuple: (agent, session_manager, session_id, mcp_registered_tools)
    """
    tools = [
        ReadTool(),
        BashTool(),
        WriteTool(),
        GrepTool(),
        GlobTool(),
        EditTool(),
        # LSP 工具
        LSPInitTool(),
        LSPDefinitionTool(),
        LSPHoverTool(),
        LSPTypeDefinitionTool(),
        LSPReferencesTool(),
        LSPSymbolsTool(),
        # 高级工具
        TaskCreateTool(),
        TaskGetTool(),
        TaskListTool(),
        TaskUpdateTool(),
        TaskOutputTool(),
        TaskStopTool(),
        WebFetchTool(),
        WebSearchTool(),
        AgentTool(),
        TodoWriteTool(),
    ]
    
    mcp_registered = []
    if mcp_config_path:
        try:
            from scripts.integration import register_mcp_tools, _initialize_mcp_manager
            manager = await _initialize_mcp_manager(mcp_config_path)
            if manager:
                mcp_registered = await register_mcp_tools(manager)
                if mcp_registered:
                    print(f"[MCP] Registered {len(mcp_registered)} tools from MCP servers")
        except Exception as e:
            print(f"[MCP] Warning: Could not initialize MCP: {e}")
    
    perm_engine = PermissionEngine.build_default_engine()
    config = AgentConfig(
        permission_engine=perm_engine,
        auth_callback=auth_callback,
        multi_agent_enabled=multi_agent_enabled,
    )
    agent = create_agent(tools=tools, config=config)
    
    manager = session_manager or SessionManager()
    final_session_id = session_id
    
    return agent, manager, final_session_id, mcp_registered


async def chat(agent: Agent, message: str, session_id: str | None = None) -> str:
    """执行单次对话"""
    final_text = ""
    tool_results = []
    async for event in agent.run_stream(message):
        if event.type == "text" and event.content:
            print(f"[AGENT] {event.content}")
        elif event.type == "tool_start":
            print(f"\n[TOOL] Executing {event.tool}...")
        elif event.type == "tool_result":
            tool_results.append(event)
            if event.success:
                data = event.data
                if isinstance(data, dict):
                    stdout = data.get("stdout", "")
                    if stdout:
                        print(f"[TOOL RESULT]\n{stdout}")
                    else:
                        print(f"[TOOL RESULT] {data}")
                else:
                    print(f"[TOOL RESULT] {data}")
            else:
                error = event.error or "unknown error"
                print(f"[TOOL ERROR] {error}")
        elif event.type == "done":
            final_text = event.content
    return final_text


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="Claude Agent")
    parser.add_argument("--session", type=str, help="会话名称或ID")
    parser.add_argument("--resume", type=str, metavar="SESSION_ID", help="恢复指定会话")
    parser.add_argument("--fork", type=str, metavar="SESSION_ID", help="Fork 指定会话创建新会话")
    parser.add_argument("--worktree", type=str, metavar="NAME", help="创建并使用 worktree")
    parser.add_argument("--mcp-config", type=str, metavar="PATH", help="MCP 配置文件路径")
    parser.add_argument("--multi-agent", action="store_true", help="启用 Multi-Agent 模式（基于复杂度自动选择 L1/L2/L3）")
    parser.add_argument("message", nargs="*", type=str, help="单次对话消息")
    return parser.parse_args()


def main():
    args = parse_args()
    
    # 创建授权确认回调
    def auth_callback(tool_name: str, args: dict) -> bool:
        args_str = ", ".join(f"{k}={repr(v)[:50]}" for k, v in args.items())
        print(f"\n[授权请求] {tool_name}({args_str})")
        try:
            response = input("是否允许执行? (y/n): ").strip().lower()
            return response in ["y", "yes", "是", "允许"]
        except EOFError:
            return False

    session_manager = SessionManager()
    session_id = None
    session_info = None
    
    if args.resume:
        session_id = args.resume
        session_info = session_manager.resume_session(session_id)
        if session_info:
            print(f"[SESSION] Resuming session: {session_info.name} ({session_id})")
        else:
            print(f"[ERROR] Session {session_id} not found")
            return
    
    elif args.fork:
        parent_id = args.fork
        new_name = f"fork-{parent_id}"
        if args.session:
            new_name = args.session
        session_info = session_manager.fork_session(parent_id, new_name)
        if session_info:
            session_id = session_info.id
            print(f"[SESSION] Forked session: {session_info.name} ({session_id}) from {parent_id}")
        else:
            print(f"[ERROR] Parent session {parent_id} not found")
            return
    
    elif args.worktree:
        worktree_name = args.worktree
        session_info = session_manager.create_worktree_session(worktree_name)
        if session_info:
            session_id = session_info.id
            print(f"[SESSION] Created worktree session: {session_info.name} ({session_id})")
            print(f"[SESSION] Worktree path: {session_info.worktree_path}")
        else:
            print(f"[ERROR] Failed to create worktree: {worktree_name}")
            return
    
    elif args.session:
        session_name = args.session
        sessions = session_manager.list_sessions()
        for s in sessions:
            if s.name == session_name or s.id == session_name:
                session_id = s.id
                session_info = s
                break
        if not session_info:
            session_info = session_manager.create_session(session_name)
            session_id = session_info.id
            print(f"[SESSION] Created new session: {session_info.name} ({session_id})")
        else:
            print(f"[SESSION] Using existing session: {session_info.name} ({session_id})")
    
    if args.message:
        message = " ".join(args.message)
        print(f"[USER] {message}\n")
        agent, manager, sid, _ = asyncio.run(
            create_default_agent_async(session_manager, session_id, args.mcp_config, auth_callback, args.multi_agent)
        )
        result = asyncio.run(chat(agent, message, sid))
        print(f"[AGENT] {result}")
    else:
        print("[AGENT] Claude Agent started (type quit to exit)")
        print("=" * 50)
        agent, manager, sid, _ = asyncio.run(
            create_default_agent_async(session_manager, session_id, args.mcp_config, auth_callback, args.multi_agent)
        )
        while True:
            try:
                user_input = input("\n[USER] ")
                if user_input.lower() in ["quit", "exit", "q"]:
                    print("Bye!")
                    break
                if not user_input.strip():
                    continue
                result = asyncio.run(chat(agent, user_input, sid))
                print(f"\n[AGENT] {result}")
            except KeyboardInterrupt:
                print("\n[CTRL+C] Bye!")
                break
            except Exception as e:
                print(f"[ERROR] {e}")


if __name__ == "__main__":
    main()
