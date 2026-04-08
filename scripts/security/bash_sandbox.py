"""
Bash 沙箱 - Bash Sandbox
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum


class ValidationStatus(Enum):
    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"
    DANGEROUS = "dangerous"


@dataclass
class ValidationResult:
    status: ValidationStatus
    message: str
    warnings: list[str] = field(default_factory=list)
    sanitized_command: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.status in (ValidationStatus.VALID, ValidationStatus.WARNING)

    @property
    def is_safe(self) -> bool:
        return self.status == ValidationStatus.VALID


@dataclass
class ExecResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    execution_time: float = 0.0
    error_message: str | None = None


class BashSandbox:
    """Bash 沙箱"""

    DEFAULT_ALLOWED_COMMANDS: set[str] = {
        "git", "ls", "cd", "pwd", "cat", "echo", "head", "tail",
        "grep", "find", "wc", "sort", "uniq", "cut", "tr",
        "mkdir", "touch", "cp", "mv", "diff", "stat",
        "which", "where", "type", "command",
        "python", "python3", "node", "ruby", "perl", "php",
        "pip", "pip3", "npm", "yarn", "pnpm", "bun",
        "cargo", "go", "rustc", "javac", "java",
        "pytest", "jest", "mocha", "rspec",
        "make", "cmake", "gradle", "mvn",
        "curl", "wget", "ssh", "scp", "rsync",
        "tar", "gzip", "gunzip", "zip", "unzip",
        "chmod", "chown", "chgrp",
    }

    DANGEROUS_COMMANDS: set[str] = {
        "rm", "dd", "mkfs", "fdisk", "parted",
        "shutdown", "reboot", "halt", "poweroff",
        "kill", "killall", "pkill",
        "sudo", "su",
        ":",
    }

    DANGEROUS_FLAGS: dict[str, list[str]] = {
        "rm": ["-rf", "-r", "-f", "--no-preserve-root", "--preserve-root"],
        "dd": ["of=", "if="],
        "chmod": ["000", "-R 777", "-R 000"],
        "chown": ["-R root", "-R 0"],
        "curl": ["-d", "--data", "--data-binary", "-F"],
        "wget": ["-O", "--output-document"],
        "git": ["push", "force", "--force", "push --force"],
        "docker": ["rm", "rmi", "prune", "system prune"],
        "kubectl": ["delete", "exec", "run --rm"],
        "npm": ["publish", "unpublish"],
        "pip": ["install", "uninstall"],
        "python": ["-c", "-m pip", "-c "],
    }

    ALLOWED_PREFIXES: set[str] = {
        "git ", "ls ", "cat ", "echo ", "head ", "tail ",
        "grep ", "find ", "wc ", "sort ", "uniq ", "cut ",
        "mkdir ", "touch ", "cp ", "diff ", "stat ",
        "python ", "python3 ", "node ", "ruby ",
        "pytest", "jest", "make ", "docker ps",
    }

    @staticmethod
    def _get_default_path() -> str:
        """Get platform-appropriate default PATH."""
        system = platform.system().lower()
        if system == "windows":
            return os.environ.get("PATH", "C:\\Windows\\System32;C:\\Windows")
        elif system == "darwin":
            return "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        else:
            return "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

    @staticmethod
    def _is_windows() -> bool:
        """Check if running on Windows."""
        return platform.system().lower() == "windows"

    @staticmethod
    def _get_path_separator() -> str:
        """Get platform-appropriate PATH separator."""
        return ";" if BashSandbox._is_windows() else ":"

    def __init__(
        self,
        allowed_commands: set[str] | None = None,
        dangerous_flags: dict[str, list[str]] | None = None,
        max_output_size: int = 1024 * 1024,
        timeout_seconds: int = 30,
        enable_timeout: bool = True,
    ):
        default_cmds = self.DEFAULT_ALLOWED_COMMANDS.copy()
        if self._is_windows():
            default_cmds.update({"cmd", "del", "rmdir", "type", "findstr", "where", "dir"})
        self.allowed_commands = allowed_commands or default_cmds

        default_dangerous: dict[str, list[str]] = {
            "rm": ["-rf", "-r", "-f", "--no-preserve-root", "--preserve-root"],
            "dd": ["of=", "if="],
            "chmod": ["000", "-R 777", "-R 000"],
            "chown": ["-R root", "-R 0"],
            "curl": ["-d", "--data", "--data-binary", "-F"],
            "wget": ["-O", "--output-document"],
            "git": ["push", "force", "--force", "push --force"],
            "docker": ["rm", "rmi", "prune", "system prune"],
            "kubectl": ["delete", "exec", "run --rm"],
            "npm": ["publish", "unpublish"],
            "pip": ["install", "uninstall"],
            "python": ["-c", "-m pip", "-c "],
        }
        if self._is_windows():
            default_dangerous.update({
                "del": ["/f", "/s", "/q"],
                "rmdir": ["/s", "/q"],
                "cmd": ["/c"],
            })
        self.dangerous_flags = dangerous_flags or default_dangerous
        self.max_output_size = max_output_size
        self.timeout_seconds = timeout_seconds
        self.enable_timeout = enable_timeout
        self._default_path = self._get_default_path()

    def _normalize_command_for_platform(self, command: str) -> str:
        """Normalize command for platform - extract base command regardless of OS."""
        if not command or not command.strip():
            return ""

        parts = command.strip().split()
        if not parts:
            return ""

        base = parts[0].lower()
        if base in ("ls", "dir"):
            return "ls"
        if base in ("cat", "type"):
            return "cat"
        if base in ("grep", "findstr"):
            return "grep"
        if base in ("rm", "del", "rmdir"):
            return "rm"
        return base

    def validate_command(self, command: str) -> ValidationResult:
        if not command or not command.strip():
            return ValidationResult(
                status=ValidationStatus.INVALID,
                message="Empty command",
            )

        parsed = self._parse_command(command)
        if not parsed:
            return ValidationResult(
                status=ValidationStatus.INVALID,
                message="Invalid command syntax",
            )

        base_cmd = parsed[0]
        args = parsed[1:] if len(parsed) > 1 else []
        full_cmd_str = " ".join(parsed)

        normalized_cmd = self._normalize_command_for_platform(base_cmd)

        warnings: list[str] = []

        if normalized_cmd == ":" or base_cmd == ":":
            return ValidationResult(
                status=ValidationStatus.DANGEROUS,
                message="Null command (:) is not allowed",
            )

        if normalized_cmd in self.DANGEROUS_COMMANDS or base_cmd in self.DANGEROUS_COMMANDS:
            return ValidationResult(
                status=ValidationStatus.DANGEROUS,
                message=f"Command '{base_cmd}' is restricted for safety",
            )

        if normalized_cmd not in self.allowed_commands and base_cmd not in self.allowed_commands:
            if not any(full_cmd_str.startswith(p) for p in self.ALLOWED_PREFIXES):
                return ValidationResult(
                    status=ValidationStatus.INVALID,
                    message=f"Command '{base_cmd}' is not in the allowed list",
                )

        check_cmd = normalized_cmd if normalized_cmd in self.dangerous_flags else base_cmd
        for dangerous_cmd, dangerous_args in self.dangerous_flags.items():
            if check_cmd == dangerous_cmd:
                for arg in args:
                    for dangerous in dangerous_args:
                        if dangerous in arg or arg.startswith(dangerous):
                            warnings.append(f"Potentially dangerous argument '{arg}' for {base_cmd}")

        if self._contains_rce_pattern(command):
            return ValidationResult(
                status=ValidationStatus.DANGEROUS,
                message="Command contains patterns that may execute remote code",
                warnings=warnings,
            )

        if warnings:
            return ValidationResult(
                status=ValidationStatus.WARNING,
                message="Command is allowed but has warnings",
                warnings=warnings,
            )

        return ValidationResult(status=ValidationStatus.VALID, message="Command is valid")

    def _translate_command_for_windows(self, command: str) -> str:
        """Translate Unix commands to Windows equivalents if needed."""
        if not self._is_windows():
            return command

        cmd_lower = command.strip().lower()

        translations: dict[str, str] = {
            "ls -la": "dir /a",
            "ls -l": "dir",
            "ls": "dir",
            "grep": "findstr",
            "cat": "type",
            "rm -rf": "rmdir /s /q",
            "rm -r": "rmdir /s /q",
            "rm -f": "del /f",
            "rm": "del /f",
            "cp": "copy",
            "mv": "move",
            "touch": "type nul >",
            "clear": "cls",
            "which": "where",
            "pwd": "cd",
        }

        for unix_cmd, win_cmd in translations.items():
            if cmd_lower.startswith(unix_cmd):
                return win_cmd + command[len(unix_cmd):]

        if cmd_lower.startswith("ls "):
            return "dir " + command[3:]
        elif cmd_lower.startswith("grep "):
            return command.replace("grep ", "findstr ", 1)
        elif cmd_lower.startswith("cat "):
            return "type " + command[4:]

        return command

    def _parse_command(self, command: str) -> list[str] | None:
        try:
            parts = command.strip().split()
            if not parts:
                return None
            return parts
        except Exception:
            return None

    def _contains_rce_pattern(self, command: str) -> bool:
        rce_patterns = [
            r";\s*rm\s", r";\s*wget\s", r";\s*curl\s",
            r"\|\s*bash", r"\|\s*sh\s", r"&&\s*rm\s",
            r"\$\([^)]*\)", r"`[^`]+`", r">\s*/dev/",
        ]
        for pattern in rce_patterns:
            if re.search(pattern, command):
                return True
        return False

    def execute_sandboxed(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecResult:
        start_time = time.time()

        validation = self.validate_command(command)
        if not validation.is_valid:
            return ExecResult(
                success=False,
                error_message=f"Command validation failed: {validation.message}",
                execution_time=time.time() - start_time,
            )

        try:
            exec_env = env.copy() if env else {}
            exec_env["PATH"] = self._default_path

            translated_cmd = self._translate_command_for_windows(command)

            if self._is_windows():
                use_shell = True
            else:
                use_shell = True

            process = subprocess.Popen(
                translated_cmd,
                shell=use_shell,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=exec_env,
                text=True,
            )

            if self.enable_timeout:
                try:
                    stdout, stderr = process.communicate(timeout=self.timeout_seconds)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                    return ExecResult(
                        success=False,
                        stdout=stdout[: self.max_output_size],
                        stderr=stderr[: self.max_output_size],
                        error_message=f"Command timed out after {self.timeout_seconds}s",
                        execution_time=time.time() - start_time,
                    )
            else:
                stdout, stderr = process.communicate()

            stdout = stdout[: self.max_output_size]
            stderr = stderr[: self.max_output_size]

            return ExecResult(
                success=process.returncode == 0,
                stdout=stdout,
                stderr=stderr,
                return_code=process.returncode,
                execution_time=time.time() - start_time,
            )

        except Exception as e:
            return ExecResult(
                success=False,
                error_message=f"Execution failed: {str(e)}",
                execution_time=time.time() - start_time,
            )

    def add_allowed_command(self, command: str) -> None:
        self.allowed_commands.add(command)

    def remove_allowed_command(self, command: str) -> None:
        self.allowed_commands.discard(command)
