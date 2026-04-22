"""
Team/Coordinator 协作系统
"""
from .constants import (
    AGENT_COLORS,
    AGENT_TYPE_COORDINATOR,
    AGENT_TYPE_WORKER,
    MESSAGE_TYPES,
    STATUS_COMPLETED,
    STATUS_RUNNING,
    STATUS_STOPPED,
    TEAM_LEAD_NAME,
    TEAM_MEM_DIR,
)
from .mailbox import TeamMailbox, get_mailbox
from .team import Message, Team, Teammate, TeamStorage
from .worker import ASYNC_AGENT_ALLOWED_TOOLS, WorkerAgent

__all__ = [
    "TEAM_LEAD_NAME",
    "TEAM_MEM_DIR",
    "AGENT_COLORS",
    "MESSAGE_TYPES",
    "STATUS_RUNNING",
    "STATUS_STOPPED",
    "STATUS_COMPLETED",
    "AGENT_TYPE_WORKER",
    "AGENT_TYPE_COORDINATOR",
    "Team",
    "Teammate",
    "Message",
    "TeamStorage",
    "TeamMailbox",
    "get_mailbox",
    "WorkerAgent",
    "ASYNC_AGENT_ALLOWED_TOOLS",
]
