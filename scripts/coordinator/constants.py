"""
Team/Coordinator 常量定义
"""
from __future__ import annotations

import os

TEAM_LEAD_NAME = "team-lead"
TEAM_MEM_DIR = os.path.join(os.path.expanduser("~"), ".claude-agent", "teams")
os.makedirs(TEAM_MEM_DIR, exist_ok=True)

STATUS_RUNNING = "running"
STATUS_STOPPED = "stopped"
STATUS_COMPLETED = "completed"

AGENT_TYPE_WORKER = "worker"
AGENT_TYPE_COORDINATOR = "coordinator"

MESSAGE_TYPES = {
    "TEXT": "text",
    "SHUTDOWN_REQUEST": "shutdown_request",
    "PLAN_APPROVAL": "plan_approval",
    "TASK_ASSIGNMENT": "task_assignment",
    "TASK_COMPLETION": "task_completion",
    "BROADCAST": "broadcast",
}

AGENT_COLORS = [
    "\033[94m",  # Blue
    "\033[92m",  # Green
    "\033[93m",  # Yellow
    "\033[96m",  # Cyan
    "\033[95m",  # Magenta
    "\033[91m",  # Red
    "\033[90m",  # Gray
]

ASYNC_AGENT_ALLOWED_TOOLS = {
    "Bash",
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "TaskCreate",
    "TaskList",
    "TaskUpdate",
    "TaskStop",
    "Agent",
    "SendMessage",
    "WebFetch",
    "WebSearch",
}
