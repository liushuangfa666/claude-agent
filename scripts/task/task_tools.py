"""
Task 工具实现

提供任务管理的各种工具。
"""
from __future__ import annotations

import logging

from ..tool import BaseTool, ToolResult
from .models import Task, TaskStatus, TaskType
from .runner import BackgroundTaskRunner
from .store import TaskStore

logger = logging.getLogger(__name__)


class TaskCreateTool(BaseTool):
    """创建任务工具"""

    name = "TaskCreate"
    description = "创建新任务"

    input_schema = {
        "type": "object",
        "properties": {
            "subject": {"type": "string", "description": "任务主题"},
            "description": {"type": "string", "description": "任务描述"},
            "active_form": {"type": "string", "description": "进行时描述"},
            "task_type": {"type": "string", "enum": ["bash", "agent", "workflow"], "description": "任务类型"},
            "blocks": {"type": "array", "items": {"type": "string"}, "description": "阻塞此任务的任务ID"},
        },
        "required": ["subject"],
    }

    def __init__(
        self,
        store: TaskStore | None = None,
        runner: BackgroundTaskRunner | None = None,
    ):
        super().__init__()
        self._store = store or TaskStore()
        self._runner = runner or BackgroundTaskRunner(self._store)

    async def call(self, args: dict, context: dict) -> ToolResult:
        session_id = context.get("session_id", "default")

        task = Task(
            id="",
            subject=args["subject"],
            description=args.get("description", ""),
            active_form=args.get("active_form", ""),
            task_type=TaskType(args.get("task_type", "bash")),
            blocked_by=args.get("blocks", []),
        )

        task = self._store.create(task, session_id)

        return ToolResult(
            success=True,
            data={"task_id": task.id, "subject": task.subject},
        )


class TaskGetTool(BaseTool):
    """获取任务详情工具"""

    name = "TaskGet"
    description = "获取任务详情"

    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "任务ID"},
        },
        "required": ["task_id"],
    }

    def __init__(self, store: TaskStore | None = None):
        super().__init__()
        self._store = store or TaskStore()

    async def call(self, args: dict, context: dict) -> ToolResult:
        session_id = context.get("session_id", "default")
        task_id = args["task_id"]

        task = self._store.get(task_id, session_id)

        if not task:
            return ToolResult(success=False, data=None, error=f"Task {task_id} not found")

        return ToolResult(success=True, data=task.to_dict())


class TaskListTool(BaseTool):
    """列出任务工具"""

    name = "TaskList"
    description = "列出所有任务"

    input_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "failed", "killed"]},
        },
    }

    def __init__(self, store: TaskStore | None = None):
        super().__init__()
        self._store = store or TaskStore()

    async def call(self, args: dict, context: dict) -> ToolResult:
        session_id = context.get("session_id", "default")

        if "status" in args:
            tasks = self._store.get_by_status(session_id, TaskStatus(args["status"]))
        else:
            tasks = self._store.list_all(session_id)

        return ToolResult(
            success=True,
            data=[{"id": t.id, "subject": t.subject, "status": t.status.value, "owner": t.owner, "blocked_by": t.blocked_by} for t in tasks],
        )


class TaskUpdateTool(BaseTool):
    """更新任务工具"""

    name = "TaskUpdate"
    description = "更新任务状态"

    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "任务ID"},
            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "failed", "killed"], "description": "新状态"},
        },
        "required": ["task_id", "status"],
    }

    def __init__(self, store: TaskStore | None = None):
        super().__init__()
        self._store = store or TaskStore()

    async def call(self, args: dict, context: dict) -> ToolResult:
        session_id = context.get("session_id", "default")
        task_id = args["task_id"]
        status = TaskStatus(args["status"])

        task = self._store.update_status(task_id, session_id, status)

        if not task:
            return ToolResult(success=False, data=None, error=f"Task {task_id} not found")

        return ToolResult(success=True, data={"task_id": task.id, "status": task.status.value})


class TaskStopTool(BaseTool):
    """停止任务工具"""

    name = "TaskStop"
    description = "停止运行中的任务"

    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "任务ID"},
        },
        "required": ["task_id"],
    }

    def __init__(self, runner: BackgroundTaskRunner | None = None, store: TaskStore | None = None):
        super().__init__()
        self._runner = runner or BackgroundTaskRunner(store)
        self._store = self._runner._store

    async def call(self, args: dict, context: dict) -> ToolResult:
        session_id = context.get("session_id", "default")
        task_id = args["task_id"]

        stopped = await self._runner.stop_task(task_id)

        if stopped:
            self._store.update_status(task_id, session_id, TaskStatus.KILLED)
            return ToolResult(success=True, data={"task_id": task_id, "message": "Task stopped"})

        return ToolResult(success=False, data=None, error=f"Task {task_id} not running")


class TaskOutputTool(BaseTool):
    """获取任务输出工具（支持流式输出）"""

    name = "TaskOutput"
    description = "获取任务输出，支持流式获取进行中的任务输出"

    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "任务ID"},
            "stream": {"type": "boolean", "description": "是否流式获取（实时返回部分输出）"},
            "clear": {"type": "boolean", "description": "获取后是否清除输出缓冲区"},
            "watch": {"type": "boolean", "description": "是否持续监听输出变化"},
        },
        "required": ["task_id"],
    }

    def __init__(self, runner: BackgroundTaskRunner | None = None):
        super().__init__()
        self._runner = runner or BackgroundTaskRunner()
        self._last_output_length: dict[str, int] = {}  # 跟踪上次输出长度

    async def call(self, args: dict, context: dict) -> ToolResult:
        task_id = args["task_id"]
        stream = args.get("stream", False)
        clear = args.get("clear", False)
        watch = args.get("watch", False)

        bg_task = self._runner.get_running_task(task_id)

        if not bg_task:
            return ToolResult(success=False, data=None, error=f"Task {task_id} not running")

        if stream or watch:
            # 流式/监听模式：返回新增的输出
            last_len = self._last_output_length.get(task_id, 0)
            current_output = bg_task.output

            if len(current_output) > last_len:
                new_output = current_output[last_len:]
                self._last_output_length[task_id] = len(current_output)
            else:
                new_output = "" if bg_task.is_running else current_output

            result_data = {
                "task_id": task_id,
                "status": bg_task.task.status.value,
                "is_running": bg_task.is_running,
                "new_output": new_output,
                "total_output": current_output if not stream else new_output,
                "error": bg_task.error,
            }

            if clear and not bg_task.is_running:
                # 任务结束后清除缓冲区
                self._last_output_length.pop(task_id, None)

            return ToolResult(success=True, data=result_data)
        else:
            # 普通模式：返回完整输出
            return ToolResult(
                success=True,
                data={
                    "task_id": task_id,
                    "status": bg_task.task.status.value,
                    "output": bg_task.output,
                    "error": bg_task.error,
                    "is_running": bg_task.is_running,
                },
            )
