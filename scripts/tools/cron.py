"""
CronTool - 定时任务管理工具

提供 cron 定时任务的创建、删除、列表功能。
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tool import BaseTool, ToolResult


CRON_STORAGE_DIR = os.path.join(os.path.expanduser("~"), ".claude-agent", "cron")
os.makedirs(CRON_STORAGE_DIR, exist_ok=True)


def get_cron_file() -> str:
    """获取 cron 任务存储文件路径"""
    return os.path.join(CRON_STORAGE_DIR, "tasks.json")


@dataclass
class CronJob:
    """定时任务定义"""
    id: str
    name: str
    schedule: str
    command: str
    description: str = ""
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_run: str | None = None
    next_run: str | None = None


def load_cron_jobs() -> dict[str, CronJob]:
    """加载所有定时任务"""
    cron_file = get_cron_file()
    if os.path.exists(cron_file):
        try:
            with open(cron_file, encoding="utf-8") as f:
                data = json.load(f)
                return {job_id: CronJob(**job) for job_id, job in data.items()}
        except Exception:
            pass
    return {}


def save_cron_jobs(jobs: dict[str, CronJob]) -> None:
    """保存定时任务"""
    cron_file = get_cron_file()
    os.makedirs(os.path.dirname(cron_file), exist_ok=True)
    with open(cron_file, "w", encoding="utf-8") as f:
        data = {job_id: job.__dict__ for job_id, job in jobs.items()}
        json.dump(data, f, ensure_ascii=False, indent=2)


class CronCreateTool(BaseTool):
    """创建定时任务工具"""

    name = "CronCreate"
    description = "Create a new scheduled cron task"

    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Task name"},
            "schedule": {"type": "string", "description": "Cron expression (min hour day month weekday)"},
            "command": {"type": "string", "description": "Command to execute"},
            "description": {"type": "string", "description": "Task description"},
        },
        "required": ["name", "schedule", "command"],
    }

    async def call(self, args: dict, context: Any) -> ToolResult:
        name = args["name"]
        schedule = args["schedule"]
        command = args["command"]
        description = args.get("description", "")

        parts = schedule.split()
        if len(parts) != 5:
            return ToolResult(
                success=False,
                data=None,
                error="Invalid cron expression. Expected format: 'min hour day month weekday'",
            )

        job_id = str(uuid.uuid4())[:8]

        job = CronJob(
            id=job_id,
            name=name,
            schedule=schedule,
            command=command,
            description=description,
        )

        jobs = load_cron_jobs()
        jobs[job_id] = job
        save_cron_jobs(jobs)

        if platform.system() != "Windows":
            await self._register_system_cron(job)

        return ToolResult(
            success=True,
            data={
                "id": job_id,
                "name": name,
                "schedule": schedule,
                "command": command,
            },
        )

    async def _register_system_cron(self, job: CronJob) -> None:
        """注册到系统 cron（Unix 系统）"""
        try:
            cron_line = f"{job.schedule} {job.command} # {job.name} ({job.id})\n"
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
            )
            current_cron = result.stdout if result.returncode == 0 else ""

            new_cron = current_cron + cron_line
            subprocess.run(
                ["crontab", "-"],
                input=new_cron,
                text=True,
            )
        except Exception:
            pass


class CronDeleteTool(BaseTool):
    """删除定时任务工具"""

    name = "CronDelete"
    description = "Delete an existing cron task"

    input_schema = {
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "Job ID to delete"},
        },
        "required": ["job_id"],
    }

    async def call(self, args: dict, context: Any) -> ToolResult:
        job_id = args["job_id"]

        jobs = load_cron_jobs()
        if job_id not in jobs:
            return ToolResult(success=False, data=None, error=f"Job {job_id} not found")

        job = jobs[job_id]

        del jobs[job_id]
        save_cron_jobs(jobs)

        if platform.system() != "Windows":
            await self._unregister_system_cron(job)

        return ToolResult(
            success=True,
            data={
                "deleted": True,
                "job_id": job_id,
                "name": job.name,
            },
        )

    async def _unregister_system_cron(self, job: CronJob) -> None:
        """从系统 cron 中移除"""
        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return

            lines = result.stdout.split("\n")
            new_lines = [
                line for line in lines
                if f"({job.id})" not in line
            ]

            new_cron = "\n".join(new_lines)
            subprocess.run(
                ["crontab", "-"],
                input=new_cron,
                text=True,
            )
        except Exception:
            pass


class CronListTool(BaseTool):
    """列出定时任务工具"""

    name = "CronList"
    description = "List all scheduled cron tasks"

    input_schema = {
        "type": "object",
        "properties": {
            "enabled_only": {
                "type": "boolean",
                "description": "Only list enabled tasks",
                "default": False,
            },
        },
    }

    async def call(self, args: dict, context: Any) -> ToolResult:
        enabled_only = args.get("enabled_only", False)

        jobs = load_cron_jobs()

        job_list = []
        for job_id, job in jobs.items():
            if enabled_only and not job.enabled:
                continue
            job_list.append({
                "id": job.id,
                "name": job.name,
                "schedule": job.schedule,
                "command": job.command,
                "description": job.description,
                "enabled": job.enabled,
                "created_at": job.created_at,
            })

        return ToolResult(
            success=True,
            data={
                "count": len(job_list),
                "jobs": job_list,
            },
        )
