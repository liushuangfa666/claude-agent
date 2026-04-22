"""Worktree management for Git worktree isolation."""
import builtins
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

WORKTREE_BASE = Path.home() / ".claude-agent" / "worktrees"


@dataclass
class WorktreeInfo:
    """Information about a Git worktree."""
    path: Path
    branch: str
    is_main: bool = False


class WorktreeManager:
    """
    Manager for Git worktree operations.
    
    Provides methods to create, list, and remove Git worktrees
    for isolated task execution.
    """

    def __init__(self, base_path: Path | None = None):
        """
        Initialize the worktree manager.
        
        Args:
            base_path: Base directory for worktrees. Defaults to ~/.claude-agent/worktrees
        """
        self.base_path = base_path or WORKTREE_BASE
        self.base_path.mkdir(parents=True, exist_ok=True)

    def create(self, name: str, branch: str | None = None) -> Path:
        """
        Create a new Git worktree.
        
        Args:
            name: Name of the worktree (used for directory and branch name)
            branch: Branch name. If None, uses 'worktree-{name}'
            
        Returns:
            Path to the created worktree
            
        Raises:
            ValueError: If worktree already exists
            RuntimeError: If git worktree command fails
        """
        worktree_path = self.base_path / name

        if worktree_path.exists():
            raise ValueError(f"Worktree '{name}' already exists at {worktree_path}")

        branch = branch or f"worktree-{name}"

        try:
            result = subprocess.run(
                ["git", "worktree", "add", "-b", branch, str(worktree_path)],
                capture_output=True,
                text=True,
                check=True
            )
            return worktree_path
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create worktree: {e.stderr}")
        except FileNotFoundError:
            raise RuntimeError("Git is not installed or not in PATH")

    def list(self) -> list[WorktreeInfo]:
        """
        List all Git worktrees.
        
        Returns:
            List of WorktreeInfo objects
        """
        try:
            result = subprocess.run(
                ["git", "worktree", "list", "--porcelain"],
                capture_output=True,
                text=True,
                check=True
            )

            worktrees: list[WorktreeInfo] = []
            current: WorktreeInfo | None = None

            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue

                if line.startswith("worktree "):
                    path_str = line[9:]
                    current = WorktreeInfo(
                        path=Path(path_str),
                        branch="",
                        is_main="main" in path_str or path_str == os.getcwd()
                    )
                elif line.startswith("branch "):
                    if current:
                        current.branch = line[7:]
                elif line.startswith("HEAD "):
                    if current:
                        pass

                if current and current.path and current.branch:
                    worktrees.append(current)
                    current = None

            return worktrees

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to list worktrees: {e.stderr}")
        except FileNotFoundError:
            raise RuntimeError("Git is not installed or not in PATH")

    def remove(self, name: str) -> None:
        """
        Remove a Git worktree.
        
        Args:
            name: Name of the worktree to remove
            
        Raises:
            ValueError: If worktree doesn't exist
            RuntimeError: If git worktree remove command fails
        """
        worktree_path = self.base_path / name

        if not worktree_path.exists():
            raise ValueError(f"Worktree '{name}' does not exist at {worktree_path}")

        try:
            subprocess.run(
                ["git", "worktree", "remove", str(worktree_path), "--force"],
                capture_output=True,
                text=True,
                check=True
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to remove worktree: {e.stderr}")
        except FileNotFoundError:
            raise RuntimeError("Git is not installed or not in PATH")

    def get_path(self, name: str) -> Path:
        """
        Get the path for a worktree by name.
        
        Args:
            name: Name of the worktree
            
        Returns:
            Path to the worktree directory
        """
        return self.base_path / name

    def exists(self, name: str) -> bool:
        """
        Check if a worktree exists.
        
        Args:
            name: Name of the worktree
            
        Returns:
            True if worktree exists
        """
        return (self.base_path / name).exists()

    def cleanup_stale(self) -> builtins.list[str]:
        """
        Remove stale worktree directories that no longer exist in git.
        
        Returns:
            List of removed worktree names
        """
        removed = []
        git_worktrees = {wt.path for wt in self.list()}

        for wt_dir in self.base_path.iterdir():
            if wt_dir.is_dir() and wt_dir not in git_worktrees:
                try:
                    import shutil
                    shutil.rmtree(wt_dir)
                    removed.append(wt_dir.name)
                except Exception:
                    pass

        return removed
