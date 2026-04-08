"""
Context 注入系统 - 参考 Claude Code 的 context.ts 设计
分层构建系统上下文：git status、文件信息、日期、skill 内容等
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Any


def find_config_file() -> str | None:
    """查找配置文件位置，优先级：当前目录 > 项目目录 > HOME 目录"""
    # 当前目录
    for name in ["crush.json", ".crush.json", "claude_agent.json"]:
        if os.path.exists(name):
            return os.path.abspath(name)
    
    # 项目目录（scripts 的父目录）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)
    for name in ["crush.json", ".crush.json", "claude_agent.json"]:
        path = os.path.join(project_dir, name)
        if os.path.exists(path):
            return path
    
    # HOME 目录
    home_config = os.path.expanduser("~/.config/claude-agent/crush.json")
    if os.path.exists(home_config):
        return home_config
    
    return None


def get_workspace() -> str | None:
    """
    获取配置的 workspace 路径
    优先级：当前目录 > HOME 目录
    """
    config_file = find_config_file()
    if config_file:
        try:
            with open(config_file, encoding="utf-8") as f:
                config = json.load(f)
            workspace = config.get("workspace", {}).get("path")
            if workspace:
                workspace = os.path.expanduser(workspace)
                workspace = os.path.abspath(workspace)
                if os.path.isdir(workspace):
                    return workspace
        except Exception:
            pass
    return None


def chdir_to_workspace() -> bool:
    """
    切换到配置的 workspace 目录
    返回是否成功切换
    """
    workspace = get_workspace()
    if workspace and workspace != os.getcwd():
        try:
            os.chdir(workspace)
            return True
        except Exception:
            return False
    return False


def switch_to_workspace() -> bool:
    """
    切换到 workspace 目录（如果没有配置则保持当前目录）
    用于在任何目录下启动 agent 的场景
    """
    workspace = get_workspace()
    if workspace:
        try:
            os.chdir(workspace)
            return True
        except Exception:
            pass
    # 没有配置 workspace 时，保持当前目录不变
    return False


def get_git_status(cwd: str | None = None) -> str | None:
    """
    获取 git 状态，对应 Claude Code 的 getGitStatus()
    """
    try:
        if cwd is None:
            cwd = os.getcwd()
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=cwd, capture_output=True, timeout=5
        )
        if result.stdout.decode("utf-8", errors="replace").strip() != "true":
            return None

        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd, capture_output=True, timeout=5
        ).stdout.decode("utf-8", errors="replace").strip()

        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=cwd, capture_output=True, timeout=5
        ).stdout.decode("utf-8", errors="replace").strip()

        log = subprocess.run(
            ["git", "log", "--oneline", "-n", "5"],
            cwd=cwd, capture_output=True, timeout=5
        ).stdout.decode("utf-8", errors="replace").strip()

        return f"""This is the git status at the start of the conversation.

Current branch: {branch or '(detached)'}

Status:
{status or '(clean)'}

Recent commits:
{log}"""
    except Exception:
        return None


def get_current_date() -> str:
    """获取当前日期"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_cwd_info() -> str:
    """获取当前目录信息"""
    try:
        cwd = os.getcwd()
        items = os.listdir(cwd)[:20]
        return f"""Current working directory: {cwd}

Directory contents (first 20):
{chr(10).join(items)}"""
    except Exception:
        return ""


def get_file_info(file_path: str) -> str:
    """获取指定文件的信息"""
    try:
        p = Path(file_path)
        if not p.exists():
            return f"File not found: {file_path}"
        stat = p.stat()
        return f"""File: {file_path}
Size: {stat.st_size} bytes
Modified: {datetime.fromtimestamp(stat.st_mtime)}"""
    except Exception as e:
        return f"Error reading file: {e}"


def get_lsp_info() -> str | None:
    """
    获取 LSP 配置信息
    """
    config_file = find_config_file()
    if not config_file:
        return None

    try:
        with open(config_file, encoding="utf-8") as f:
            config = json.load(f)
        lsp_config = config.get("lsp", {})
        if not lsp_config:
            return None

        languages = list(lsp_config.keys())
        info = f"""LSP Configuration (from {config_file}):
Available language servers: {', '.join(languages)}

You can use LSP tools to get code context:
- LSPInit: Initialize LSP server for a file
- LSPDefinition: Go to Definition
- LSPHover: Get type information
- LSPTypeDefinition: Go to Type Definition
- LSPReferences: Find References
- LSPSymbols: Get file outline/symbols

When analyzing code, use LSP tools to provide better context."""
        return info
    except Exception:
        return None


class ContextBuilder:
    """
    分层 Context 构建器，对应 Claude Code 的 getSystemContext / getUserContext
    """

    def __init__(self):
        self.system_context_parts: list[str] = []
        self.user_context_parts: list[str] = []

    def add_system_context(self, content: str):
        """添加系统级上下文（git status、日期等）"""
        if content:
            self.system_context_parts.append(content)

    def add_user_context(self, content: str):
        """添加用户级上下文（CLAUDE.md、skill 内容等）"""
        if content:
            self.user_context_parts.append(content)

    def build(self) -> dict[str, str]:
        """
        构建最终 context 字典
        返回 {"system": "...", "user": "..."}
        """
        return {
            "system": "\n\n".join(self.system_context_parts),
            "user": "\n\n".join(self.user_context_parts),
        }

    def build_system_prompt_section(self) -> str:
        """构建完整的 system prompt 段落"""
        parts = []
        if self.system_context_parts:
            parts.append("## System Context\n")
            parts.append("\n".join(self.system_context_parts))
        if self.user_context_parts:
            parts.append("\n## User Context\n")
            parts.append("\n".join(self.user_context_parts))
        return "\n".join(parts)


