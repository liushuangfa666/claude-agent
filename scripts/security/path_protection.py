"""
路径保护 - Protected Paths
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

PROTECTED_PATHS: list[str] = [
    ".git",
    ".vscode",
    ".claude",
    ".env",
    "secrets/**",
    "**/.ssh/**",
    "**/node_modules/**",
    "**/__pycache__/**",
    "**/.pytest_cache/**",
    "**/.git/**",
    "**/.DS_Store",
    "**/thumbs.db",
    "**/.idea/**",
    "**/*.log",
    "**/.cache/**",
]


class ProtectedPathManager:
    """路径保护管理器"""

    def __init__(
        self,
        protected_patterns: list[str] | None = None,
        allow_override: bool = False,
    ):
        self._patterns: list[str] = protected_patterns or PROTECTED_PATHS.copy()
        self._override_patterns: set[str] = set()

        if allow_override:
            self._load_env_overrides()

    def _load_env_overrides(self) -> None:
        override = os.environ.get("CLAUDE_PROTECTED_PATHS_OVERRIDE", "")
        if override:
            for pattern in override.split(","):
                pattern = pattern.strip()
                if pattern:
                    self._override_patterns.add(pattern)

    def is_protected(self, path: str) -> bool:
        normalized = self._normalize_path(path)

        for pattern in self._override_patterns:
            if fnmatch.fnmatch(normalized, pattern):
                return False

        return self._matches_any_pattern(normalized)

    def _normalize_path(self, path: str) -> str:
        path = os.path.normpath(path)
        path = path.replace("\\", "/")
        return path

    def _matches_any_pattern(self, path: str) -> bool:
        for pattern in self._patterns:
            if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, f"*/{pattern}"):
                return True
            parts = path.split("/")
            for i, part in enumerate(parts):
                partial_path = "/".join(parts[: i + 1])
                if fnmatch.fnmatch(partial_path, pattern) or fnmatch.fnmatch(partial_path, f"*/{pattern}"):
                    return True
        return False

    def check_override(self, path: str, operation: str) -> bool:
        if operation in ("read", "Read"):
            return self._check_read_override(path)
        elif operation in ("write", "edit", "Write", "Edit"):
            return self._check_write_override(path)
        elif operation in ("delete", "remove", "rm", "Delete"):
            return self._check_delete_override(path)
        return self._check_write_override(path)

    def _check_read_override(self, path: str) -> bool:
        normalized = self._normalize_path(path)
        return normalized == ".git" or normalized.startswith(".git/")

    def _check_write_override(self, path: str) -> bool:
        override_env = os.environ.get("CLAUDE_ALLOW_PROTECTED_WRITES", "")
        if not override_env:
            return False
        normalized = self._normalize_path(path)
        for pattern in override_env.split(","):
            if fnmatch.fnmatch(normalized, pattern.strip()):
                return True
        return False

    def _check_delete_override(self, path: str) -> bool:
        return False

    def add_protected_pattern(self, pattern: str) -> None:
        if pattern not in self._patterns:
            self._patterns.append(pattern)

    def remove_protected_pattern(self, pattern: str) -> None:
        if pattern in self._patterns:
            self._patterns.remove(pattern)

    def get_protected_patterns(self) -> list[str]:
        return self._patterns.copy()

    def is_symlink(self, path: str) -> bool:
        try:
            return Path(path).is_symlink()
        except (OSError, RuntimeError):
            return False

    def resolve_symlink(self, path: str) -> str | None:
        try:
            return str(Path(path).resolve())
        except (OSError, RuntimeError):
            return None
