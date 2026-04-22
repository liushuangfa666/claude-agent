"""
Agents Handler - Handle agents subcommand
"""
from __future__ import annotations

from typing import Any

from ..print import format_table, print_info


def handle_agents_list(
    local_only: bool = False,
    project_only: bool = False,
) -> list[dict[str, Any]]:
    """
    Handle agents list command.

    Args:
        local_only: Only show local agents
        project_only: Only show project agents

    Returns:
        List of agent info dictionaries
    """
    # Placeholder - 实际从 agent registry 获取
    agents = []

    try:
        from ...subagent.registry import SubagentRegistry

        registry = SubagentRegistry.get_instance()
        agents_data = registry.list_subagents()

        for agent_info in agents_data:
            scope = getattr(agent_info, "scope", "local")
            if local_only and scope != "local":
                continue
            if project_only and scope != "project":
                continue

            agents.append({
                "id": getattr(agent_info, "agent_id", "unknown"),
                "name": getattr(agent_info, "name", "unknown"),
                "type": getattr(agent_info, "subagent_type", "unknown"),
                "status": getattr(agent_info, "status", "unknown"),
                "scope": scope,
            })
    except ImportError:
        print_info("No agents available (registry not available)")

    return agents


def display_agents_table(agents: list[dict[str, Any]]) -> None:
    """Display agents in table format."""
    if not agents:
        print_info("No agents found")
        return

    headers = ["Name", "Type", "Status", "Scope"]
    rows = [
        [a["name"], a["type"], a["status"], a["scope"]]
        for a in agents
    ]

    table = format_table(headers, rows)
    print(table)
