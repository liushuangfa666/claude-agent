"""Worktree module for Git worktree-based task isolation.

This module provides:
- manager: WorktreeManager for creating/removing/list Git worktrees
- isolation: IsolatedAgent for running tasks in isolated worktrees

Usage:
    manager = WorktreeManager()
    manager.create("feature-xyz", branch="feature/xyz")
    
    # Run task in isolation
    agent = IsolatedAgent(config, manager.get_path("feature-xyz"))
    async for event in agent.run("Implement feature"):
        print(event)
"""

from .isolation import IsolatedAgent
from .manager import WORKTREE_BASE, WorktreeInfo, WorktreeManager

__all__ = [
    "WorktreeManager",
    "WorktreeInfo",
    "WORKTREE_BASE",
    "IsolatedAgent",
]
