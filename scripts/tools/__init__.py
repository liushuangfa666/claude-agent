"""
P2 工具模块 - 补充关键工具

包含:
- PowerShellTool: Windows PowerShell 命令执行
- WorkflowTool: 复杂工作流编排
- CronTool: 定时任务管理
- MCP 资源工具
"""
from __future__ import annotations

from pathlib import Path
import importlib.util

scripts_dir = Path(__file__).parent.parent
tools_spec = importlib.util.spec_from_file_location("core_tools", scripts_dir / "tools.py")
core_tools = importlib.util.module_from_spec(tools_spec)
tools_spec.loader.exec_module(core_tools)

BashTool = core_tools.BashTool
EditTool = core_tools.EditTool
GlobTool = core_tools.GlobTool
GrepTool = core_tools.GrepTool
ReadTool = core_tools.ReadTool
WriteTool = core_tools.WriteTool
validate_path_security = core_tools.validate_path_security
register_base_tools = core_tools.register_base_tools

from .powershell import PowerShellTool
from .workflow import WorkflowTool, WorkflowStep, WorkflowDefinition
from .cron import CronCreateTool, CronDeleteTool, CronListTool
from .mcp_utils import ListMcpResourcesTool, ReadMcpResourceTool
from .remote_agent import RemoteAgentTaskTool
from .browser_tool import WebBrowserTool

__all__ = [
    "BashTool",
    "EditTool",
    "GlobTool",
    "GrepTool",
    "ReadTool",
    "WriteTool",
    "validate_path_security",
    "register_base_tools",
    "PowerShellTool",
    "WorkflowTool",
    "WorkflowStep",
    "WorkflowDefinition",
    "CronCreateTool",
    "CronDeleteTool",
    "CronListTool",
    "ListMcpResourcesTool",
    "ReadMcpResourceTool",
    "RemoteAgentTaskTool",
    "WebBrowserTool",
]
