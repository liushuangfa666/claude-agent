#!/usr/bin/env python3
"""
Claude Agent 命令行入口

用法:
  python3 cmd.py start          # 启动 agent 服务（后台运行）
  python3 cmd.py stop           # 停止 agent
  python3 cmd.py status         # 查看状态
  python3 cmd.py chat "你好"   # 单次对话
  python3 cmd.py interactive    # 交互模式
  python3 cmd.py --session my_session interactive  # 指定会话交互
  python3 cmd.py --resume session_id  # 恢复会话
  python3 cmd.py --fork session_id    # Fork 会话
  python3 cmd.py --worktree name      # 使用 worktree
"""
import argparse
import os
import sys

# 添加 scripts 路径
_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_dir)

# 自动切换到配置的 workspace
from context import switch_to_workspace
switch_to_workspace()

try:
    from .agent import create_agent
    from .lsp_tool import (
        LSPDefinitionTool,
        LSPHoverTool,
        LSPInitTool,
        LSPReferencesTool,
        LSPSymbolsTool,
        LSPTypeDefinitionTool,
    )
    from .session.manager import SessionManager
    from .tools import BashTool, GlobTool, GrepTool, ReadTool, WriteTool
except ImportError:
    from agent import create_agent
    from lsp_tool import (
        LSPDefinitionTool,
        LSPHoverTool,
        LSPInitTool,
        LSPReferencesTool,
        LSPSymbolsTool,
        LSPTypeDefinitionTool,
    )
    from session.manager import SessionManager
    from tools import BashTool, GlobTool, GrepTool, ReadTool, WriteTool


def cmd_start(args):
    """启动 agent"""
    session_manager = SessionManager()
    session_id = None
    session_info = None

    if getattr(args, 'resume', None):
        session_id = args.resume
        session_info = session_manager.resume_session(session_id)
        if session_info:
            print(f"🚀 Resuming session: {session_info.name} ({session_id})")
        else:
            print(f"❌ Session {session_id} not found")
            return

    elif getattr(args, 'fork', None):
        parent_id = args.fork
        new_name = f"fork-{parent_id}"
        if getattr(args, 'session', None):
            new_name = args.session
        session_info = session_manager.fork_session(parent_id, new_name)
        if session_info:
            session_id = session_info.id
            print(f"🚀 Forked session: {session_info.name} ({session_id}) from {parent_id}")
        else:
            print(f"❌ Parent session {parent_id} not found")
            return

    elif getattr(args, 'worktree', None):
        worktree_name = args.worktree
        session_info = session_manager.create_worktree_session(worktree_name)
        if session_info:
            session_id = session_info.id
            print(f"🚀 Created worktree session: {session_info.name}")
            print(f"   Worktree path: {session_info.worktree_path}")
        else:
            print(f"❌ Failed to create worktree: {worktree_name}")
            return

    print("🚀 启动 Claude Agent...")
    # 注册内置工具
    tools = [
        ReadTool(),
        BashTool(),
        WriteTool(),
        GrepTool(),
        GlobTool(),
        # LSP 工具
        LSPInitTool(),
        LSPDefinitionTool(),
        LSPHoverTool(),
        LSPTypeDefinitionTool(),
        LSPReferencesTool(),
        LSPSymbolsTool(),
    ]
    agent = create_agent(tools=tools)
    print("✅ Agent 已启动")
    print(f"   工具数: {len(tools)}")
    print(f"   模型: {agent.config.model}")
    print(f"   API: {agent.config.api_url}")
    if session_id:
        print(f"   会话: {session_id}")


def cmd_chat(args):
    """单次对话"""
    from agent import create_agent
    from tool import BashTool, ReadTool, WriteTool

    session_manager = SessionManager()
    session_id = None

    if getattr(args, 'resume', None):
        session_id = args.resume
        session_info = session_manager.resume_session(session_id)
        if session_info:
            print(f"[SESSION] Resuming: {session_info.name} ({session_id})")
        else:
            print(f"[ERROR] Session {session_id} not found")
            return

    tools = [ReadTool(), BashTool(), WriteTool()]
    agent = create_agent(tools=tools)

    print(f"🤖 {args.message}")
    import asyncio
    result = asyncio.run(agent.run(args.message))
    print(result)


def cmd_status(args):
    """查看状态"""
    session_manager = SessionManager()
    sessions = session_manager.list_sessions()

    print("Claude Agent 状态:")
    print("  状态: 就绪")
    print("  工具: Read, Bash, Write, Grep, Glob")
    print(f"  会话数: {len(sessions)}")
    if sessions:
        print("  最近会话:")
        for s in sessions[:5]:
            print(f"    - {s.name} ({s.id})")


def cmd_list(args):
    """列出所有会话"""
    session_manager = SessionManager()
    sessions = session_manager.list_sessions()

    if not sessions:
        print("No sessions found")
        return

    print(f"Sessions ({len(sessions)}):")
    for s in sessions:
        print(f"  {s.name} ({s.id})")
        print(f"    Root: {s.root}")
        print(f"    Created: {s.created_at}")
        if s.worktree_path:
            print(f"    Worktree: {s.worktree_path}")
        if s.parent_session_id:
            print(f"    Parent: {s.parent_session_id}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Claude Agent")
    parser.add_argument("--session", type=str, help="会话名称或ID")
    parser.add_argument("--resume", type=str, metavar="SESSION_ID", help="恢复指定会话")
    parser.add_argument("--fork", type=str, metavar="SESSION_ID", help="Fork 指定会话")
    parser.add_argument("--worktree", type=str, metavar="NAME", help="使用 worktree")

    sub = parser.add_subparsers()

    sub.add_command("start", cmd_start)
    sub.add_command("status", cmd_status)
    sub.add_command("chat", cmd_chat)
    sub.add_command("list", cmd_list)
    sub.add_command("interactive", cmd_start)

    args = parser.parse_intermixed_args()
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
