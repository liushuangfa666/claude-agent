"""
PowerShellTool - Windows PowerShell 命令执行工具

仅在 Windows 平台启用，执行 PowerShell 命令并返回结果。
"""
from __future__ import annotations

import asyncio
import platform
from typing import Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tool import BaseTool, ToolResult


class PowerShellTool(BaseTool):
    """PowerShell 命令执行工具"""

    name = "PowerShell"
    description = "Execute PowerShell commands on Windows"

    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "PowerShell command to execute",
            },
            "timeout": {
                "type": "number",
                "description": "Timeout in seconds",
                "default": 30,
            },
            "cwd": {
                "type": "string",
                "description": "Working directory",
            },
        },
        "required": ["command"],
    }

    def is_enabled(self) -> bool:
        """仅在 Windows 上启用"""
        return platform.system() == "Windows"

    async def call(self, args: dict, context: Any) -> ToolResult:
        command = args["command"]
        timeout = args.get("timeout", 30)
        cwd = args.get("cwd")

        try:
            proc = await asyncio.create_subprocess_exec(
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Command timed out after {timeout}s",
                )

            result = stdout.decode("utf-8", errors="replace")
            err = stderr.decode("utf-8", errors="replace")

            if proc.returncode != 0:
                return ToolResult(
                    success=False,
                    data=result,
                    error=err or f"Exit code: {proc.returncode}",
                )

            return ToolResult(success=True, data=result)

        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
