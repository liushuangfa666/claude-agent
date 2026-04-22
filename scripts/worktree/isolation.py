"""Isolated agent execution within a worktree."""
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent import AgentConfig


class IsolatedAgent:
    """
    Agent wrapper that operates within an isolated worktree directory.
    
    This provides task isolation by running the agent in a separate
    Git worktree, preventing interference with the main working tree.
    
    Example:
        manager = WorktreeManager()
        manager.create("feature-x")
        
        config = AgentConfig()
        agent = IsolatedAgent(config, worktree_path=manager.get_path("feature-x"))
        
        async for event in agent.run("Fix the login bug"):
            print(event)
    """

    def __init__(self, config: "AgentConfig", worktree_path: Path):
        """
        Initialize isolated agent.
        
        Args:
            config: Agent configuration
            worktree_path: Path to the worktree directory
        """
        self.worktree_path = worktree_path
        self.config = config

        if not worktree_path.exists():
            raise ValueError(f"Worktree does not exist: {worktree_path}")

    async def run(self, prompt: str):
        """
        Run the agent in the isolated worktree.
        
        Args:
            prompt: Task prompt
            
        Yields:
            Event objects from the agent execution
        """
        from agent import Agent

        agent = Agent(self.config)
        agent.cwd = self.worktree_path

        async for event in agent.run_stream(prompt):
            yield event

    def get_working_dir(self) -> Path:
        """
        Get the working directory for this isolated agent.
        
        Returns:
            The worktree path
        """
        return self.worktree_path
