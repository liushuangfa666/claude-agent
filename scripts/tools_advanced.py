"""
高级工具实现 - Task工具组, Web工具, LSP工具, AgentTool
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime

try:
    from tool import BaseTool, ToolResult
except ImportError:
    from scripts.tool import BaseTool, ToolResult


IS_WINDOWS = platform.system() == "Windows"


def wsl_path_to_linux(windows_path: str) -> str:
    """将 Windows 路径转换为 WSL/Linux 路径"""
    if not IS_WINDOWS:
        try:
            with open("/proc/version") as f:
                if "microsoft" not in f.read().lower() and "wsl" not in f.read().lower():
                    return windows_path
        except:
            return windows_path

    path = windows_path.strip().replace("\\\\", "/").replace("\\", "/")
    if path.startswith("//") or path.startswith("\\\\"):
        match = re.match(r"^(//+|\\\\+)([^/]+)(/.*)?$", path)
        if match:
            server = match.group(2)
            rest = match.group(3) or ""
            return f"/mnt/unc/{server}{rest}"
    match = re.match(r"^([A-Za-z]):(/.*)?$", path)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2) or ""
        return f"/mnt/{drive}{rest}"
    return windows_path


# ============ Task 工具组 ============

TASK_STORAGE_DIR = os.path.join(os.path.expanduser("~"), ".claude-agent", "tasks")
os.makedirs(TASK_STORAGE_DIR, exist_ok=True)


def get_task_list_path() -> str:
    """获取任务列表文件路径"""
    return os.path.join(TASK_STORAGE_DIR, "tasks.json")


def load_tasks() -> dict:
    """加载任务列表"""
    path = get_task_list_path()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"tasks": [], "counter": 0}


def save_tasks(data: dict) -> None:
    """保存任务列表"""
    path = get_task_list_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def generate_task_id() -> str:
    """生成任务ID"""
    data = load_tasks()
    data["counter"] += 1
    task_id = str(data["counter"])
    save_tasks(data)
    return task_id


class TaskCreateTool(BaseTool):
    """创建新任务"""

    name = "TaskCreate"
    description = "创建一个新任务到任务列表"
    input_schema = {
        "type": "object",
        "properties": {
            "subject": {"type": "string", "description": "任务标题"},
            "description": {"type": "string", "description": "任务详细描述"},
            "activeForm": {"type": "string", "description": "进行中的状态描述"},
            "metadata": {"type": "object", "description": "附加元数据"}
        },
        "required": ["subject", "description"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        subject = args["subject"]
        description = args.get("description", "")
        active_form = args.get("activeForm", "")
        metadata = args.get("metadata", {})

        task_id = generate_task_id()

        task = {
            "id": task_id,
            "subject": subject,
            "description": description,
            "activeForm": active_form,
            "status": "pending",
            "owner": None,
            "blocks": [],
            "blockedBy": [],
            "metadata": metadata,
            "createdAt": datetime.now().isoformat(),
            "updatedAt": datetime.now().isoformat()
        }

        data = load_tasks()
        data["tasks"].append(task)
        save_tasks(data)

        return ToolResult(
            success=True,
            data={"task": {"id": task_id, "subject": subject}}
        )


class TaskGetTool(BaseTool):
    """获取任务详情"""

    name = "TaskGet"
    description = "根据ID获取任务详情"
    input_schema = {
        "type": "object",
        "properties": {
            "taskId": {"type": "string", "description": "任务ID"}
        },
        "required": ["taskId"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        task_id = args["taskId"]
        data = load_tasks()

        for task in data.get("tasks", []):
            if task["id"] == task_id:
                return ToolResult(
                    success=True,
                    data={
                        "task": {
                            "id": task["id"],
                            "subject": task["subject"],
                            "description": task["description"],
                            "status": task["status"],
                            "blocks": task.get("blocks", []),
                            "blockedBy": task.get("blockedBy", [])
                        }
                    }
                )

        return ToolResult(success=True, data={"task": None})


class TaskListTool(BaseTool):
    """列出所有任务"""

    name = "TaskList"
    description = "列出所有任务及其状态"
    input_schema = {
        "type": "object",
        "properties": {}
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        data = load_tasks()
        tasks = []

        for task in data.get("tasks", []):
            # 过滤内部任务
            if task.get("metadata", {}).get("_internal"):
                continue

            # 计算被阻塞的任务（排除已完成的）
            blocked_by = task.get("blockedBy", [])
            if task["status"] != "completed":
                resolved_ids = {t["id"] for t in data["tasks"] if t["status"] == "completed"}
                blocked_by = [b for b in blocked_by if b not in resolved_ids]

            tasks.append({
                "id": task["id"],
                "subject": task["subject"],
                "status": task["status"],
                "owner": task.get("owner"),
                "blockedBy": blocked_by
            })

        return ToolResult(success=True, data={"tasks": tasks})


class TaskUpdateTool(BaseTool):
    """更新任务状态/信息"""

    name = "TaskUpdate"
    description = "更新任务信息（状态、描述、拥有人等）"
    input_schema = {
        "type": "object",
        "properties": {
            "taskId": {"type": "string", "description": "任务ID"},
            "subject": {"type": "string", "description": "新标题"},
            "description": {"type": "string", "description": "新描述"},
            "activeForm": {"type": "string", "description": "进行中状态"},
            "status": {"type": "string", "description": "新状态 (pending/in_progress/completed)"},
            "addBlocks": {"type": "array", "items": {"type": "string"}, "description": "该任务阻塞的其他任务ID"},
            "addBlockedBy": {"type": "array", "items": {"type": "string"}, "description": "阻塞该任务的任务ID"},
            "owner": {"type": "string", "description": "任务负责人"}
        },
        "required": ["taskId"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        task_id = args["taskId"]
        data = load_tasks()

        task = None
        task_index = -1
        for i, t in enumerate(data["tasks"]):
            if t["id"] == task_id:
                task = t
                task_index = i
                break

        if not task:
            return ToolResult(success=False, data=None, error=f"任务 {task_id} 不存在")

        updated_fields = []

        for field_name in ["subject", "description", "activeForm", "owner"]:
            if field_name in args and args[field_name]:
                old_val = task.get(field_name)
                new_val = args[field_name]
                if old_val != new_val:
                    task[field_name] = new_val
                    updated_fields.append(field_name)

        if "status" in args and args["status"]:
            new_status = args["status"]
            if new_status == "deleted":
                data["tasks"].pop(task_index)
                save_tasks(data)
                return ToolResult(
                    success=True,
                    data={"success": True, "taskId": task_id, "updatedFields": ["deleted"]}
                )
            if task["status"] != new_status:
                task["status"] = new_status
                updated_fields.append("status")

        if "addBlocks" in args and args["addBlocks"]:
            existing_blocks = set(task.get("blocks", []))
            for bid in args["addBlocks"]:
                if bid not in existing_blocks:
                    task.setdefault("blocks", []).append(bid)
            if task["blocks"]:
                updated_fields.append("blocks")

        if "addBlockedBy" in args and args["addBlockedBy"]:
            existing_blocked = set(task.get("blockedBy", []))
            for bid in args["addBlockedBy"]:
                if bid not in existing_blocked:
                    task.setdefault("blockedBy", []).append(bid)
            if task["blockedBy"]:
                updated_fields.append("blockedBy")

        task["updatedAt"] = datetime.now().isoformat()
        save_tasks(data)

        return ToolResult(
            success=True,
            data={
                "success": True,
                "taskId": task_id,
                "updatedFields": updated_fields
            }
        )


# ============ TaskOutput / TaskStop ============

# 后台任务存储
BACKGROUND_TASKS: dict = {}


@dataclass
class BackgroundTask:
    """后台任务"""
    task_id: str
    type: str  # "bash" | "agent"
    description: str
    status: str = "pending"  # pending/running/completed/failed/killed
    prompt: str = ""
    result: str = ""
    error: str = ""
    output_file: str = ""
    exit_code: int | None = None
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None


class TaskOutputTool(BaseTool):
    """获取后台任务输出"""

    name = "TaskOutput"
    description = "获取后台任务的输出结果"
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "任务ID"},
            "block": {"type": "boolean", "description": "是否等待完成", "default": True},
            "timeout": {"type": "integer", "description": "等待超时(毫秒)", "default": 30000}
        },
        "required": ["task_id"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        task_id = args["task_id"]
        block = args.get("block", True)
        timeout_ms = args.get("timeout", 30000)

        if task_id not in BACKGROUND_TASKS:
            return ToolResult(success=False, data=None, error=f"任务 {task_id} 不存在")

        task = BACKGROUND_TASKS[task_id]

        if not block:
            if task.status not in ("running", "pending"):
                return ToolResult(
                    success=True,
                    data={
                        "retrieval_status": "success",
                        "task": {
                            "task_id": task.task_id,
                            "task_type": task.type,
                            "status": task.status,
                            "description": task.description,
                            "output": task.result,
                            "error": task.error,
                            "exitCode": task.exit_code
                        }
                    }
                )
            return ToolResult(
                success=True,
                data={
                    "retrieval_status": "not_ready",
                    "task": {
                        "task_id": task.task_id,
                        "task_type": task.type,
                        "status": task.status,
                        "description": task.description,
                        "output": ""
                    }
                }
            )

        # 阻塞等待
        start = time.time() * 1000
        while time.time() * 1000 - start < timeout_ms:
            if task.status not in ("running", "pending"):
                return ToolResult(
                    success=True,
                    data={
                        "retrieval_status": "success",
                        "task": {
                            "task_id": task.task_id,
                            "task_type": task.type,
                            "status": task.status,
                            "description": task.description,
                            "output": task.result,
                            "error": task.error,
                            "exitCode": task.exit_code
                        }
                    }
                )
            await asyncio.sleep(0.1)

        return ToolResult(
            success=True,
            data={
                "retrieval_status": "timeout",
                "task": {
                    "task_id": task.task_id,
                    "task_type": task.type,
                    "status": task.status,
                    "description": task.description,
                    "output": task.result
                }
            }
        )


class TaskStopTool(BaseTool):
    """停止后台任务"""

    name = "TaskStop"
    description = "停止正在运行的后台任务"
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "任务ID"}
        },
        "required": ["task_id"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        task_id = args["task_id"]

        if task_id not in BACKGROUND_TASKS:
            return ToolResult(success=False, data=None, error=f"任务 {task_id} 不存在")

        task = BACKGROUND_TASKS[task_id]
        if task.status != "running":
            return ToolResult(
                success=False, data=None,
                error=f"任务 {task_id} 不在运行中 (状态: {task.status})"
            )

        task.status = "killed"
        task.end_time = time.time()

        return ToolResult(
            success=True,
            data={
                "message": f"已停止任务: {task_id} ({task.description})",
                "task_id": task_id,
                "task_type": task.type
            }
        )


# ============ WebFetch 工具 ============

class WebFetchTool(BaseTool):
    """获取网页内容"""

    name = "WebFetch"
    description = "获取URL内容并根据prompt提取信息"
    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要获取的URL"},
            "prompt": {"type": "string", "description": "在内容上执行的prompt"}
        },
        "required": ["url", "prompt"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        url = args.get("url", "")
        prompt = args.get("prompt", "")
        start = time.time()

        if not url:
            return ToolResult(success=False, data=None, error="URL is required")

        if not prompt:
            return ToolResult(success=False, data=None, error="prompt is required")

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; Claude/1.0)",
                    "Accept": "text/html,application/xhtml+xml,*/*"
                }
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                bytes_len = len(content.encode("utf-8"))

            # 简单的prompt处理：直接返回content的前10000字符
            # 实际生产环境应该用LLM提取
            if len(content) > 10000:
                result_text = content[:10000] + f"\n\n[内容已截断，原文 {len(content)} 字符]"
            else:
                result_text = content

            return ToolResult(
                success=True,
                data={
                    "bytes": bytes_len,
                    "code": 200,
                    "codeText": "OK",
                    "result": result_text,
                    "durationMs": int((time.time() - start) * 1000),
                    "url": url
                }
            )

        except urllib.error.HTTPError as e:
            return ToolResult(
                success=False, data=None,
                error=f"HTTP {e.code}: {e.reason}"
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class WebSearchTool(BaseTool):
    """网络搜索 - 使用 Tavily API"""

    name = "WebSearch"
    description = "搜索网络获取相关信息"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "allowed_domains": {"type": "array", "items": {"type": "string"}},
            "blocked_domains": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["query"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        query = args["query"]
        start = time.time()

        # Tavily API
        tavily_key = os.environ.get("TAVILY_API_KEY")
        if not tavily_key:
            return ToolResult(
                success=False, data=None,
                error="TAVILY_API_KEY environment variable not set"
            )

        data = {
            "api_key": tavily_key,
            "query": query,
            "max_results": 10,
            "include_answer": True,
        }

        try:
            req = urllib.request.Request(
                "https://api.tavily.com/search",
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            results = []
            for r in result.get("results", [])[:10]:
                results.append({
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                })

            answer = result.get("answer", "")

            duration = time.time() - start

            output = f"搜索结果 ({len(results)} 条):\n\n"
            for r in results:
                output += f"- {r['title']}: {r['url']}\n"
            if answer:
                output += f"\n答案: {answer}\n"

            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "results": results,
                    "answer": answer,
                    "durationSeconds": round(duration, 2)
                }
            )

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            return ToolResult(success=False, data=None, error=f"HTTP {e.code}: {body[:200]}")
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


# ============ AgentTool (支持 Subagent 类型) ============

# 存储子代理
SUB_AGENTS: dict = {}


@dataclass
class SubAgent:
    """子代理"""
    agent_id: str
    description: str
    prompt: str
    subagent_type: str = "GeneralPurpose"
    status: str = "pending"
    messages: list = field(default_factory=list)
    result: str = ""
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None


class AgentTool(BaseTool):
    """
    启动子代理执行任务

    支持:
    - description: 简短描述
    - prompt: 给子代理的任务描述
    - subagent_type: 代理类型 (Explore/Plan/Verification/GeneralPurpose)
    - run_in_background: 是否后台运行
    - isolation: 执行隔离模式 (worktree/none)
    """

    name = "Agent"
    description = """启动子代理执行任务，支持以下类型:
    - Explore: 只读代码探索
    - Plan: 复杂任务规划
    - Verification: 测试验证
    - GeneralPurpose: 通用（默认）
    """
    input_schema = {
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "简短描述(3-5词)"},
            "prompt": {"type": "string", "description": "给子代理的任务"},
            "subagent_type": {
                "type": "string",
                "enum": ["Explore", "Plan", "Verification", "GeneralPurpose"],
                "default": "GeneralPurpose",
                "description": "子代理类型"
            },
            "model": {"type": "string", "description": "模型选择"},
            "run_in_background": {"type": "boolean", "description": "后台运行", "default": False},
            "isolation": {
                "type": "string",
                "enum": ["worktree", "none"],
                "default": "none",
                "description": "执行隔离模式"
            }
        },
        "required": ["description", "prompt"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        description = args["description"]
        prompt = args["prompt"]
        subagent_type_str = args.get("subagent_type", "GeneralPurpose")
        run_in_background = args.get("run_in_background", False)

        agent_id = f"agent_{uuid.uuid4().hex[:8]}"

        # 导入 SubagentType
        try:
            from .subagent.types import SubagentType
        except ImportError:
            from scripts.subagent.types import SubagentType

        subagent_type = SubagentType(subagent_type_str)

        # 创建子代理
        agent = SubAgent(
            agent_id=agent_id,
            description=description,
            prompt=prompt,
            subagent_type=subagent_type_str,
        )
        SUB_AGENTS[agent_id] = agent

        isolation = args.get("isolation", "none")

        if run_in_background:
            # 后台模式：立即返回
            asyncio.create_task(self._run_agent_async(agent_id, subagent_type, isolation))
            return ToolResult(
                success=True,
                data={
                    "status": "async_launched",
                    "agentId": agent_id,
                    "description": description,
                    "subagent_type": subagent_type_str,
                    "prompt": prompt,
                    "isolation": isolation,
                    "output_file": f"~/.claude-agent/agents/{agent_id}.json"
                }
            )
        else:
            # 同步模式：等待完成
            result = await self._run_agent_sync(agent_id, subagent_type, isolation)
            return result

    async def _run_agent_async(self, agent_id: str, subagent_type, isolation: str = "none") -> None:
        """异步运行子代理"""
        try:
            await self._run_agent_sync(agent_id, subagent_type, isolation)
        except Exception as e:
            if agent_id in SUB_AGENTS:
                SUB_AGENTS[agent_id].status = "failed"
                SUB_AGENTS[agent_id].error = str(e)

    async def _run_agent_sync(self, agent_id: str, subagent_type, isolation: str = "none") -> ToolResult:
        """同步运行子代理"""
        if agent_id not in SUB_AGENTS:
            return ToolResult(success=False, data=None, error="代理不存在")

        agent = SUB_AGENTS[agent_id]
        agent.status = "running"

        try:
            # 使用 SubagentExecutor 执行
            try:
                from .subagent.executor import get_subagent_executor
            except ImportError:
                from scripts.subagent.executor import get_subagent_executor

            executor = get_subagent_executor()

            info = await executor.execute(
                prompt=agent.prompt,
                subagent_type=subagent_type,
                description=agent.description,
                isolation=isolation,
            )

            agent.status = info.status
            agent.result = info.result or ""
            agent.end_time = time.time()

            return ToolResult(
                success=True,
                data={
                    "status": info.status,
                    "agent_id": info.agent_id,
                    "result": info.result,
                    "duration_ms": info.duration_ms,
                }
            )

        except Exception as e:
            agent.status = "failed"
            agent.error = str(e)
            agent.end_time = time.time()
            return ToolResult(success=False, data=None, error=str(e))


# ============ TodoWrite 工具 ============

class TodoWriteTool(BaseTool):
    """写入待办事项"""

    name = "TodoWrite"
    description = "创建或更新待办事项列表"
    input_schema = {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "description": "in_progress | completed | pending"},
                        "content": {"type": "string", "description": "待办内容"},
                        "activeForm": {"type": "string", "description": "进行中描述"}
                    },
                    "required": ["status", "content"]
                }
            }
        },
        "required": ["todos"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        todos = args["todos"]

        # 存储到文件
        todo_file = os.path.join(os.path.expanduser("~"), ".claude-agent", "todos.json")
        os.makedirs(os.path.dirname(todo_file), exist_ok=True)

        with open(todo_file, "w", encoding="utf-8") as f:
            json.dump(todos, f, ensure_ascii=False, indent=2)

        return ToolResult(
            success=True,
            data={"todos": todos}
        )


# ============ 计划模式工具 ============

try:
    from .plan_mode import Plan, get_plan_mode_manager
except ImportError:
    from scripts.plan_mode import get_plan_mode_manager


class EnterPlanModeTool(BaseTool):
    """进入计划模式，生成执行计划但不执行"""

    name = "EnterPlanMode"
    description = "进入计划模式，为任务生成执行计划。AI 将分析任务并列出执行步骤，但不会实际执行工具。用户批准后可以通过 ExitPlanMode 执行计划。"
    input_schema = {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "要执行的任务描述"},
            "autoApprove": {"type": "boolean", "description": "是否自动批准计划", "default": False}
        },
        "required": ["task"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        task = args["task"]
        auto_approve = args.get("autoApprove", False)

        manager = get_plan_mode_manager()
        plan = manager.enter_plan_mode(task)

        if auto_approve:
            manager._auto_approve = True

        return ToolResult(
            success=True,
            data={
                "status": "plan_mode_entered",
                "task": task,
                "message": "计划模式已启用。请生成执行计划，列出每个步骤的工具调用和原因。"
            }
        )


class ExitPlanModeTool(BaseTool):
    """退出计划模式，执行或取消计划"""

    name = "ExitPlanMode"
    description = "退出计划模式。如果 approve=true，则执行计划中的步骤；如果 approve=false，则取消计划。"
    input_schema = {
        "type": "object",
        "properties": {
            "approve": {"type": "boolean", "description": "是否批准执行计划"},
            "rejectReason": {"type": "string", "description": "拒绝原因（当 approve=false 时）"}
        },
        "required": ["approve"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        approve = args["approve"]
        reject_reason = args.get("rejectReason", "")

        manager = get_plan_mode_manager()

        if not manager.enabled:
            return ToolResult(
                success=False,
                error="当前不在计划模式中"
            )

        plan = manager.exit_plan_mode(approved=approve)

        if not approve:
            return ToolResult(
                success=True,
                data={
                    "status": "plan_rejected",
                    "reason": reject_reason,
                    "message": "计划已取消"
                }
            )

        # 批准执行
        pending_steps = plan.steps  # 全部步骤视为批准

        return ToolResult(
            success=True,
            data={
                "status": "plan_approved",
                "plan": {
                    "task": plan.task,
                    "steps": [
                        {
                            "step_number": s.step_number,
                            "tool_name": s.tool_name,
                            "args": s.args,
                            "reason": s.reason
                        }
                        for s in pending_steps
                    ],
                    "total_steps": len(pending_steps)
                },
                "message": f"计划已批准，包含 {len(pending_steps)} 个步骤"
            }
        )


class PlanStepApproveTool(BaseTool):
    """批准计划中的特定步骤"""

    name = "PlanStepApprove"
    description = "批准计划中的特定步骤"
    input_schema = {
        "type": "object",
        "properties": {
            "stepNumber": {"type": "integer", "description": "步骤编号"}
        },
        "required": ["stepNumber"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        step_number = args["stepNumber"]
        manager = get_plan_mode_manager()

        if not manager.enabled:
            return ToolResult(success=False, error="当前不在计划模式中")

        if manager.approve_step(step_number):
            return ToolResult(success=True, data={"stepNumber": step_number, "status": "approved"})
        return ToolResult(success=False, error=f"步骤 {step_number} 不存在")


class PlanStepRejectTool(BaseTool):
    """拒绝计划中的特定步骤"""

    name = "PlanStepReject"
    description = "拒绝计划中的特定步骤"
    input_schema = {
        "type": "object",
        "properties": {
            "stepNumber": {"type": "integer", "description": "步骤编号"},
            "reason": {"type": "string", "description": "拒绝原因"}
        },
        "required": ["stepNumber"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        step_number = args["stepNumber"]
        reason = args.get("reason", "")
        manager = get_plan_mode_manager()

        if not manager.enabled:
            return ToolResult(success=False, error="当前不在计划模式中")

        if manager.reject_step(step_number):
            return ToolResult(success=True, data={"stepNumber": step_number, "status": "rejected", "reason": reason})
        return ToolResult(success=False, error=f"步骤 {step_number} 不存在")


# ============ Worktree 工具 ============

try:
    from worktree import WorktreeManager
except ImportError:
    from scripts.worktree import WorktreeManager


class WorktreeCreateTool(BaseTool):
    """创建 Git worktree 用于隔离执行"""

    name = "WorktreeCreate"
    description = "创建一个新的 Git worktree，用于隔离任务执行"
    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Worktree 名称"},
            "branch": {"type": "string", "description": "分支名称（可选，默认使用 worktree-{name}）"}
        },
        "required": ["name"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        name = args["name"]
        branch = args.get("branch")

        try:
            manager = WorktreeManager()
            path = manager.create(name, branch)
            return ToolResult(
                success=True,
                data={
                    "name": name,
                    "path": str(path),
                    "branch": branch or f"worktree-{name}"
                }
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class WorktreeRemoveTool(BaseTool):
    """删除 Git worktree"""

    name = "WorktreeRemove"
    description = "删除一个 Git worktree"
    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Worktree 名称"}
        },
        "required": ["name"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        name = args["name"]

        try:
            manager = WorktreeManager()
            manager.remove(name)
            return ToolResult(
                success=True,
                data={"name": name, "status": "removed"}
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class WorktreeListTool(BaseTool):
    """列出所有 Git worktree"""

    name = "WorktreeList"
    description = "列出所有 Git worktree"
    input_schema = {
        "type": "object",
        "properties": {}
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        try:
            manager = WorktreeManager()
            worktrees = manager.list()
            return ToolResult(
                success=True,
                data={
                    "worktrees": [
                        {"path": str(wt.path), "branch": wt.branch, "is_main": wt.is_main}
                        for wt in worktrees
                    ]
                }
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


# ============ Team 工具 ============

try:
    from .coordinator.team import Team, Teammate, TeamStorage, create_agent_id
    from .coordinator.mailbox import TeamMailbox, get_mailbox
    from .coordinator.constants import (
        AGENT_TYPE_WORKER,
        AGENT_TYPE_COORDINATOR,
        TEAM_LEAD_NAME,
        STATUS_RUNNING,
    )
except ImportError:
    from scripts.coordinator.team import Team, Teammate, TeamStorage, create_agent_id
    from scripts.coordinator.mailbox import TeamMailbox, get_mailbox
    from scripts.coordinator.constants import (
        AGENT_TYPE_WORKER,
        AGENT_TYPE_COORDINATOR,
        TEAM_LEAD_NAME,
        STATUS_RUNNING,
    )


class TeamCreateTool(BaseTool):
    """创建团队"""

    name = "TeamCreate"
    description = "创建一个新团队，可指定初始成员"
    input_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "团队名称"},
            "members": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "成员名称"},
                        "agent_type": {"type": "string", "description": "代理类型 (worker/coordinator)"},
                        "model": {"type": "string", "description": "模型名称"}
                    },
                    "required": ["name"]
                },
                "description": "初始成员列表"
            }
        },
        "required": ["name"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        name = args["name"]
        members_data = args.get("members", [])

        try:
            storage = TeamStorage()
            if storage.team_exists(name):
                return ToolResult(success=False, data=None, error=f"团队 {name} 已存在")

            lead_id = create_agent_id(AGENT_TYPE_COORDINATOR)
            team = Team(
                name=name,
                lead_agent_id=lead_id,
            )

            for m in members_data:
                teammate = Teammate(
                    agent_id=create_agent_id(AGENT_TYPE_WORKER),
                    name=m["name"],
                    agent_type=m.get("agent_type", AGENT_TYPE_WORKER),
                    model=m.get("model", "MiniMax-M2"),
                    color="",
                    status=STATUS_RUNNING,
                )
                team.add_member(teammate)

            storage.save_team(team)

            return ToolResult(
                success=True,
                data={
                    "name": name,
                    "lead_agent_id": lead_id,
                    "members_count": len(team.members),
                    "created_at": team.created_at.isoformat()
                }
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class TeamJoinTool(BaseTool):
    """加入团队"""

    name = "TeamJoin"
    description = "加入一个已存在的团队"
    input_schema = {
        "type": "object",
        "properties": {
            "team_name": {"type": "string", "description": "团队名称"},
            "name": {"type": "string", "description": "成员名称"},
            "agent_type": {"type": "string", "description": "代理类型 (worker/coordinator)"},
            "model": {"type": "string", "description": "模型名称"}
        },
        "required": ["team_name", "name"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        team_name = args["team_name"]
        name = args["name"]
        agent_type = args.get("agent_type", AGENT_TYPE_WORKER)
        model = args.get("model", "MiniMax-M2")

        try:
            storage = TeamStorage()
            team = storage.load_team(team_name)
            if team is None:
                return ToolResult(success=False, data=None, error=f"团队 {team_name} 不存在")

            existing = team.get_member_by_name(name)
            if existing:
                return ToolResult(success=False, data=None, error=f"成员 {name} 已存在")

            teammate = Teammate(
                agent_id=create_agent_id(agent_type),
                name=name,
                agent_type=agent_type,
                model=model,
                color="",
                status=STATUS_RUNNING,
            )
            team.add_member(teammate)
            storage.save_team(team)

            return ToolResult(
                success=True,
                data={
                    "team_name": team_name,
                    "agent_id": teammate.agent_id,
                    "name": name,
                    "agent_type": agent_type
                }
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class TeamLeaveTool(BaseTool):
    """离开团队"""

    name = "TeamLeave"
    description = "离开一个团队"
    input_schema = {
        "type": "object",
        "properties": {
            "team_name": {"type": "string", "description": "团队名称"},
            "name": {"type": "string", "description": "成员名称"}
        },
        "required": ["team_name", "name"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        team_name = args["team_name"]
        name = args["name"]

        try:
            storage = TeamStorage()
            team = storage.load_team(team_name)
            if team is None:
                return ToolResult(success=False, data=None, error=f"团队 {team_name} 不存在")

            member = team.get_member_by_name(name)
            if member is None:
                return ToolResult(success=False, data=None, error=f"成员 {name} 不存在")

            if member.agent_id == team.lead_agent_id:
                return ToolResult(success=False, data=None, error="团队负责人不能离开，请先转让权限")

            team.remove_member(member.agent_id)
            storage.save_team(team)

            return ToolResult(
                success=True,
                data={
                    "team_name": team_name,
                    "name": name,
                    "status": "left"
                }
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class TeamListTool(BaseTool):
    """列出所有团队"""

    name = "TeamList"
    description = "列出所有团队及其成员"
    input_schema = {
        "type": "object",
        "properties": {
            "team_name": {"type": "string", "description": "团队名称（可选，不指定则列出所有）"}
        }
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        team_name = args.get("team_name")

        try:
            storage = TeamStorage()

            if team_name:
                team = storage.load_team(team_name)
                if team is None:
                    return ToolResult(success=False, data=None, error=f"团队 {team_name} 不存在")

                return ToolResult(
                    success=True,
                    data={
                        "teams": [{
                            "name": team.name,
                            "lead_agent_id": team.lead_agent_id,
                            "members": [
                                {
                                    "name": m.name,
                                    "agent_id": m.agent_id,
                                    "agent_type": m.agent_type,
                                    "status": m.status
                                }
                                for m in team.members
                            ],
                            "created_at": team.created_at.isoformat()
                        }]
                    }
                )
            else:
                team_names = storage.list_teams()
                teams = []
                for tn in team_names:
                    t = storage.load_team(tn)
                    if t:
                        teams.append({
                            "name": t.name,
                            "lead_agent_id": t.lead_agent_id,
                            "members_count": len(t.members),
                            "created_at": t.created_at.isoformat()
                        })

                return ToolResult(
                    success=True,
                    data={"teams": teams}
                )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class TeamSendMessageTool(BaseTool):
    """向团队成员发送消息"""

    name = "TeamSendMessage"
    description = "向团队成员发送消息"
    input_schema = {
        "type": "object",
        "properties": {
            "team_name": {"type": "string", "description": "团队名称"},
            "to": {"type": "string", "description": "收件人名称（支持广播: *）"},
            "content": {"type": "string", "description": "消息内容"},
            "message_type": {"type": "string", "description": "消息类型 (text/broadcast)", "default": "text"}
        },
        "required": ["team_name", "to", "content"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        team_name = args["team_name"]
        to = args["to"]
        content = args["content"]
        message_type = args.get("message_type", "text")

        from_agent = context.get("agent_name", "unknown")

        try:
            mailbox = get_mailbox()

            if to == "*":
                count = mailbox.broadcast(
                    team_name=team_name,
                    from_agent=from_agent,
                    message=content,
                )
                return ToolResult(
                    success=True,
                    data={
                        "team_name": team_name,
                        "broadcast": True,
                        "recipients_count": count
                    }
                )
            else:
                success = mailbox.send(
                    team_name=team_name,
                    from_agent=from_agent,
                    to_agent=to,
                    message=content,
                    summary=content[:50] if len(content) > 50 else content,
                    message_type=message_type,
                )

                if success:
                    return ToolResult(
                        success=True,
                        data={
                            "team_name": team_name,
                            "to": to,
                            "sent": True
                        }
                    )
                else:
                    return ToolResult(success=False, data=None, error=f"发送失败，收件人 {to} 不存在")
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


# ============ VerifyPlanExecution 工具 ============

try:
    from plan import VerifyPlanExecutionTool as PlanVerifyTool
except ImportError:
    from scripts.plan import VerifyPlanExecutionTool as PlanVerifyTool


# ============ REPL 工具 ============

import shlex


class REPLTool(BaseTool):
    """交互式 REPL - 在当前会话中执行多轮命令"""

    name = "REPL"
    description = "启动交互式 REPL 会话，支持多轮命令输入"
    input_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令"},
            "language": {
                "type": "string",
                "enum": ["python", "bash", "node", "lua"],
                "description": "解释器类型"
            },
            "session_id": {"type": "string", "description": "会话 ID（可选）"}
        },
        "required": ["command"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        command = args["command"]
        language = args.get("language", "bash")
        session_id = args.get("session_id", "default")

        # 简单的 REPL 执行
        try:
            if language == "python":
                result = await self._exec_python(command)
            elif language == "node":
                result = await self._exec_node(command)
            elif language == "lua":
                result = await self._exec_lua(command)
            else:
                result = await self._exec_bash(command)

            return ToolResult(
                success=True,
                data={
                    "session_id": session_id,
                    "language": language,
                    "command": command,
                    "output": result["output"],
                    "exit_code": result["exit_code"],
                    "duration_ms": result.get("duration_ms", 0)
                }
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))

    async def _exec_python(self, code: str) -> dict:
        """执行 Python 代码"""
        import subprocess
        start = time.time()
        try:
            result = subprocess.run(
                ["python", "-c", code],
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "output": result.stdout + result.stderr,
                "exit_code": result.returncode,
                "duration_ms": int((time.time() - start) * 1000)
            }
        except subprocess.TimeoutExpired:
            return {"output": "Timeout: 30s limit exceeded", "exit_code": -1, "duration_ms": 30000}
        except Exception as e:
            return {"output": str(e), "exit_code": -1, "duration_ms": 0}

    async def _exec_node(self, code: str) -> dict:
        """执行 Node.js 代码"""
        import subprocess
        start = time.time()
        try:
            result = subprocess.run(
                ["node", "-e", code],
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "output": result.stdout + result.stderr,
                "exit_code": result.returncode,
                "duration_ms": int((time.time() - start) * 1000)
            }
        except subprocess.TimeoutExpired:
            return {"output": "Timeout: 30s limit exceeded", "exit_code": -1, "duration_ms": 30000}
        except Exception as e:
            return {"output": str(e), "exit_code": -1, "duration_ms": 0}

    async def _exec_lua(self, code: str) -> dict:
        """执行 Lua 代码"""
        import subprocess
        start = time.time()
        try:
            result = subprocess.run(
                ["lua", "-e", code],
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "output": result.stdout + result.stderr,
                "exit_code": result.returncode,
                "duration_ms": int((time.time() - start) * 1000)
            }
        except FileNotFoundError:
            return {"output": "Lua not installed", "exit_code": -1, "duration_ms": 0}
        except subprocess.TimeoutExpired:
            return {"output": "Timeout: 30s limit exceeded", "exit_code": -1, "duration_ms": 30000}
        except Exception as e:
            return {"output": str(e), "exit_code": -1, "duration_ms": 0}

    async def _exec_bash(self, command: str) -> dict:
        """执行 Bash 命令"""
        import subprocess
        start = time.time()
        shell = "bash" if not IS_WINDOWS else "cmd"
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
            return {
                "output": result.stdout + result.stderr,
                "exit_code": result.returncode,
                "duration_ms": int((time.time() - start) * 1000)
            }
        except subprocess.TimeoutExpired:
            return {"output": "Timeout: 60s limit exceeded", "exit_code": -1, "duration_ms": 60000}
        except Exception as e:
            return {"output": str(e), "exit_code": -1, "duration_ms": 0}


# ============ Config 工具 ============

# 运行时配置存储
RUNTIME_CONFIG: dict = {
    "log_level": "info",
    "max_tokens": 4096,
    "temperature": 0.7,
    "stream": True,
    "compact_threshold": 0.8,
    "auto_approve": False,
}


class ConfigGetTool(BaseTool):
    """获取配置项"""

    name = "ConfigGet"
    description = "获取运行时配置项的值"
    input_schema = {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "配置项名称"}
        },
        "required": ["key"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        key = args["key"]

        if key in RUNTIME_CONFIG:
            return ToolResult(
                success=True,
                data={"key": key, "value": RUNTIME_CONFIG[key]}
            )

        # 尝试从环境变量获取
        env_key = f"CLAUDE_{key.upper()}"
        if env_key in os.environ:
            return ToolResult(
                success=True,
                data={"key": key, "value": os.environ[env_key], "source": "environment"}
            )

        return ToolResult(success=False, data=None, error=f"配置项 '{key}' 不存在")


class ConfigSetTool(BaseTool):
    """设置配置项"""

    name = "ConfigSet"
    description = "设置运行时配置项的值"
    input_schema = {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "配置项名称"},
            "value": {"type": "string", "description": "配置值"}
        },
        "required": ["key", "value"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        key = args["key"]
        value = args["value"]

        # 类型转换
        old_value = RUNTIME_CONFIG.get(key)

        # 尝试转换为适当的类型
        if old_value is not None:
            if isinstance(old_value, bool):
                value = value.lower() in ("true", "1", "yes")
            elif isinstance(old_value, int):
                try:
                    value = int(value)
                except ValueError:
                    return ToolResult(success=False, data=None, error=f"'{value}' 不是有效的整数")
            elif isinstance(old_value, float):
                try:
                    value = float(value)
                except ValueError:
                    return ToolResult(success=False, data=None, error=f"'{value}' 不是有效的数字")

        RUNTIME_CONFIG[key] = value

        return ToolResult(
            success=True,
            data={"key": key, "value": value, "old_value": old_value}
        )


class ConfigListTool(BaseTool):
    """列出所有配置项"""

    name = "ConfigList"
    description = "列出所有运行时配置项"
    input_schema = {
        "type": "object",
        "properties": {}
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        return ToolResult(
            success=True,
            data={"config": RUNTIME_CONFIG.copy()}
        )


# ============ ToolSearch 工具 ============

class ToolSearchTool(BaseTool):
    """搜索已注册的工具"""

    name = "ToolSearch"
    description = "搜索已注册的工具，支持按名称或描述搜索"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "type": {
                "type": "string",
                "enum": ["name", "description", "all"],
                "default": "all",
                "description": "搜索类型"
            }
        },
        "required": ["query"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        query = args["query"].lower()
        search_type = args.get("type", "all")

        try:
            from tool import get_registry
        except ImportError:
            from scripts.tool import get_registry

        registry = get_registry()
        results = []

        for tool_def in registry.all():
            if search_type == "name":
                if query in tool_def.name.lower():
                    results.append({
                        "name": tool_def.name,
                        "description": tool_def.description,
                        "input_schema": tool_def.input_schema
                    })
            elif search_type == "description":
                if query in tool_def.description.lower():
                    results.append({
                        "name": tool_def.name,
                        "description": tool_def.description,
                        "input_schema": tool_def.input_schema
                    })
            else:
                # all: 搜索名称或描述
                if query in tool_def.name.lower() or query in tool_def.description.lower():
                    results.append({
                        "name": tool_def.name,
                        "description": tool_def.description,
                        "input_schema": tool_def.input_schema
                    })

        return ToolResult(
            success=True,
            data={
                "query": query,
                "count": len(results),
                "tools": results
            }
        )


class ToolListAllTool(BaseTool):
    """列出所有已注册的工具"""

    name = "ToolListAll"
    description = "列出所有已注册的工具及其详细信息"
    input_schema = {
        "type": "object",
        "properties": {
            "include_disabled": {"type": "boolean", "description": "是否包含已禁用的工具", "default": False}
        }
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        include_disabled = args.get("include_disabled", False)

        try:
            from tool import get_registry
        except ImportError:
            from scripts.tool import get_registry

        registry = get_registry()
        tools = []

        for tool_def in registry.all():
            tools.append({
                "name": tool_def.name,
                "description": tool_def.description,
                "input_schema": tool_def.input_schema,
                "aliases": tool_def.aliases
            })

        return ToolResult(
            success=True,
            data={
                "count": len(tools),
                "tools": tools
            }
        )


# ============ Monitor 工具 ============

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None  # type: ignore
    HAS_PSUTIL = False


class MonitorCPUTool(BaseTool):
    """监控 CPU 使用率"""

    name = "MonitorCPU"
    description = "获取 CPU 使用率信息"
    input_schema = {
        "type": "object",
        "properties": {
            "interval": {"type": "number", "description": "采样间隔（秒）", "default": 1.0}
        }
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        if not HAS_PSUTIL:
            return ToolResult(
                success=False, data=None,
                error="psutil 库未安装: pip install psutil"
            )

        interval = args.get("interval", 1.0)

        cpu_percent = psutil.cpu_percent(interval=interval, percpu=True)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()

        return ToolResult(
            success=True,
            data={
                "cpu_percent": cpu_percent,
                "cpu_percent_avg": sum(cpu_percent) / len(cpu_percent),
                "cpu_count": cpu_count,
                "cpu_freq_current": cpu_freq.current if cpu_freq else None,
                "cpu_freq_max": cpu_freq.max if cpu_freq else None
            }
        )


class MonitorMemoryTool(BaseTool):
    """监控内存使用"""

    name = "MonitorMemory"
    description = "获取内存使用信息"
    input_schema = {
        "type": "object",
        "properties": {}
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        if not HAS_PSUTIL:
            return ToolResult(
                success=False, data=None,
                error="psutil 库未安装: pip install psutil"
            )

        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        return ToolResult(
            success=True,
            data={
                "total": mem.total,
                "available": mem.available,
                "used": mem.used,
                "percent": mem.percent,
                "swap_total": swap.total,
                "swap_used": swap.used,
                "swap_percent": swap.percent
            }
        )


class MonitorDiskTool(BaseTool):
    """监控磁盘使用"""

    name = "MonitorDisk"
    description = "获取磁盘使用信息"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "指定路径（可选）"}
        }
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        if not HAS_PSUTIL:
            return ToolResult(
                success=False, data=None,
                error="psutil 库未安装: pip install psutil"
            )

        path = args.get("path", "/")

        try:
            disk = psutil.disk_usage(path)
            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": disk.percent
                }
            )
        except FileNotFoundError:
            return ToolResult(success=False, data=None, error=f"路径 '{path}' 不存在")


class MonitorProcessTool(BaseTool):
    """监控进程信息"""

    name = "MonitorProcess"
    description = "获取进程信息"
    input_schema = {
        "type": "object",
        "properties": {
            "pid": {"type": "integer", "description": "进程 ID（当前进程: 0）"},
            "top": {"type": "integer", "description": "获取 CPU 最高的 N 个进程"}
        }
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        if not HAS_PSUTIL:
            return ToolResult(
                success=False, data=None,
                error="psutil 库未安装: pip install psutil"
            )

        pid = args.get("pid", 0)
        top = args.get("top", 0)

        if top > 0:
            # 返回 CPU 最高的进程
            processes = []
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    pinfo = p.info
                    pinfo['cpu_percent'] = p.cpu_percent(interval=0.1)
                    pinfo['memory_percent'] = p.memory_percent()
                    processes.append(pinfo)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            processes.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
            return ToolResult(
                success=True,
                data={
                    "processes": processes[:top],
                    "count": top
                }
            )

        if pid == 0:
            # 返回当前进程
            current = psutil.Process()
            return ToolResult(
                success=True,
                data={
                    "pid": current.pid,
                    "name": current.name(),
                    "cpu_percent": current.cpu_percent(),
                    "memory_percent": current.memory_percent(),
                    "memory_info": current.memory_info()._asdict(),
                    "num_threads": current.num_threads(),
                    "create_time": current.create_time()
                }
            )

        # 获取指定进程
        try:
            p = psutil.Process(pid)
            return ToolResult(
                success=True,
                data={
                    "pid": p.pid,
                    "name": p.name(),
                    "cpu_percent": p.cpu_percent(),
                    "memory_percent": p.memory_percent(),
                    "memory_info": p.memory_info()._asdict(),
                    "num_threads": p.num_threads(),
                    "status": p.status(),
                    "create_time": p.create_time()
                }
            )
        except psutil.NoSuchProcess:
            return ToolResult(success=False, data=None, error=f"进程 {pid} 不存在")


class MonitorSystemTool(BaseTool):
    """综合系统监控"""

    name = "MonitorSystem"
    description = "获取综合系统监控信息（CPU、内存、磁盘）"
    input_schema = {
        "type": "object",
        "properties": {}
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        if not HAS_PSUTIL:
            return ToolResult(
                success=False, data=None,
                error="psutil 库未安装: pip install psutil"
            )

        cpu = psutil.cpu_percent(interval=0.5, percpu=True)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        boot_time = psutil.boot_time()
        uptime = time.time() - boot_time

        return ToolResult(
            success=True,
            data={
                "cpu": {
                    "percent_avg": sum(cpu) / len(cpu),
                    "percent_per_core": cpu,
                    "count": len(cpu)
                },
                "memory": {
                    "total": mem.total,
                    "used": mem.used,
                    "available": mem.available,
                    "percent": mem.percent
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": disk.percent
                },
                "uptime_seconds": uptime,
                "platform": platform.system(),
                "platform_release": platform.release()
            }
        )


# ============ SSH Daemon 工具 ============

try:
    from .sshd import SSHDaemon, SSHDConfig, get_ssh_daemon
except ImportError:
    try:
        from sshd import SSHDaemon, SSHDConfig, get_ssh_daemon
    except ImportError:
        SSHDaemon = None
        SSHDConfig = None
        get_ssh_daemon = None


class SSHDaemonStartTool(BaseTool):
    """启动 SSH 守护进程"""

    name = "SSHDaemonStart"
    description = "启动 SSH 守护进程，允许通过 SSH 远程连接到 Agent"
    input_schema = {
        "type": "object",
        "properties": {
            "host": {"type": "string", "description": "监听地址", "default": "0.0.0.0"},
            "port": {"type": "integer", "description": "监听端口", "default": 2222},
            "username": {"type": "string", "description": "用户名", "default": "claude"},
            "password": {"type": "string", "description": "密码（可选）"}
        }
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        if SSHDaemon is None:
            return ToolResult(
                success=False, data=None,
                error="sshd 模块不可用，请安装 paramiko: pip install paramiko"
            )

        try:
            config = SSHDConfig(
                host=args.get("host", "0.0.0.0"),
                port=args.get("port", 2222),
                username=args.get("username", "claude"),
                password=args.get("password"),
            )

            daemon = get_ssh_daemon(config)
            await daemon.start()

            return ToolResult(
                success=True,
                data={
                    "status": "started",
                    "host": config.host,
                    "port": config.port,
                    "mode": "ssh" if daemon._use_ssh_mode else "tcp"
                }
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class SSHDaemonStopTool(BaseTool):
    """停止 SSH 守护进程"""

    name = "SSHDaemonStop"
    description = "停止 SSH 守护进程"
    input_schema = {
        "type": "object",
        "properties": {}
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        if SSHDaemon is None:
            return ToolResult(
                success=False, data=None,
                error="sshd 模块不可用"
            )

        try:
            from .sshd import stop_ssh_daemon
        except ImportError:
            try:
                from sshd import stop_ssh_daemon
            except ImportError:
                return ToolResult(success=False, data=None, error="sshd 模块不可用")

        await stop_ssh_daemon()

        return ToolResult(
            success=True,
            data={"status": "stopped"}
        )


class SSHDaemonStatusTool(BaseTool):
    """获取 SSH 守护进程状态"""

    name = "SSHDaemonStatus"
    description = "获取 SSH 守护进程的运行状态"
    input_schema = {
        "type": "object",
        "properties": {}
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        if get_ssh_daemon is None:
            return ToolResult(
                success=False, data=None,
                error="sshd 模块不可用"
            )

        try:
            daemon = get_ssh_daemon()

            return ToolResult(
                success=True,
                data={
                    "running": daemon._running,
                    "host": daemon.config.host,
                    "port": daemon.config.port,
                    "mode": "ssh" if hasattr(daemon, '_use_ssh_mode') and daemon._use_ssh_mode else "tcp"
                }
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


# ============ 内置工具注册 ============

def register_advanced_tools():
    """注册所有高级工具"""
    try:
        from tool import get_registry
    except ImportError:
        from scripts.tool import get_registry

    tools = [
        TaskCreateTool(),
        TaskGetTool(),
        TaskListTool(),
        TaskUpdateTool(),
        TaskOutputTool(),
        TaskStopTool(),
        WebFetchTool(),
        WebSearchTool(),
        AgentTool(),
        TodoWriteTool(),
        EnterPlanModeTool(),
        ExitPlanModeTool(),
        PlanStepApproveTool(),
        PlanStepRejectTool(),
        WorktreeCreateTool(),
        WorktreeRemoveTool(),
        WorktreeListTool(),
        TeamCreateTool(),
        TeamJoinTool(),
        TeamLeaveTool(),
        TeamListTool(),
        TeamSendMessageTool(),
        PlanVerifyTool(),
        # Phase 3 新工具
        REPLTool(),
        ConfigGetTool(),
        ConfigSetTool(),
        ConfigListTool(),
        ToolSearchTool(),
        ToolListAllTool(),
        MonitorCPUTool(),
        MonitorMemoryTool(),
        MonitorDiskTool(),
        MonitorProcessTool(),
        MonitorSystemTool(),
        # SSH Daemon 工具
        SSHDaemonStartTool(),
        SSHDaemonStopTool(),
        SSHDaemonStatusTool(),
    ]

    for tool in tools:
        get_registry().register(tool)


# 自动注册
register_advanced_tools()
