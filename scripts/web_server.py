"""
Agent HTTP 服务层 - 后台持久运行
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

# 把 scripts 的父目录加入路径，让它可以作为包导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from .agent import Agent, AgentConfig, create_agent
    from .config import get_config, update_config, get_config_manager
    from .lsp_tool import (
        LSPDefinitionTool,
        LSPHoverTool,
        LSPInitTool,
        LSPReferencesTool,
        LSPSymbolsTool,
        LSPTypeDefinitionTool,
    )
    from .permission import PermissionEngine
    from .tools import BashTool, EditTool, GlobTool, GrepTool, ReadTool, WriteTool
    from .tools_advanced import ToolListAllTool
except ImportError:
    from agent import Agent, AgentConfig, create_agent
    from config import get_config, update_config, get_config_manager
    from lsp_tool import (
        LSPDefinitionTool,
        LSPHoverTool,
        LSPInitTool,
        LSPReferencesTool,
        LSPSymbolsTool,
        LSPTypeDefinitionTool,
    )
    from permission import PermissionEngine
    from tools import BashTool, EditTool, GlobTool, GrepTool, ReadTool, WriteTool
    from tools_advanced import ToolListAllTool

# ============ 统计和状态 ============

@dataclass
class UsageRecord:
    timestamp: str
    input_tokens: int
    output_tokens: int
    model: str
    duration_ms: int
    session_id: str


@dataclass
class AgentStats:
    status: str = "idle"  # idle | running
    total_conversations: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0  # 累计费用（美元）
    history: list = field(default_factory=list)
    usage_records: list = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # MiniMax-M2.7 pricing (per 1M tokens)
    INPUT_PRICE_PER_M = 0.30
    OUTPUT_PRICE_PER_M = 1.20

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """计算费用（美元）"""
        input_cost = (input_tokens / 1_000_000) * self.INPUT_PRICE_PER_M
        output_cost = (output_tokens / 1_000_000) * self.OUTPUT_PRICE_PER_M
        return input_cost + output_cost

    def record(self, session_id: str, input_tokens: int, output_tokens: int, model: str, duration_ms: int):
        cost = self._calculate_cost(input_tokens, output_tokens)
        with self._lock:
            record = UsageRecord(
                timestamp=datetime.now().isoformat(),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
                duration_ms=duration_ms,
                session_id=session_id
            )
            self.usage_records.append(record)
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_cost += cost
            self.total_conversations += 1

    def get_usage(self, from_time: datetime = None, to_time: datetime = None) -> dict:
        with self._lock:
            records = self.usage_records
            if from_time:
                # 统一为 naive datetime 比较
                from_t = from_time.replace(tzinfo=None)
                records = [r for r in records if datetime.fromisoformat(r.timestamp).replace(tzinfo=None) >= from_t]
            if to_time:
                to_t = to_time.replace(tzinfo=None)
                records = [r for r in records if datetime.fromisoformat(r.timestamp).replace(tzinfo=None) <= to_t]

            total_in = sum(r.input_tokens for r in records)
            total_out = sum(r.output_tokens for r in records)
            total_cost = self._calculate_cost(total_in, total_out)
            return {
                "records": len(records),
                "input_tokens": total_in,
                "output_tokens": total_out,
                "total_tokens": total_in + total_out,
                "total_cost": total_cost,
                "conversations": len(records)
            }

    def get_history(self, limit: int = 50) -> list:
        with self._lock:
            return self.history[-limit:]


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """支持多线程的 HTTP 服务器"""
    daemon_threads = True
    allow_reuse_address = True


stats = AgentStats()

# ============ 全局 Agent 实例 ============

_agent: Agent = None
_agent_lock = threading.Lock()


def get_agent() -> Agent:
    global _agent
    with _agent_lock:
        if _agent is None:
            tools = [
                ReadTool(),
                BashTool(),
                WriteTool(),
                GrepTool(),
                GlobTool(),
                EditTool(),
                # LSP 工具
                LSPInitTool(),
                LSPDefinitionTool(),
                LSPHoverTool(),
                LSPTypeDefinitionTool(),
                LSPReferencesTool(),
                LSPSymbolsTool(),
            ]
            # 从当前配置创建 Agent
            cfg = get_config()
            config = AgentConfig(
                api_key=cfg.api_key,
                api_url=cfg.api_url,
                model=cfg.model,
                temperature=cfg.temperature,
                max_turns=cfg.max_turns,
                timeout=cfg.timeout,
                parallel_tool_calls=cfg.parallel_tool_calls,
                multi_agent_enabled=cfg.multi_agent_enabled,
            )
            _agent = create_agent(tools=tools, permission_engine=PermissionEngine.build_default_engine(), config=config)
        return _agent


# ============ Chat 会话管理 ============

@dataclass
class ChatSession:
    id: str
    messages: list = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    last_message: str = ""
    token_count: int = 0
    allowed_tools: list[str] | None = None  # None = all tools allowed


sessions: dict[str, ChatSession] = {}
_session_lock = threading.Lock()
_agents: dict[str, Agent] = {}  # per-session Agent instances
_permission_engines: dict[str, PermissionEngine] = {}  # per-session Permission engines


def _recreate_all_agents():
    """当配置变更时，重新创建所有 Agent 实例"""
    global _agent, _agents, _permission_engines
    with _session_lock:
        # 重建全局 agent
        _agent = None
        for session_id in list(_agents.keys()):
            session = sessions.get(session_id)
            allowed_tools = session.allowed_tools if session else None
            engine = _permission_engines.get(session_id)
            if engine is None:
                engine = PermissionEngine.build_default_engine()
                _permission_engines[session_id] = engine
            _agents[session_id] = _create_agent_for_session(session_id, allowed_tools, engine)
    print("[Config] All agents recreated with new config")


def get_or_create_session(session_id: str, allowed_tools: list[str] | None = None) -> ChatSession:
    global _agents, _permission_engines
    with _session_lock:
        if session_id not in sessions:
            now = datetime.now().isoformat()
            sessions[session_id] = ChatSession(
                id=session_id,
                created_at=now,
                updated_at=now,
                allowed_tools=allowed_tools
            )
            # 为新 session 创建独立的 PermissionEngine 和 Agent 实例
            engine = PermissionEngine.build_default_engine()
            _permission_engines[session_id] = engine
            _agents[session_id] = _create_agent_for_session(session_id, allowed_tools, engine)
        return sessions[session_id]


def _create_agent_for_session(session_id: str, allowed_tools: list[str] | None = None, permission_engine: PermissionEngine | None = None) -> Agent:
    """为每个 session 创建独立的 Agent 实例"""
    all_tools = [
        ("Read", ReadTool()),
        ("Bash", BashTool()),
        ("Write", WriteTool()),
        ("Grep", GrepTool()),
        ("Glob", GlobTool()),
        ("Edit", EditTool()),
        ("LSPInit", LSPInitTool()),
        ("LSPDefinition", LSPDefinitionTool()),
        ("LSPHover", LSPHoverTool()),
        ("LSPTypeDefinition", LSPTypeDefinitionTool()),
        ("LSPReferences", LSPReferencesTool()),
        ("LSPSymbols", LSPSymbolsTool()),
        ("ToolListAll", ToolListAllTool()),
    ]

    # 根据 allowed_tools 过滤工具
    if allowed_tools is not None:
        tools = [tool for name, tool in all_tools if name in allowed_tools]
    else:
        tools = [tool for _, tool in all_tools]

    # 使用提供的 permission engine 或创建默认的
    engine = permission_engine or PermissionEngine.build_default_engine()

    # 从当前配置创建 Agent
    cfg = get_config()
    config = AgentConfig(
        api_key=cfg.api_key,
        api_url=cfg.api_url,
        model=cfg.model,
        temperature=cfg.temperature,
        max_turns=cfg.max_turns,
        timeout=cfg.timeout,
        parallel_tool_calls=cfg.parallel_tool_calls,
        multi_agent_enabled=cfg.multi_agent_enabled,
        allowed_tools=allowed_tools,  # 修复：传递 allowed_tools 到 AgentConfig
    )

    try:
        from memory.session_memory import SessionMemory
        from memory.memory_store import MemoryStore
        store = MemoryStore()
        session_memory = SessionMemory(session_id=session_id, store=store)
        agent = create_agent(tools=tools, permission_engine=engine, config=config)
        agent.set_session_memory(session_memory)
        return agent
    except ImportError:
        return create_agent(tools=tools, permission_engine=engine, config=config)


def get_agent_for_session(session_id: str) -> Agent:
    """获取指定 session 的 Agent 实例"""
    with _session_lock:
        if session_id not in _agents:
            # Fallback：使用 session 中保存的 allowed_tools
            allowed = sessions.get(session_id).allowed_tools if session_id in sessions else None
            _agents[session_id] = _create_agent_for_session(session_id, allowed)
        return _agents[session_id]


# ============ HTTP Handler ============

class AgentHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理"""

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def parse_body(self) -> dict:
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                body = self.rfile.read(content_length)
                return json.loads(body.decode("utf-8"))
        except Exception as e:
            print(f"[parse_body] error: {e}, body_len={content_length}", flush=True)
        return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/status":
            self.send_json({"status": stats.status, "conversations": stats.total_conversations})

        elif path == "/api/stats":
            self.send_json({
                "total_input_tokens": stats.total_input_tokens,
                "total_output_tokens": stats.total_output_tokens,
                "total_conversations": stats.total_conversations,
                "total_cost": stats.total_cost,
                "usage": stats.get_usage()
            })

        elif path == "/api/config":
            # 获取当前配置（隐藏 api_key）
            cfg = get_config()
            self.send_json({"config": cfg.to_public_dict()})

        elif path == "/api/usage":
            from_t = query.get("from", [None])[0]
            to_t = query.get("to", [None])[0]
            from_dt = datetime.fromisoformat(from_t) if from_t else None
            to_dt = datetime.fromisoformat(to_t) if to_t else None
            self.send_json(stats.get_usage(from_dt, to_dt))

        elif path == "/api/history":
            limit = int(query.get("limit", ["50"])[0])
            self.send_json({"history": stats.get_history(limit)})

        elif path == "/api/sessions":
            with _session_lock:
                self.send_json({
                    "sessions": [
                        {
                            "id": s.id,
                            "created_at": s.created_at,
                            "updated_at": s.updated_at,
                            "last_message": s.last_message,
                            "message_count": len(s.messages)
                        }
                        for s in sessions.values()
                    ]
                })

        elif path.startswith("/api/session/") and path.endswith("/memory"):
            # 获取指定 session 的 memory 详情
            # 格式: /api/session/{session_id}/memory
            parts = path.split("/")
            if len(parts) >= 4:
                session_id = parts[3]
                try:
                    from memory.session_memory import SessionMemory
                    from memory.memory_store import MemoryStore
                    store = MemoryStore()
                    session_memory = SessionMemory.load_from_store(session_id, store)
                    if session_memory:
                        self.send_json({"session_id": session_id, "memory": session_memory.to_dict()})
                    else:
                        self.send_json({"session_id": session_id, "memory": None, "error": "No memory found"})
                except ImportError:
                    self.send_json({"error": "Memory module not available"}, 500)
            else:
                self.send_json({"error": "Invalid path"}, 400)

        elif path == "/api/tools":
            # 返回可用工具列表
            tools_data = [
                {"name": "Read", "icon": "📖", "category": "文件", "description": "读取文件内容", "params": [{"name": "file_path", "type": "string", "desc": "文件路径"}, {"name": "max_lines", "type": "number", "desc": "最大行数"}]},
                {"name": "Write", "icon": "✏️", "category": "文件", "description": "创建或覆盖文件内容", "params": [{"name": "file_path", "type": "string", "desc": "文件路径"}, {"name": "content", "type": "string", "desc": "文件内容"}]},
                {"name": "Edit", "icon": "🔧", "category": "文件", "description": "精确替换文件中的文本", "params": [{"name": "file_path", "type": "string", "desc": "文件路径"}, {"name": "old_string", "type": "string", "desc": "原文本"}, {"name": "new_string", "type": "string", "desc": "新文本"}]},
                {"name": "Bash", "icon": "💻", "category": "系统", "description": "执行Shell命令", "params": [{"name": "command", "type": "string", "desc": "Shell命令"}, {"name": "timeout", "type": "number", "desc": "超时时间(秒)"}]},
                {"name": "Grep", "icon": "🔍", "category": "搜索", "description": "在文件中搜索文本", "params": [{"name": "pattern", "type": "string", "desc": "正则表达式"}, {"name": "path", "type": "string", "desc": "搜索路径"}, {"name": "recursive", "type": "boolean", "desc": "递归搜索"}]},
                {"name": "Glob", "icon": "📁", "category": "搜索", "description": "按模式查找文件", "params": [{"name": "pattern", "type": "string", "desc": "Glob模式，如 **/*.py"}]},
                {"name": "WebSearch", "icon": "🌐", "category": "网络", "description": "搜索网络信息", "params": [{"name": "query", "type": "string", "desc": "搜索关键词"}]},
                {"name": "WebFetch", "icon": "📄", "category": "网络", "description": "获取网页内容", "params": [{"name": "url", "type": "string", "desc": "网页URL"}]},
                {"name": "TaskCreate", "icon": "✅", "category": "任务", "description": "创建任务", "params": [{"name": "title", "type": "string", "desc": "任务标题"}, {"name": "description", "type": "string", "desc": "任务描述"}]},
                {"name": "Skill", "icon": "🎯", "category": "技能", "description": "使用内置技能", "params": [{"name": "name", "type": "string", "desc": "技能名称"}, {"name": "args", "type": "string", "desc": "技能参数"}]},
                {"name": "EnterPlanMode", "icon": "📋", "category": "模式", "description": "进入计划模式", "params": []},
                {"name": "ExitPlanMode", "icon": "✅", "category": "模式", "description": "退出计划模式", "params": []},
                {"name": "Agent", "icon": "🤖", "category": "Agent", "description": "启动子Agent执行任务", "params": [{"name": "prompt", "type": "string", "desc": "Agent指令"}]},
                {"name": "LSP", "icon": "💎", "category": "代码", "description": "语言服务器协议操作", "params": [{"name": "command", "type": "string", "desc": "LSP命令"}]},
            ]
            self.send_json({"tools": tools_data})

        elif path == "/":
            self.send_file("web/index.html")

        elif path.startswith("/static/"):
            filename = path[8:]
            self.send_file(f"web/{filename}")

        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/config":
            # 更新配置
            body = self.parse_body()
            config_data = body.get("config", {})
            updated = update_config(config_data)
            # 保存到文件
            get_config_manager().save(updated)
            self.send_json({"success": True, "config": updated.to_public_dict()})
            return

        if path == "/api/chat":
            body = self.parse_body()
            message = body.get("message", "")
            session_id = body.get("session_id", "default")
            model = body.get("model", "MiniMax-M2.7")
            stream = body.get("stream", False)
            allowed_tools = body.get("allowed_tools")  # 可选，指定可用工具列表

            print(f"[POST /api/chat] stream={stream}, msg={message[:30]!r}", flush=True)

            if not message:
                return self.send_json({"error": "message is required"}, 400)

            # 获取/创建 session（首次可指定 allowed_tools）
            session = get_or_create_session(session_id, allowed_tools)
            session.last_message = message[:100]
            session.updated_at = datetime.now().isoformat()

            # 流式模式：SSE
            if stream:
                self._do_sse_chat(message, session_id, model, session)
                # 等待 SSE 完成
                self._sse_thread.join()
                return

            # 非流式：后台执行，返回最终结果
            stats.status = "running"

            def run_async():
                try:
                    agent = get_agent_for_session(session_id)
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    t0 = time.time()
                    response = loop.run_until_complete(agent.run(message))
                    duration_ms = int((time.time() - t0) * 1000)

                    input_tokens = len(message) // 4
                    output_tokens = len(response) // 4

                    stats.record(session_id, input_tokens, output_tokens, model, duration_ms)

                    with stats._lock:
                        stats.history.append({
                            "timestamp": datetime.now().isoformat(),
                            "message": message[:100],
                            "response": response[:200],
                            "session_id": session_id,
                            "tokens": input_tokens + output_tokens,
                            "duration_ms": duration_ms
                        })

                    with _session_lock:
                        session.messages.append({
                            "role": "user",
                            "content": message,
                            "timestamp": datetime.now().isoformat()
                        })
                        session.messages.append({
                            "role": "assistant",
                            "content": response,
                            "timestamp": datetime.now().isoformat(),
                            "tokens": input_tokens + output_tokens
                        })
                        session.token_count += input_tokens + output_tokens

                    stats.status = "idle"

                except Exception as e:
                    stats.status = "idle"
                    print(f"[Agent] Error: {e}", file=sys.stderr)

            thread = threading.Thread(target=run_async)
            thread.start()

            self.send_json({"status": "processing", "session_id": session_id})

        elif path == "/api/chat/stream":
            # 专用 SSE 端点：GET 请求建立 SSE 连接
            body = self.parse_body()
            self._do_sse_chat("", "default", "MiniMax-M2.7", None)

        elif path == "/api/session":
            body = self.parse_body()
            session_id = body.get("session_id", "default")
            session = get_or_create_session(session_id)
            self.send_json({
                "session": {
                    "id": session.id,
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                    "messages": session.messages,
                    "allowed_tools": session.allowed_tools
                }
            })

        elif path == "/api/session/tools":
            # 更新 session 的可用工具或权限规则
            body = self.parse_body()
            session_id = body.get("session_id", "default")
            allowed_tools = body.get("allowed_tools")  # null 表示不改变
            tool_rules = body.get("tool_rules")  # 可选，额外的工具规则列表

            # 确保 session 存在
            get_or_create_session(session_id)
            session = sessions[session_id]

            # 如果提供了 allowed_tools，更新并重建 agent
            if allowed_tools is not None:
                session.allowed_tools = allowed_tools
                session.updated_at = datetime.now().isoformat()
                _agents[session_id] = _create_agent_for_session(session_id, allowed_tools, _permission_engines.get(session_id))

            # 如果提供了 tool_rules，添加到 permission engine
            if tool_rules and isinstance(tool_rules, list):
                engine = _permission_engines.get(session_id)
                if engine:
                    for rule in tool_rules:
                        # 规则格式: "ToolName(*):allow" 或 "ToolName(*):deny"
                        if rule.endswith(":allow"):
                            pattern = rule[:-6]
                            engine.allow(pattern, "用户授权")
                        elif rule.endswith(":deny"):
                            pattern = rule[:-5]
                            engine.deny(pattern, "用户拒绝")

            self.send_json({
                "success": True,
                "session_id": session_id,
                "allowed_tools": session.allowed_tools
            })

        else:
            self.send_json({"error": "not found"}, 404)

    def send_file(self, filepath):
        """发送静态文件"""
        try:
            # web/ 目录在 scripts/ 的上一级
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            full_path = os.path.join(base_dir, filepath)
            with open(full_path, "rb") as f:
                content = f.read()
            ext = filepath.split(".")[-1]
            content_type = {"html": "text/html", "css": "text/css", "js": "application/javascript", "png": "image/png", "jpg": "image/jpeg"}.get(ext, "text/plain")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_json({"error": "file not found"}, 404)

    def log_message(self, format, *args):
        print(f"[HTTP] {args[0]}", file=sys.stderr)

    def _do_sse_chat(self, message: str, session_id: str, model: str, session: ChatSession):
        """
        SSE 流式聊天
        """
        # 发送 SSE headers
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        
        # 确保 socket 不被关闭
        self.request.setblocking(True)

        # 保存 wfile 引用
        wfile = self.wfile

        # 如果非空，先发送 user message 到 session
        if session and message:
            with _session_lock:
                session.messages.append({
                    "role": "user",
                    "content": message,
                    "timestamp": datetime.now().isoformat()
                })

        # 使用锁保护 agent 调用
        def run_and_send():
            import traceback
            loop = None
            try:
                agent = get_agent_for_session(session_id)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                client_disconnected = False

                async def run_stream_async():
                    agen = agent.run_stream(message)
                    accumulated_text = ""
                    accumulated_tool_output = {}
                    accumulated_usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
                    
                    def safe_write(msg):
                        nonlocal client_disconnected
                        if client_disconnected:
                            return False
                        try:
                            if isinstance(msg, str):
                                wfile.write(msg.encode("utf-8"))
                            else:
                                wfile.write(msg)
                            wfile.flush()
                            return True
                        except OSError:
                            client_disconnected = True
                            return False
                        except BrokenPipeError:
                            client_disconnected = True
                            return False
                        except ConnectionResetError:
                            client_disconnected = True
                            return False
                        except Exception:
                            client_disconnected = True
                            return False
                    
                    try:
                        async for event in agen:
                            if client_disconnected:
                                break
                            # 累积 usage 信息
                            if event.usage:
                                accumulated_usage["input_tokens"] += event.usage.get("input_tokens", 0)
                                accumulated_usage["output_tokens"] += event.usage.get("output_tokens", 0)
                                accumulated_usage["total_tokens"] += event.usage.get("total_tokens", 0)
                            event_data = {
                                "type": event.type,
                                "content": event.content,
                                "tool": event.tool,
                                "args": event.args,
                                "success": event.success,
                                "data": event.data,
                                "recovered": event.recovered,
                                "warning": event.warning,
                                "error": event.error,
                                "usage": event.usage,
                                "auth_required": event.auth_required,
                            }
                            sse_msg = f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                            print(f"[SSE] Sending event: {event.type}", flush=True)
                            if not safe_write(sse_msg):
                                print(f"[SSE] safe_write failed, breaking", flush=True)
                                break
                            if event.type == "text":
                                accumulated_text = event.content
                            elif event.type in ("tool_result", "tool_error"):
                                accumulated_tool_output[event.tool] = event.content
                                if event.type == "tool_error":
                                    print(f"[SSE] tool_error: {event.tool} - {event.error}", flush=True)
                    finally:
                        agen.aclose()

                    # 记录 token 使用量
                    if accumulated_usage["total_tokens"] > 0:
                        stats.record(
                            session_id=session_id,
                            input_tokens=accumulated_usage["input_tokens"],
                            output_tokens=accumulated_usage["output_tokens"],
                            model=model,
                            duration_ms=0
                        )
                        print(f"[SSE] Recorded usage: {accumulated_usage}", flush=True)

                    print(f"[SSE] Sending DONE event", flush=True)
                    if not client_disconnected:
                        safe_write(b"data: [DONE]\n\n")
                        try:
                            wfile.close()
                        except Exception as e:
                            print(f"[SSE] wfile.close() error: {e}", flush=True)
                    print(f"[SSE] Stream complete", flush=True)

                    if session and (accumulated_text or accumulated_tool_output):
                        with _session_lock:
                            session.messages.append({
                                "role": "assistant",
                                "content": accumulated_text or json.dumps(accumulated_tool_output, ensure_ascii=False),
                                "timestamp": datetime.now().isoformat(),
                                "tool_output": accumulated_tool_output,
                            })
                        
                        # 更新 stats.history（流式模式）
                        user_msg = next((m["content"] for m in session.messages if m.get("role") == "user"), "")
                        with stats._lock:
                            stats.history.append({
                                "timestamp": datetime.now().isoformat(),
                                "message": user_msg[:100] if user_msg else "",
                                "response": accumulated_text[:200] if accumulated_text else json.dumps(accumulated_tool_output, ensure_ascii=False)[:200],
                                "session_id": session_id,
                                "tokens": accumulated_usage.get("total_tokens", 0),
                                "duration_ms": 0
                            })

                loop.run_until_complete(run_stream_async())

            except Exception as e:
                print(f"[SSE] Error: {e}\n{traceback.format_exc()}", flush=True)
                import traceback
                traceback.print_exc()
            finally:
                print(f"[SSE] finally block, cleaning up", flush=True)
                if loop:
                    try:
                        pending = asyncio.all_tasks(loop)
                        for task in pending:
                            task.cancel()
                        if pending:
                            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    except Exception:
                        pass
                    loop.close()
                stats.status = "idle"

        thread = threading.Thread(target=run_and_send)
        thread.start()
        self._sse_thread = thread


def start_server(port=18780):
    """启动 HTTP 服务"""
    # 注册配置变更回调
    get_config_manager().on_changed(lambda cfg: _recreate_all_agents())
    
    server = ThreadedHTTPServer(("0.0.0.0", port), AgentHandler)
    print(f"[HTTP] Agent Web UI: http://localhost:{port}")
    print(f"       API: http://localhost:{port}/api/status")
    sys.stdout.flush()
    server.serve_forever()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Claude Agent Web Server")
    parser.add_argument("--port", type=int, default=18780, help="Port to listen on")
    args = parser.parse_args()
    start_server(args.port)
