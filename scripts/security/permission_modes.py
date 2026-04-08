"""
权限模式 - Permission Modes
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any


class PermissionMode(Enum):
    DEFAULT = "default"
    PLAN = "plan"
    ACCEPTED = "acceptedEdits"
    BYPASS = "bypassPermissions"
    DONT_ASK = "dontAsk"
    AUTO = "auto"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> PermissionMode:
        value = value.lower().replace("-", "").replace("_", "")
        for mode in cls:
            mode_value = mode.value.lower().replace("-", "").replace("_", "")
            if mode_value == value:
                return mode
        return cls.DEFAULT


@dataclass
class ModeConfig:
    name: PermissionMode
    ask_before_approval: bool = True
    allow_known_edits: bool = False
    skip_validation: bool = False
    auto_classify: bool = False
    auto_decide: bool = False
    read_only: bool = False
    silent: bool = False
    bypass_protected_paths: bool = False
    bypass_sandbox: bool = False
    allowed_tools: set[str] | None = None
    denied_tools: set[str] | None = None


DEFAULT_MODE_CONFIGS: dict[PermissionMode, ModeConfig] = {
    PermissionMode.DEFAULT: ModeConfig(
        name=PermissionMode.DEFAULT,
        ask_before_approval=True,
    ),
    PermissionMode.PLAN: ModeConfig(
        name=PermissionMode.PLAN,
        ask_before_approval=True,
        read_only=True,
        allowed_tools={"Read", "Glob", "Grep", "WebFetch", "WebSearch", "Agent", "TaskCreate", "TaskList"},
    ),
    PermissionMode.ACCEPTED: ModeConfig(
        name=PermissionMode.ACCEPTED,
        ask_before_approval=True,
        allow_known_edits=True,
    ),
    PermissionMode.BYPASS: ModeConfig(
        name=PermissionMode.BYPASS,
        ask_before_approval=False,
        skip_validation=True,
        bypass_protected_paths=True,
        bypass_sandbox=True,
    ),
    PermissionMode.DONT_ASK: ModeConfig(
        name=PermissionMode.DONT_ASK,
        ask_before_approval=False,
        skip_validation=True,
        silent=True,
    ),
    PermissionMode.AUTO: ModeConfig(
        name=PermissionMode.AUTO,
        ask_before_approval=False,
        auto_classify=True,
        auto_decide=True,
    ),
}


class PermissionModeManager:
    def __init__(self):
        self._modes: dict[str, ModeConfig] = {}
        self._current_mode: PermissionMode = PermissionMode.DEFAULT
        self._accepted_tools: set[str] = set()
        self._accepted_paths: set[str] = set()

        for mode, config in DEFAULT_MODE_CONFIGS.items():
            self._modes[mode.value] = config

        self._load_from_env()

    def _load_from_env(self) -> None:
        env_mode = os.environ.get("CLAUDE_PERMISSION_MODE", "")
        if env_mode:
            try:
                self._current_mode = PermissionMode.from_string(env_mode)
            except ValueError:
                pass

        if os.environ.get("CLAUDE_BYPASS_PERMISSIONS", "") in ("1", "true", "yes"):
            self._current_mode = PermissionMode.BYPASS

        if os.environ.get("CLAUDE_DONT_ASK", "") in ("1", "true", "yes"):
            self._current_mode = PermissionMode.DONT_ASK

        if os.environ.get("CLAUDE_AUTO_APPROVE", "") in ("1", "true", "yes"):
            self._current_mode = PermissionMode.AUTO

    @property
    def current_mode(self) -> PermissionMode:
        return self._current_mode

    @property
    def current_config(self) -> ModeConfig:
        return self._modes.get(
            self._current_mode.value,
            DEFAULT_MODE_CONFIGS[PermissionMode.DEFAULT],
        )

    def set_mode(self, mode: PermissionMode) -> None:
        self._current_mode = mode

    def should_ask(self, tool_name: str, operation: dict[str, Any]) -> bool:
        config = self.current_config

        if not config.ask_before_approval:
            return False

        if config.allowed_tools and tool_name not in config.allowed_tools:
            return True

        if config.denied_tools and tool_name in config.denied_tools:
            return True

        if config.read_only:
            write_tools = {"Write", "Edit", "Bash", "Delete", "Move"}
            if tool_name in write_tools:
                return True

        return True

    def should_allow(self, tool_name: str, operation: dict[str, Any]) -> bool:
        config = self.current_config

        if config.skip_validation:
            return True

        if config.silent:
            return True

        return False

    def accept_tool(self, tool_name: str) -> None:
        self._accepted_tools.add(tool_name)

    def accept_path(self, path: str) -> None:
        self._accepted_paths.add(path)

    def is_accepted(self, tool_name: str, path: str | None = None) -> bool:
        if tool_name in self._accepted_tools:
            return True
        if path and path in self._accepted_paths:
            return True
        return False

    def reset_accepted(self) -> None:
        self._accepted_tools.clear()
        self._accepted_paths.clear()
