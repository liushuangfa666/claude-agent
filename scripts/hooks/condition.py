"""
Hook 条件匹配器
"""
from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass


@dataclass
class MatchResult:
    matched: bool
    reason: str = ""


class HookCondition:
    """Hook 条件匹配器"""

    TOOL_PATTERN = re.compile(r"^(\w+)\((.*)\)$")
    ENV_PATTERN = re.compile(r"^env:([A-Za-z_][A-Za-z0-9_]*)(?:=(.*))?$")
    PATH_PATTERN = re.compile(r"^path:(.+)$")
    OR_PATTERN = re.compile(r"^OR\((.+)\)$", re.IGNORECASE)
    AND_PATTERN = re.compile(r"^AND\((.+)\)$", re.IGNORECASE)

    def matches(self, context: dict, pattern: str) -> bool:
        pattern = pattern.strip()

        if not pattern:
            return True

        or_match = self.OR_PATTERN.match(pattern)
        if or_match:
            return self._match_or(context, or_match.group(1))

        and_match = self.AND_PATTERN.match(pattern)
        if and_match:
            return self._match_and(context, and_match.group(1))

        if "," in pattern and not pattern.startswith("("):
            conditions = [c.strip() for c in pattern.split(",")]
            return all(self.matches(context, c) for c in conditions)

        env_match = self.ENV_PATTERN.match(pattern)
        if env_match:
            return self._match_env(env_match.group(1), env_match.group(2), context)

        path_match = self.PATH_PATTERN.match(pattern)
        if path_match:
            return self._match_path(path_match.group(1), context)

        tool_match = self.TOOL_PATTERN.match(pattern)
        if tool_match:
            tool_name = tool_match.group(1)
            args_pattern = tool_match.group(2)
            return self._match_tool(tool_name, args_pattern, context)

        if ":" in pattern:
            key, value = pattern.split(":", 1)
            if key == "tool_name":
                return context.get("tool_name") == value
            return context.get(key) == value

        return context.get("tool_name") == pattern

    def _match_or(self, context: dict, conditions_str: str) -> bool:
        conditions = self._parse_conditions(conditions_str)
        return any(self.matches(context, c) for c in conditions)

    def _match_and(self, context: dict, conditions_str: str) -> bool:
        conditions = self._parse_conditions(conditions_str)
        return all(self.matches(context, c) for c in conditions)

    def _parse_conditions(self, conditions_str: str) -> list[str]:
        conditions = []
        current = ""
        depth = 0

        for char in conditions_str:
            if char == "(":
                depth += 1
                current += char
            elif char == ")":
                depth -= 1
                current += char
            elif char == "," and depth == 0:
                if current.strip():
                    conditions.append(current.strip())
                current = ""
            else:
                current += char

        if current.strip():
            conditions.append(current.strip())

        return conditions

    def _match_env(self, var_name: str, expected_value: str | None, context: dict) -> bool:
        actual_value = os.environ.get(var_name)
        if expected_value is None:
            return actual_value is not None
        return actual_value == expected_value

    def _match_path(self, pattern: str, context: dict) -> bool:
        path = context.get("path") or context.get("file_path") or context.get("tool_args", {}).get("file_path", "")
        if not path:
            return False
        if "**" in pattern:
            return self._match_recursive_path(path, pattern)
        return bool(fnmatch.fnmatch(path, pattern))

    def _match_recursive_path(self, path: str, pattern: str) -> bool:
        parts = pattern.split("**")
        if len(parts) == 2:
            prefix = parts[0].rstrip("/")
            suffix = parts[1].lstrip("/*")
            if prefix and not path.startswith(prefix):
                return False
            if suffix:
                return path.endswith(suffix) or suffix in path
            return True
        return fnmatch.fnmatch(path, pattern)

    def _match_tool(self, tool_name: str, args_pattern: str, context: dict) -> bool:
        if context.get("tool_name") != tool_name:
            return False
        if not args_pattern or args_pattern == "*":
            return True
        tool_args = context.get("tool_args", {})
        args_str = str(tool_args)
        if "*" in args_pattern:
            return bool(fnmatch.fnmatch(args_str, f"*{args_pattern}*"))
        return args_pattern in args_str
