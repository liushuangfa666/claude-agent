"""
路径验证 - Path Validation
"""
from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ValidationStatus(Enum):
    VALID = "valid"
    INVALID = "invalid"
    SYMLINK = "symlink"
    OUTSIDE_CWD = "outside_cwd"
    TOO_LONG = "too_long"
    DANGEROUS = "dangerous"


@dataclass
class PathValidationResult:
    status: ValidationStatus
    message: str
    normalized_path: str | None = None
    real_path: str | None = None
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.status == ValidationStatus.VALID


class PathValidator:
    MAX_PATH_LENGTH = 4096
    MAX_COMPONENT_LENGTH = 255
    SUSPICIOUS_COMPONENTS = {
        "..", ".git", ".svn", ".hg", "__pycache__",
        "node_modules", ".DS_Store", "thumbs.db",
    }

    def __init__(
        self,
        cwd: str | None = None,
        max_path_length: int | None = None,
        allow_symlinks: bool = False,
        restrict_parent_access: bool = True,
    ):
        self.cwd = os.path.abspath(cwd) if cwd else os.getcwd()
        self.max_path_length = max_path_length or self.MAX_PATH_LENGTH
        self.allow_symlinks = allow_symlinks
        self.restrict_parent_access = restrict_parent_access

    def validate(self, path: str, operation: str = "access") -> PathValidationResult:
        warnings: list[str] = []

        if len(path) > self.max_path_length:
            return PathValidationResult(
                status=ValidationStatus.TOO_LONG,
                message=f"Path exceeds maximum length of {self.max_path_length}",
                normalized_path=path,
            )

        normalized = self._normalize_path(path)

        component_length_check = self._check_component_length(normalized)
        if component_length_check:
            warnings.append(component_length_check)

        suspicious_check = self._check_suspicious_components(normalized)
        if suspicious_check:
            warnings.append(suspicious_check)

        if self._is_symlink(normalized):
            if not self.allow_symlinks:
                return PathValidationResult(
                    status=ValidationStatus.SYMLINK,
                    message="Symbolic links are not allowed",
                    normalized_path=normalized,
                    real_path=self._resolve_symlink(normalized),
                    warnings=warnings,
                )
            else:
                warnings.append("Path is a symbolic link")

        if self.restrict_parent_access:
            parent_check = self._check_parent_access(normalized, operation)
            if parent_check:
                return parent_check

        traversal_check = self._check_directory_traversal(path)
        if traversal_check:
            return PathValidationResult(
                status=ValidationStatus.DANGEROUS,
                message="Directory traversal attempt detected",
                normalized_path=normalized,
                warnings=warnings,
            )

        outside_cwd = self._is_outside_cwd(normalized)
        if outside_cwd:
            warnings.append("Path is outside current working directory")

        dangerous_check = self._check_dangerous_paths(normalized)
        if dangerous_check:
            warnings.append(dangerous_check)

        return PathValidationResult(
            status=ValidationStatus.VALID,
            message="Path validation passed",
            normalized_path=normalized,
            real_path=self._resolve_path(normalized),
            warnings=warnings,
        )

    def _normalize_path(self, path: str) -> str:
        if path.startswith("~/"):
            path = os.path.expanduser(path)
        if not os.path.isabs(path):
            path = os.path.join(self.cwd, path)
        path = os.path.normpath(path)
        path = path.replace("\\", "/")
        return path

    def _check_component_length(self, path: str) -> str | None:
        for component in path.split("/"):
            if len(component) > self.MAX_COMPONENT_LENGTH:
                return f"Path component '{component}' exceeds {self.MAX_COMPONENT_LENGTH} chars"
        return None

    def _check_suspicious_components(self, path: str) -> str | None:
        components = set(path.split("/"))
        suspicious = components & self.SUSPICIOUS_COMPONENTS
        if suspicious:
            return f"Path contains suspicious components: {', '.join(suspicious)}"
        return None

    def _is_symlink(self, path: str) -> bool:
        try:
            return Path(path).is_symlink()
        except (OSError, RuntimeError):
            return False

    def _resolve_symlink(self, path: str) -> str | None:
        try:
            return str(Path(path).resolve())
        except (OSError, RuntimeError):
            return None

    def _resolve_path(self, path: str) -> str:
        try:
            return str(Path(path).resolve())
        except (OSError, RuntimeError):
            return path

    def _check_parent_access(self, path: str, operation: str) -> PathValidationResult | None:
        if operation in ("write", "delete"):
            parent = os.path.dirname(path)
            if parent != self.cwd and not parent.startswith(self.cwd + "/"):
                sensitive_parents = ["/etc", "/usr", "/bin", "/sbin", "/boot"]
                for sp in sensitive_parents:
                    if parent == sp or parent.startswith(sp + "/"):
                        return PathValidationResult(
                            status=ValidationStatus.DANGEROUS,
                            message=f"Attempting to write to protected parent directory: {parent}",
                            normalized_path=path,
                            warnings=[f"Parent directory '{parent}' is protected"],
                        )
        return None

    def _check_directory_traversal(self, path: str) -> bool:
        patterns = [r"\.\./", r"/\.\.", r"^\.\.", r"\.+/"]
        for pattern in patterns:
            if re.search(pattern, path):
                return True
        return False

    def _is_outside_cwd(self, path: str) -> bool:
        normalized_cwd = os.path.normpath(self.cwd).replace("\\", "/")
        normalized_path = os.path.normpath(path).replace("\\", "/")
        return not (normalized_path == normalized_cwd or normalized_path.startswith(normalized_cwd + "/"))

    def _check_dangerous_paths(self, path: str) -> str | None:
        dangerous_patterns = [
            "/etc/passwd", "/etc/shadow", "/etc/sudoers",
            "/root/.ssh/", "/home/*/.ssh/", "/.ssh/",
            "**/id_rsa", "**/id_dsa", "**/id_ed25519",
            "**/*.pem", "**/private_key*",
        ]
        for pattern in dangerous_patterns:
            if fnmatch.fnmatch(path.lower(), pattern.lower()):
                return f"Path matches dangerous pattern: {pattern}"
        return None
