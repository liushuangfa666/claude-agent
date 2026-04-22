"""
CLI Main Entry - Command line interface for Claude Agent

Supports subcommands:
- chat: Chat with agent (supports streaming)
- agents: List local/project agents
- session: Session management (list/show/delete)
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from .print import print_error, print_info, print_success, print_warning


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        description="Claude Agent CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Chat subcommand
    chat_parser = subparsers.add_parser("chat", help="Chat with agent")
    chat_parser.add_argument("message", nargs="*", help="Message to send")
    chat_parser.add_argument("--session", help="Session ID")
    chat_parser.add_argument("--stream", action="store_true", help="Stream response")

    # Agents subcommand
    agents_parser = subparsers.add_parser("agents", help="List agents")
    agents_parser.add_argument(
        "--local", action="store_true", help="Show local agents"
    )
    agents_parser.add_argument(
        "--project", action="store_true", help="Show project agents"
    )

    # Session subcommand
    session_parser = subparsers.add_parser("session", help="Session management")
    session_parser.add_argument("action", choices=["list", "show", "delete"])
    session_parser.add_argument("--id", help="Session ID")

    return parser


async def run_chat(args: argparse.Namespace) -> int:
    """Run chat with agent."""
    try:
        from ..session.manager import SessionManager
    except ImportError as e:
        print_error(f"Failed to import session modules: {e}")
        return 1

    message = " ".join(args.message) if args.message else ""
    if not message:
        print_warning("No message provided")
        return 1

    manager = SessionManager()
    session = manager.get_or_create(args.session or "")

    if args.stream:
        print_info("Streaming response...")
        async for event in session.stream_message(message):
            if event.get("type") == "text" and event.get("content"):
                print(event["content"], end="", flush=True)
            elif event.get("type") == "done":
                print()
    else:
        response = await session.process_message(message)
        print(response)

    return 0


async def run_agents(args: argparse.Namespace) -> int:
    """List agents (local/project)."""
    try:
        from .handlers.agents import handle_agents_list, display_agents_table
    except ImportError as e:
        print_error(f"Failed to import agents handler: {e}")
        return 1

    agents = handle_agents_list(
        local_only=args.local, project_only=args.project
    )

    print_info(f"{len(agents)} active agents\n")
    display_agents_table(agents)

    return 0


async def run_session(args: argparse.Namespace) -> int:
    """Session management (list/show/delete)."""
    try:
        from ..session.manager import SessionManager
    except ImportError as e:
        print_error(f"Failed to import session modules: {e}")
        return 1

    manager = SessionManager()

    if args.action == "list":
        sessions = manager.list()
        print_info(f"{len(sessions)} sessions\n")
        for session in sessions:
            print(f"  {session['id']}")
        return 0

    elif args.action == "show":
        if not args.id:
            print_error("Session ID required for 'show' action")
            return 1

        session = manager.get(args.id)
        if session:
            print_success(f"Session: {session.id}")
            print(f"  Created: {session.created_at}")
            print(f"  Messages: {len(session.messages)}")
        else:
            print_error(f"Session {args.id} not found")
            return 1

    elif args.action == "delete":
        if not args.id:
            print_error("Session ID required for 'delete' action")
            return 1

        if manager.delete(args.id):
            print_success(f"Deleted session {args.id}")
        else:
            print_error(f"Session {args.id} not found")
            return 1

    return 0


async def main_async() -> int:
    """Async main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "chat":
        return await run_chat(args)
    elif args.command == "agents":
        return await run_agents(args)
    elif args.command == "session":
        return await run_session(args)

    return 0


def main() -> int:
    """Main entry point."""
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