def build_default_context() -> dict[str, str]:
    """构建默认 context（启动时调用一次）"""
    builder = ContextBuilder()

    builder.add_system_context(get_current_date())
    git_status = get_git_status()
    if git_status:
        builder.add_system_context(git_status)

    lsp_info = get_lsp_info()
    if lsp_info:
        builder.add_system_context(lsp_info)

    cwd_info = get_cwd_info()
    if cwd_info:
        builder.add_user_context(cwd_info)

    return builder.build()


# === 分层 Context 数据类 ===

@dataclass
class SystemContext:
    """系统级上下文"""
    os: str
    arch: str
    python_version: str
    timestamp: str
    cwd: str


@dataclass
class GitContext:
    """Git 上下文"""
    branch: Optional[str]
    status: str
    diff: str
    log: str


@dataclass
class SessionContext:
    """会话上下文"""
    session_id: str
    message_count: int


@dataclass
class TaskContext:
    """任务上下文"""
    pending_tasks: int
    running_tasks: int


class LayeredContextBuilder:
    """
    分层 Context 构建器 - 增强版

    支持分层构建系统上下文，对应 DEVELOPMENT.md 中的设计。
    """

    def __init__(self):
        self._layers: list[dict[str, Any]] = []

    def build(self, mode: str = "cli") -> dict[str, Any]:
        """
        构建完整上下文

        Args:
            mode: 构建模式 ('cli', 'web', 'api')

        Returns:
            分层上下文字典
        """
        layers = [
            self._build_system_context(),
            self._build_git_context(),
            self._build_cwd_context(),
            self._build_user_context(),
            self._build_session_context(),
            self._build_task_context(),
        ]

        if mode == "web":
            layers.append(self._build_web_context())

        return self._merge_layers(layers)

    def _build_system_context(self) -> dict[str, Any]:
        """系统级上下文"""
        return {
            "system": SystemContext(
                os=platform.system(),
                arch=platform.machine(),
                python_version=platform.python_version(),
                timestamp=datetime.now().isoformat(),
                cwd=os.getcwd(),
            )
        }

    def _build_git_context(self) -> dict[str, Any]:
        """Git 上下文"""
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()

            status = subprocess.check_output(
                ["git", "status", "--porcelain"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()

            log = subprocess.check_output(
                ["git", "log", "-3", "--oneline"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()

            diff = subprocess.check_output(
                ["git", "diff", "--stat"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()

            return {
                "git": GitContext(
                    branch=branch,
                    status=status or "clean",
                    diff=diff,
                    log=log,
                )
            }
        except (subprocess.CalledProcessError, FileNotFoundError):
            return {"git": None}

    def _build_cwd_context(self) -> dict[str, Any]:
        """当前目录上下文"""
        return {"cwd": os.getcwd()}

    def _build_user_context(self) -> dict[str, Any]:
        """用户上下文"""
        return {
            "user": {
                "home": os.path.expanduser("~"),
            }
        }

    def _build_session_context(
        self, session_id: str = "", message_count: int = 0
    ) -> dict[str, Any]:
        """会话上下文"""
        return {
            "session": SessionContext(
                session_id=session_id,
                message_count=message_count,
            )
        }

    def _build_task_context(
        self, pending: int = 0, running: int = 0
    ) -> dict[str, Any]:
        """任务上下文"""
        return {
            "tasks": TaskContext(
                pending_tasks=pending,
                running_tasks=running,
            )
        }

    def _build_web_context(self) -> dict[str, Any]:
        """Web 模式额外上下文"""
        return {"mode": "web"}

    def _merge_layers(self, layers: list[dict[str, Any]]) -> dict[str, Any]:
        """合并所有层"""
        result = {}
        for layer in layers:
            result.update(layer)
        return result

    def inject_context(self, prompt: str, context: dict[str, Any]) -> str:
        """
        注入上下文到提示

        Args:
            prompt: 原始提示
            context: 上下文字典

        Returns:
            注入上下文后的提示
        """
        lines = [prompt, "\n\n--- Context ---"]

        if context.get("system"):
            s = context["system"]
            if isinstance(s, SystemContext):
                lines.append(f"OS: {s.os} ({s.arch}), Python {s.python_version}")

        if context.get("git"):
            g = context["git"]
            if isinstance(g, GitContext) and g:
                lines.append(f"Git branch: {g.branch}")
                if g.status != "clean":
                    lines.append(f"Git status:\n{g.status}")

        if context.get("cwd"):
            lines.append(f"Working directory: {context['cwd']}")

        if context.get("session"):
            s = context["session"]
            if isinstance(s, SessionContext):
                lines.append(f"Session: {s.session_id}")

        if context.get("tasks"):
            t = context["tasks"]
            if isinstance(t, TaskContext):
                if t.pending_tasks or t.running_tasks:
                    lines.append(
                        f"Tasks: {t.running_tasks} running, {t.pending_tasks} pending"
                    )

        return "\n".join(lines)
