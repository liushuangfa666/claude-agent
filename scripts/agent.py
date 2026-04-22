"""
Agent 核心循环 - 参考 Claude Code 的 query.ts + QueryEngine.ts 设计

核心流程：
1. 构建 system prompt（工具 + 上下文）
2. 发送消息给 LLM
3. 解析 LLM 响应（文本 or 工具调用）
4. 执行工具前先做权限检查
5. 工具结果反馈给 LLM
6. 循环直到任务完成

流式输出（Edit → 错误恢复 → 流式输出）:
- Agent.run_stream() 是 async generator，逐条 yield 执行事件
- 事件类型：
  - {"type": "thinking", "content": "..."}          # LLM 思考中
  - {"type": "tool_start", "tool": "Edit", "args": {...}}  # 工具开始执行
  - {"type": "tool_progress", "content": "搜索文本...", "recovered": false}  # 执行进度
  - {"type": "tool_recovered", "warning": "自动去除了首尾空白"}  # 错误恢复警告
  - {"type": "tool_result", "success": true, "data": {...}}    # 工具结果
  - {"type": "tool_error", "error": "..."}          # 工具执行失败
  - {"type": "text", "content": "..."}              # LLM 文本回复
  - {"type": "done", "final_text": "..."}           # 完成
"""
from __future__ import annotations

import asyncio
import atexit
import json
import logging
import re
import signal
import sys
import urllib.error
import urllib.request
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

try:
    from .context import build_default_context
    from .permission import PermissionEngine, PermissionResult
    from .system_prompt import build_system_prompt
    from .tool import BaseTool, ToolResult, get_registry
except ImportError:
    from context import build_default_context
    from permission import PermissionEngine, PermissionResult
    from system_prompt import build_system_prompt
    from tool import BaseTool, ToolResult, get_registry

try:
    from .llm_pricing import (
        extract_usage_from_response,
        get_pricing_config,
        print_token_info,
        TokenUsage,
    )
except ImportError:
    from llm_pricing import (
        extract_usage_from_response,
        get_pricing_config,
        print_token_info,
        TokenUsage,
    )

try:
    from .compact.token_budget import (
        calculate_budget_info,
        calculate_token_budget,
        estimate_response_tokens,
    )
except ImportError:
    try:
        from compact.token_budget import (
            calculate_budget_info,
            calculate_token_budget,
            estimate_response_tokens,
        )
    except ImportError:
        calculate_budget_info = None
        calculate_token_budget = None
        estimate_response_tokens = None

# LLM API 配置（可注入）
# 选择 LLM 提供者: "ollama" | "minimax"
# 默认值从环境变量或 crush.json 读取
LLM_PROVIDER = "minimax"
LLM_API_URL = "https://api.minimaxi.com/anthropic/v1/messages"
LLM_MODEL = "MiniMax-M2.7"
LLM_API_KEY = ""

# 初始化时尝试从 config 加载
try:
    from .config import get_config
    _cfg = get_config()
    if _cfg.api_key:
        LLM_API_KEY = _cfg.api_key
    if _cfg.api_url:
        LLM_API_URL = _cfg.api_url
    if _cfg.model:
        LLM_MODEL = _cfg.model
except Exception:
    pass

# 全局 Agent 注册表（用于进程退出时保存）
_current_agent: "Agent | None" = None


def _get_current_agent() -> "Agent | None":
    """获取当前活动的 Agent 实例"""
    return _current_agent


def _set_current_agent(agent: "Agent | None") -> None:
    """设置当前活动的 Agent 实例"""
    global _current_agent
    _current_agent = agent


def _save_current_session() -> None:
    """保存当前 Agent 的 Session（进程退出时调用）"""
    agent = _current_agent
    if agent is None:
        return

    try:
        # 保存 Session 记忆
        if agent._session_memory:
            agent._session_memory.save()

        # 保存 Session 消息
        if agent._session_manager and agent._session_id:
            api_messages = agent._build_api_messages()
            agent._session_manager.save_messages(agent._session_id, api_messages)

        logger.info("Session saved on process exit")
    except Exception as e:
        logger.error(f"Failed to save session on exit: {e}")


def _signal_handler(signum, frame) -> None:
    """信号处理器（Ctrl+C / SIGTERM）"""
    _save_current_session()
    # 重新安装处理器以便可以继续退出
    signal.signal(signum, signal.SIG_DFL)
    # 触发默认行为（退出）
    raise KeyboardInterrupt


# 注册进程退出和信号处理器
atexit.register(_save_current_session)
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


@dataclass
class Message:
    """对话消息"""
    role: str          # "user" | "assistant" | "system" | "tool"
    content: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))  # 消息唯一 ID
    parent_id: str = ""  # 父消息 ID，用于追踪消息关系
    created_at: datetime = field(default_factory=datetime.now)  # 创建时间
    tool_call_id: str = ""  # 用于 tool 消息关联调用
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)


@dataclass
class AgentConfig:
    """Agent 配置"""
    model: str = LLM_MODEL
    api_url: str = LLM_API_URL
    api_key: str = LLM_API_KEY
    temperature: float = 0.1
    max_turns: int = 20
    timeout: int = 180
    permission_engine: PermissionEngine | None = None
    max_context_tokens: int = 180000  # 上下文 token 上限，超出后压缩
    parallel_tool_calls: bool = True   # 是否并行执行独立的工具调用
    auth_callback: callable | None = None  # 授权确认回调 (tool_name, args) -> bool
    system_prompt_config: dict | None = None  # System prompt 优先级配置
    multi_agent_enabled: bool = False  # 是否启用 Multi-Agent 模式（基于复杂度自动选择 L1/L2/L3）
    allowed_tools: list[str] | None = None  # 允许的工具名称列表，None 表示全部允许
    # 记忆提取配置
    auto_extract_enabled: bool = True  # 是否启用自动记忆提取
    auto_extract_interval: int = 3  # 每 N 轮对话提取一次


class ToolCallMatch:
    """从 LLM 响应中解析出的工具调用"""
    def __init__(self, tool_name: str, args: dict):
        self.tool_name = tool_name
        self.args = args


@dataclass
class StreamEvent:
    """流式事件"""
    type: str           # thinking | tool_start | tool_progress | tool_recovered | tool_result | tool_error | tool_auth_required | text | done | usage
    content: str = ""
    tool: str = ""
    args: dict = field(default_factory=dict)
    success: bool = True
    data: Any = None
    recovered: bool = False
    warning: str = ""
    error: str = ""
    usage: dict = field(default_factory=dict)  # {"input_tokens": int, "output_tokens": int, "total_tokens": int}
    auth_required: tuple = None  # (tool_name, args, reason) 当需要授权时

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v}


def _extract_tool_calls_from_text(text: str) -> list[tuple[str, dict]]:
    """
    从文本（如 thinking 内容）中提取工具调用。
    匹配格式：
    1. JSON格式：[调用 工具名 工具: {"param": "value"}]
    2. XML格式：[调用 工具名> <参数>值</参数> </调用>]
    返回: [(tool_name, args_dict), ...]
    容错：即使 JSON 不完整也尝试解析 command 参数
    """
    matches = []
    pattern = r'\[调用\s+(\w+)\s+工具:\s*(\{.*?\})\]'
    for m in re.finditer(pattern, text, re.DOTALL):
        tool_name = m.group(1)
        args_str = m.group(2)
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            # 容错：尝试提取 command 参数
            cm = re.search(r'"command"\s*:\s*"([^"]*)"', args_str)
            if cm:
                args = {"command": cm.group(1)}
            else:
                # 尝试其他常见参数
                fp = re.search(r'"file_path"\s*:\s*"([^"]*)"', args_str)
                if fp:
                    args = {"file_path": fp.group(1)}
                else:
                    continue
        matches.append((tool_name, args))

    # XML 格式支持：[调用 工具名> <param>value</param> </调用>]
    # 也支持：[调用 工具名"> <param>value</param> </调用>]
    xml_pattern = r'\[调用\s+(\w+)\s*"?>\s*<([^>]+)>\s*([^<]*)</\2>\s*</调用>\]'
    for m in re.finditer(xml_pattern, text):
        tool_name = m.group(1)
        param_name = m.group(2)
        param_value = m.group(3).strip()
        matches.append((tool_name, {param_name: param_value}))

    return matches


def parse_content_blocks(response: dict) -> list[dict]:
    """
    从 LLM 响应中解析所有 content blocks，按原顺序返回。

    返回格式：
    [{"type": "text", "text": "..."}, {"type": "tool_use", "name": "...", "input": {...}}, ...]

    支持的 block type：
    - text: 文本内容
    - tool_use: 工具调用
    - thinking: 思考过程（Claude 特有，跳过）

    支持的响应格式：
    - 标准 Anthropic: response["content"] = [{"type": "text/tool_use", ...}]
    - 字符串 content: response["content"] = "普通文本"
    - MiniMax 格式: response["message"]["content"] = [...]
    - OpenAI 格式: response["choices"][0]["message"] = {"content": "...", "tool_calls": [...]}
    """
    blocks = []
    try:
        content = response.get("content", [])

        # content 是字符串的情况（如某些 API 直接返回文本）
        if isinstance(content, str):
            if content.strip():
                blocks.append({"type": "text", "text": content.strip()})
            return blocks

        # MiniMax 等格式：内容在 response["message"]["content"]
        if not content and isinstance(response.get("message"), dict):
            content = response.get("message", {}).get("content", [])

        # OpenAI 格式：response["choices"][0]["message"]
        if not content and isinstance(response.get("choices"), list):
            choice = response["choices"][0] if response["choices"] else {}
            message = choice.get("message", {}) if isinstance(choice, dict) else {}
            content = message.get("content", [])
            # OpenAI tool_calls
            openai_tools = message.get("tool_calls", [])
            for t in openai_tools:
                blocks.append({
                    "type": "tool_use",
                    "id": t.get("id", ""),
                    "name": t.get("function", {}).get("name", ""),
                    "input": json.loads(t.get("function", {}).get("arguments", "{}")),
                })

        if not isinstance(content, list):
            # content 可能是字符串（如 OpenAI 纯文本回复）
            if isinstance(content, str) and content.strip():
                blocks.append({"type": "text", "text": content.strip()})
                return blocks
            content = [] if not content else [content]

        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            if block_type == "thinking":
                # 从 thinking 内容中提取工具调用
                thinking_text = block.get("thinking", "") or ""
                tool_calls = _extract_tool_calls_from_text(thinking_text)
                for tc in tool_calls:
                    blocks.append({"type": "tool_use", "name": tc[0], "input": tc[1]})
                # thinking 内容也输出（作为特殊文本块）
                if thinking_text.strip():
                    blocks.append({"type": "thinking_text", "text": thinking_text.strip()})
            elif block_type == "tool_use":
                blocks.append(block)
            elif block_type == "text":
                # 检查文本中是否包含工具调用（MiniMax 有时把工具调用写成普通文本）
                text = block.get("text", "") or ""
                tool_calls = _extract_tool_calls_from_text(text)
                if tool_calls:
                    # 文本中包含工具调用：提取出来作为 tool_use 执行
                    for tc in tool_calls:
                        blocks.append({"type": "tool_use", "name": tc[0], "input": tc[1]})
                    # 纯工具调用文本直接丢弃（不再输出说明文本）
                else:
                    blocks.append(block)
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError):
        pass
    return blocks


def parse_tool_calls(response: dict) -> list[ToolCallMatch]:
    """
    从 LLM 响应中解析工具调用（仅返回 tool_use 块）。
    兼容两种格式：
    1. Anthropic 格式：response["content"] = [{"type": "tool_use", ...}]
    2. 旧格式文本解析：回复中包含 "[调用 工具名 工具: {...}]"
    """
    matches = []
    blocks = parse_content_blocks(response)

    # 优先从结构化 blocks 中提取
    for block in blocks:
        if block.get("type") == "tool_use":
            name = block.get("name", "")
            tool_input = block.get("input", {})
            if name:
                matches.append(ToolCallMatch(name, tool_input))

    # 如果没有结构化 tool_use，尝试从文本中解析（包括 thinking）
    if not matches:
        try:
            content = response.get("content", [])
            if isinstance(content, list):
                for block in content:
                    block_type = block.get("type", "")
                    if block_type == "text":
                        text = block.get("text", "")
                    elif block_type == "thinking":
                        text = block.get("thinking", "") or ""
                    else:
                        continue
                    for tool_name, args in _extract_tool_calls_from_text(text):
                        matches.append(ToolCallMatch(tool_name, args))
            elif isinstance(content, str):
                for tool_name, args in _extract_tool_calls_from_text(content):
                    matches.append(ToolCallMatch(tool_name, args))
        except (KeyError, TypeError, AttributeError):
            pass

    return matches


def call_llm(
    messages: list[dict],
    model: str,
    api_url: str,
    temperature: float = 0.1,
    timeout: int = 60,
    api_key: str = "",
    tools: list = None,
) -> dict:
    """
    调用 LLM API（参考 OpenClaw 的 pi-ai 实现）

    使用 Anthropic messages API 格式，通过 MiniMax 的 Anthropic 兼容端点
    支持 function calling（tool_use 格式）
    """
    global LLM_PROVIDER, LLM_API_KEY
    provider = LLM_PROVIDER
    key = api_key or LLM_API_KEY

    if provider == "minimax":
        # Anthropic messages API 格式
        system_content = None
        anthropic_messages = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls")
            tool_call_id = msg.get("tool_call_id", "")

            if role == "system":
                # Anthropic 格式：system 作为顶级参数，不是消息
                system_content = content
            elif role == "user":
                anthropic_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                if tool_calls:
                    # assistant 带 tool_calls：保留完整 content blocks
                    blocks = []
                    if content:
                        blocks.append({"type": "text", "text": content})
                    for tc in tool_calls:
                        blocks.append({
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": tc.get("name", ""),
                            "input": tc.get("input", {}),
                        })
                    anthropic_messages.append({"role": "assistant", "content": blocks})
                else:
                    anthropic_messages.append({"role": "assistant", "content": content})
            elif role == "tool":
                # Anthropic 格式：tool 结果作为 user 消息的 tool_result content block
                tool_result_content = str(content) if content else ""
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": tool_result_content,
                    }]
                })

        data = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": 150000,
        }
        if system_content:
            data["system"] = system_content
        if tools:
            data["tools"] = tools

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "anthropic-version": "2023-06-01",
            "anthropic-dangerous-direct-browser-access": "true",
        }
    elif provider == "ollama":
        data = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        headers = {"Content-Type": "application/json"}
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")

    req_body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    logger.debug(f"[CALL-LLM-REQ] url={api_url}, model={model}, msg_count={len(data.get('messages', []))}, "
                 f"has_system={bool(data.get('system'))}, has_tools={bool(data.get('tools'))}, "
                 f"tools_count={len(data.get('tools', []))}, body_len={len(req_body)}")

    req = urllib.request.Request(
        api_url,
        data=req_body,
        headers=headers,
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        # DEBUG: 检查API返回的content blocks类型
        content_blocks = result.get("content", [])
        block_types = [b.get("type", "?") if isinstance(b, dict) else type(b).__name__ for b in content_blocks]
        logger.debug(f"[LLM-RESP] block_types={block_types}, stop_reason={result.get('stop_reason')}")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
        raise RuntimeError(f"HTTP {e.code} from API: {err_body[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"URL error (网络/连接问题): {e.reason}")
    except TimeoutError:
        raise RuntimeError(f"LLM API 请求超时（{timeout}s），请检查网络或 API 地址是否可达")

    return result


class Agent:
    """
    Agent 核心类
    参考 Claude Code 的 QueryEngine 设计
    """

    def __init__(self, config: AgentConfig | None = None, structured_io: Any = None):
        self.config = config or AgentConfig()
        self.registry = get_registry()
        self.messages: list[Message] = []
        self._id_index: dict[str, Message] = {}  # 消息 ID 索引，用于 O(1) 查找
        self.turn_count = 0
        self._memory_retriever = None
        self._memory_extractor = None
        self._memory_store = None
        self._auto_extract_turn_counter = 0  # 记忆提取轮次计数
        self._session_explicit_save_detected = False  # Session 级别的显式保存标志
        self._path_protection = None
        self._auto_classifier = None
        self._last_usage: "TokenUsage | None" = None  # 最近一次 LLM 调用的 token 使用情况
        self._total_usage: TokenUsage = TokenUsage()  # Session 累计 token 使用情况
        self._session_id: str | None = None  # 当前 Session ID
        self._session_manager = None  # Session 管理器
        self._session_memory = None  # Session 记忆
        self._structured_io = structured_io  # StructuredIO 实例
        self._init_memory_retriever()
        self._init_memory_extractor()
        self._init_path_protection()
        self._init_auto_classifier()
        self._init_session_manager()

    def _init_memory_retriever(self) -> None:
        """Initialize memory retriever if memory module is available."""
        try:
            from .memory.memory_retriever import MemoryRetriever
            self._memory_retriever = MemoryRetriever()
        except ImportError:
            try:
                from memory.memory_retriever import MemoryRetriever
                self._memory_retriever = MemoryRetriever()
            except ImportError:
                logger.debug("MemoryRetriever not available, memory integration disabled")
                self._memory_retriever = None

    def _init_memory_extractor(self) -> None:
        """Initialize memory extractor and store if memory module is available."""
        if not self.config.auto_extract_enabled:
            self._memory_extractor = None
            self._memory_store = None
            return

        try:
            from .memory.memory_store import MemoryStore
            from .memory.extract_memories import MemoryExtractor
            self._memory_store = MemoryStore()
            self._memory_extractor = MemoryExtractor(self._memory_store)
        except ImportError:
            try:
                from memory.memory_store import MemoryStore
                from memory.extract_memories import MemoryExtractor
                self._memory_store = MemoryStore()
                self._memory_extractor = MemoryExtractor(self._memory_store)
            except ImportError:
                logger.debug("MemoryExtractor not available, auto memory extraction disabled")
                self._memory_extractor = None
                self._memory_store = None

    def set_session_memory(self, session_memory) -> None:
        """设置 Session 记忆"""
        self._session_memory = session_memory

    def _init_path_protection(self) -> None:
        """Initialize path protection manager if security module is available."""
        try:
            from .security.path_protection import ProtectedPathManager
            self._path_protection = ProtectedPathManager()
        except ImportError:
            try:
                from security.path_protection import ProtectedPathManager
                self._path_protection = ProtectedPathManager()
            except ImportError:
                logger.debug("ProtectedPathManager not available, path protection disabled")
                self._path_protection = None

    def _init_auto_classifier(self) -> None:
        """Initialize auto classifier if security module is available."""
        try:
            from .security.auto_classifier import AutoClassifier
            self._auto_classifier = AutoClassifier()
        except ImportError:
            try:
                from security.auto_classifier import AutoClassifier
                self._auto_classifier = AutoClassifier()
            except ImportError:
                logger.debug("AutoClassifier not available, auto classification disabled")
                self._auto_classifier = None

    def _init_session_manager(self) -> None:
        """Initialize session manager if session module is available."""
        try:
            from .session import SessionManager
            self._session_manager = SessionManager()
        except ImportError:
            try:
                from session import SessionManager
                self._session_manager = SessionManager()
            except ImportError:
                logger.debug("SessionManager not available, session persistence disabled")
                self._session_manager = None

    def _get_llm_client_for_multi_agent(self) -> Any:
        """
        创建用于 Multi-Agent 的 LLM 客户端适配器

        Returns:
            适配了 complete 方法的 LLM 客户端
        """
        class LLMClientAdapter:
            """适配现有 Agent 的 LLM 调用接口"""
            def __init__(self, agent: Agent):
                self.agent = agent

            async def complete(self, prompt: str) -> str:
                """使用 Agent 的 LLM 配置完成请求"""
                try:
                    api_messages = [{"role": "user", "content": prompt}]
                    response = call_llm(
                        api_messages,
                        model=self.agent.config.model,
                        api_url=self.agent.config.api_url,
                        temperature=self.agent.config.temperature,
                        timeout=self.agent.config.timeout,
                        api_key=self.agent.config.api_key,
                        tools=None,
                    )
                    # 提取文本响应
                    if isinstance(response, dict):
                        content = response.get("content", "")
                        if isinstance(content, str):
                            return content
                        elif isinstance(content, list):
                            for block in content:
                                if block.get("type") == "text":
                                    return block.get("text", "")
                        message = response.get("message", {})
                        msg_content = message.get("content", "")
                        if isinstance(msg_content, str):
                            return msg_content
                    return str(response)
                except Exception as e:
                    logger.error(f"LLM 调用失败: {e}")
                    return f"[LLM 错误: {e}]"

        return LLMClientAdapter(self)

    def _convert_multi_agent_event(self, event: Any) -> StreamEvent:
        """
        将 Multi-Agent 的事件转换为 Agent 的 StreamEvent

        Args:
            event: Multi-Agent.StreamEvent

        Returns:
            Agent.StreamEvent
        """
        if isinstance(event, StreamEvent):
            return event
        if hasattr(event, 'type'):
            return StreamEvent(
                type=event.type,
                content=getattr(event, 'content', ''),
                tool=getattr(event, 'tool', ''),
                args=getattr(event, 'args', {}),
                success=getattr(event, 'success', True),
                data=getattr(event, 'data', None),
                recovered=getattr(event, 'recovered', False),
                warning=getattr(event, 'warning', ''),
                error=getattr(event, 'error', ''),
            )
        # Fallback
        return StreamEvent(type="text", content=str(event))

    def _print_usage(self) -> None:
        """打印 token 使用情况和费用到控制台（Session 累计）"""
        if self._total_usage.input_tokens == 0 and self._total_usage.output_tokens == 0:
            return
        
        pricing_config = get_pricing_config()
        pricing = pricing_config.get_pricing()
        
        # 如果没有从 API 获取到 input_tokens，回退到本地计数
        if self._total_usage.input_tokens == 0:
            from .compact.token_counter import count_messages_tokens
            self._total_usage.input_tokens = count_messages_tokens(self.messages)
        
        cost = self._total_usage.cost(pricing)
        print_token_info(
            self._total_usage,
            cost,
            total_context=self.config.max_context_tokens
        )

    async def _trigger_auto_memory_extraction(self) -> None:
        """触发自动记忆提取（在对话结束时调用）"""
        if not self._memory_extractor or not self.config.auto_extract_enabled:
            return

        # Session 级别互斥：如果检测到显式保存，跳过自动提取
        if self._session_explicit_save_detected:
            logger.info("Explicit save detected in session, skipping auto extraction")
            return

        # 更新提取轮次计数
        self._auto_extract_turn_counter += 1

        # 检查是否达到提取间隔
        if self._auto_extract_turn_counter < self.config.auto_extract_interval:
            return

        # 重置计数
        self._auto_extract_turn_counter = 0

        # 执行记忆提取
        try:
            from .memory.extract_memories import extract_memories_from_messages

            logger.info("Starting auto memory extraction...")
            result = await extract_memories_from_messages(
                messages=self.messages,
                store=self._memory_store,
            )

            if result.success and result.memories_saved > 0:
                logger.info(f"Auto memory extraction completed: {result.memories_saved} memories saved")
            elif result.error:
                logger.warning(f"Auto memory extraction skipped: {result.error}")

        except Exception as e:
            logger.error(f"Auto memory extraction failed: {e}")

    def _classify_operation(self, tool_name: str, args: dict) -> tuple[bool, str]:
        """
        Classify the tool operation using AutoClassifier.
        Returns (should_block, error_message).
        """
        if self._auto_classifier is None:
            return False, ""

        classification = self._auto_classifier.classify({
            "tool_name": tool_name,
            "input": args,
        })

        if classification.should_deny:
            return True, f"操作被自动分类为危险: {classification.reason}"

        if classification.should_ask:
            return True, f"操作需要确认: {classification.reason}"

        return False, ""

    def _check_path_protection(self, tool_name: str, args: dict) -> tuple[bool, str]:
        """
        Check if the tool operation targets a protected path.
        Returns (is_protected, error_message).
        """
        if self._path_protection is None:
            return False, ""

        # Tools that work with file paths
        path_tools = {"Read", "Write", "Edit", "Bash", "Glob", "Grep"}
        if tool_name not in path_tools:
            return False, ""

        # Extract path from args
        command = args.get("command", "")
        if args.get("file_path"):
            path = args["file_path"]
        elif args.get("path"):
            path = args["path"]
        elif command:
            parts = command.split()
            path = parts[1] if len(parts) > 1 else ""
        else:
            path = ""
        if not path:
            return False, ""

        # Check for read operations on protected paths (allowed with warning)
        if self._path_protection.is_protected(path):
            operation = "read" if tool_name == "Read" else "write"
            if self._path_protection.check_override(path, operation):
                return False, ""
            return True, f"路径受保护: {path}"

        return False, ""

    def _get_memory_context(self, query: str) -> str:
        """Retrieve relevant memories and format them for injection into system prompt."""
        if self._memory_retriever is None:
            return ""

        try:
            memories = self._memory_retriever.retrieve(query, limit=5)
            if not memories:
                return ""

            context_parts = ["\n\n## Relevant Memory\n"]
            for mem in memories:
                context_parts.append(f"- **{mem.header.name}**: {mem.content[:200]}...")
                if mem.reason:
                    context_parts.append(f"  ({mem.reason})")

            return "\n".join(context_parts)
        except Exception as e:
            logger.debug(f"Memory retrieval failed: {e}")
            return ""

    def _update_session_memory(self, trigger: str, **kwargs) -> None:
        """
        更新 SessionMemory（如果可用）

        Args:
            trigger: 触发来源标识
            **kwargs: 根据触发来源传入不同参数
                - user_message: 用户消息内容
                - tool_name: 工具名称
                - tool_args: 工具参数
                - tool_result: 工具结果
                - success: 是否成功
        """
        if not self._session_memory:
            return

        try:
            if trigger == "user_message":
                # 用户消息：更新任务规格和当前状态
                content = kwargs.get("content", "")
                self._session_memory.update_task_spec(content[:500] if len(content) > 500 else content)
                self._session_memory.update_current_state(f"用户请求: {content[:100]}..." if len(content) > 100 else f"用户请求: {content}")

            elif trigger == "tool_success":
                tool_name = kwargs.get("tool_name", "")
                tool_args = kwargs.get("tool_args", {})
                tool_result = kwargs.get("tool_result")

                # 记录文件操作
                if tool_name in ("Read", "Write", "Edit"):
                    file_path = tool_args.get("file_path", "")
                    if file_path:
                        desc = ""
                        if tool_name == "Read":
                            desc = f"读取文件"
                        elif tool_name == "Write":
                            desc = "写入文件"
                        elif tool_name == "Edit":
                            desc = "编辑文件"
                        self._session_memory.add_file(file_path, desc)

                # 记录 Bash 命令
                elif tool_name == "Bash":
                    command = tool_args.get("command", "")
                    if command:
                        self._session_memory.add_workflow_step(command)

            elif trigger == "tool_error":
                tool_name = kwargs.get("tool_name", "")
                error = kwargs.get("error", "")
                if error:
                    self._session_memory.add_error(f"{tool_name}: {error[:200]}", "见工具返回结果")

            # 标记更新
            self._session_memory._mark_updated()

        except Exception as e:
            logger.debug(f"Failed to update session memory: {e}")

    def _add_message_with_index(self, message: Message) -> None:
        """
        添加消息并更新索引

        Args:
            message: 要添加的消息
        """
        self.messages.append(message)
        self._id_index[message.id] = message

    def _rebuild_id_index(self) -> None:
        """重建消息 ID 索引"""
        self._id_index = {m.id: m for m in self.messages}

    def _get_message_by_id(self, message_id: str) -> Message | None:
        """
        通过 ID 获取消息（O(1) 查找）

        Args:
            message_id: 消息 ID

        Returns:
            找到的消息或 None
        """
        return self._id_index.get(message_id)

    def _build_system_message(self) -> Message:
        """构建 system prompt，支持优先级配置"""
        tools = self.registry.all()
        context = build_default_context()
        prompt = build_system_prompt(tools, context, self.config.system_prompt_config)
        return Message(role="system", content=prompt)

    def _check_permission(self, tool_name: str, args: dict) -> PermissionResult:
        """权限检查"""
        if self.config.permission_engine is None:
            return PermissionResult(behavior="allow", updated_input=args)
        return self.config.permission_engine.check(tool_name, args)

    def _count_tokens(self, text: str) -> int:
        """估算文本的 token 数量（粗略估算：中文约 2 字符/token，英文约 4 字符/token）"""
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 2 + other_chars / 4)

    def _get_budget_info(self) -> dict:
        """
        获取当前 budget 信息

        Returns:
            budget 信息字典，如果 token_budget 模块不可用则返回空字典
        """
        if calculate_budget_info is None:
            return {}

        try:
            from .compact.token_counter import count_messages_tokens
        except ImportError:
            try:
                from compact.token_counter import count_messages_tokens
            except ImportError:
                return {}

        api_messages = self._build_api_messages()
        current_tokens = count_messages_tokens(api_messages)

        return calculate_budget_info(
            max_context_tokens=self.config.max_context_tokens,
            current_tokens=current_tokens,
            reserved_buffer=5000,
        )

    def _get_available_budget(self) -> int:
        """
        获取本轮可用输出 token 数

        Returns:
            可用 token 数，如果模块不可用则返回 0
        """
        if calculate_token_budget is None:
            return 0

        try:
            from .compact.token_counter import count_messages_tokens
        except ImportError:
            try:
                from compact.token_counter import count_messages_tokens
            except ImportError:
                return 0

        api_messages = self._build_api_messages()
        current_tokens = count_messages_tokens(api_messages)

        return calculate_token_budget(
            max_context_tokens=self.config.max_context_tokens,
            current_tokens=current_tokens,
            reserved_buffer=5000,
        )

    async def _compress_if_needed(self) -> bool:
        """
        检查并执行自动压缩
        返回: 是否执行了压缩
        """
        try:
            from .compact.auto_compact import try_auto_compact
            from .compact.compact_manager import CompactConfig

            config = CompactConfig(
                warning_buffer=20000,
                auto_compact_buffer=13000,
                blocking_buffer=3000,
            )

            # 直接计算当前 token 数（不调用 _build_api_messages 避免递归）
            total_tokens = sum(self._count_tokens(m.content) for m in self.messages)

            if total_tokens < config.auto_compact_buffer:
                return False

            # 构建 API 格式消息用于压缩
            api_messages = []
            for m in self.messages:
                if m.role == "system":
                    api_messages.append({"role": "system", "content": m.content})
                elif m.role == "assistant":
                    api_messages.append({"role": "assistant", "content": m.content})
                elif m.role == "tool":
                    api_messages.append({"role": "tool", "tool_call_id": getattr(m, "tool_call_id", ""), "content": m.content})
                else:
                    api_messages.append({"role": "user", "content": m.content})

            result = await try_auto_compact(api_messages, config)

            if result.success and result.messages_removed > 0:
                self._apply_compaction(result)
                # 触发压缩后 Hook
                await self._trigger_hook("PostCompact", {
                    "original_tokens": result.original_tokens,
                    "compacted_tokens": result.compacted_tokens,
                    "messages_removed": result.messages_removed,
                })
                return True

        except ImportError:
            pass
        except Exception as e:
            logger.error(f"Auto compact failed: {e}")

        return False

    def _apply_compaction(self, result) -> None:
        """应用压缩结果到消息列表"""
        if not result or not result.summary:
            return

        # 找到 system 消息和中间消息的位置，用摘要替换
        system_msg = None
        other_messages = []

        for m in self.messages:
            if m.role == "system":
                if system_msg is None:
                    system_msg = m
            else:
                other_messages.append(m)

        # 保留最近的 10 条消息
        recent = other_messages[-10:] if len(other_messages) > 10 else other_messages

        # 重建消息列表
        self.messages = []
        if system_msg:
            self.messages.append(system_msg)

        self.messages.append(Message(
            role="system",
            content=f"[之前的对话摘要]\n{result.summary}"
        ))

        self.messages.extend(recent)
        self._rebuild_id_index()
        self._save_session_if_needed()

    def _save_session_if_needed(self) -> None:
        """保存 Session 如果有 Session 管理器"""
        if not self._session_manager or not self._session_id:
            return

        try:
            # 构建 API 格式消息
            api_messages = self._build_api_messages()
            self._session_manager.save_messages(self._session_id, api_messages)
        except Exception as e:
            logger.error(f"Failed to save session: {e}")

    def _load_session(self, session_id: str) -> bool:
        """
        加载 Session

        Args:
            session_id: Session ID

        Returns:
            是否加载成功
        """
        if not self._session_manager:
            return False

        try:
            messages = self._session_manager.load_messages(session_id)
            if messages:
                # 重建 Message 对象列表
                self.messages = []
                self._id_index = {}
                for msg_data in messages:
                    msg = Message(
                        role=msg_data.get("role", "user"),
                        content=msg_data.get("content", ""),
                        tool_call_id=msg_data.get("tool_call_id", ""),
                    )
                    self._add_message_with_index(msg)
                self._session_id = session_id
                logger.info(f"Loaded session {session_id} with {len(messages)} messages")
                return True
        except Exception as e:
            logger.error(f"Failed to load session: {e}")
        return False

    def _micro_compact_if_needed(self) -> bool:
        """
        检查并执行 Micro-Compact（微压缩）
        返回: 是否执行了微压缩
        """
        try:
            from .compact.micro_compact import MicroCompactor

            # Micro-Compact 阈值：消息列表超过 20 条时考虑执行
            if len(self.messages) < 20:
                return False

            # 构建 API 格式消息
            api_messages = []
            for m in self.messages:
                if m.role == "system":
                    api_messages.append({"role": "system", "content": m.content})
                elif m.role == "assistant":
                    api_messages.append({"role": "assistant", "content": m.content})
                elif m.role == "tool":
                    api_messages.append({"role": "tool", "tool_call_id": getattr(m, "tool_call_id", ""), "content": m.content})
                else:
                    api_messages.append({"role": "user", "content": m.content})

            compactor = MicroCompactor()
            compacted = compactor.compact(api_messages)

            # 如果有变化，应用压缩
            if len(compacted) < len(api_messages):
                self._apply_micro_compaction(compacted, api_messages)
                logger.info(f"Micro-Compact: {len(api_messages)} -> {len(compacted)} messages")
                return True

        except ImportError:
            pass
        except Exception as e:
            logger.error(f"Micro compact failed: {e}")

        return False

    def _apply_micro_compaction(self, compacted: list[dict], original: list[dict]) -> None:
        """
        应用微压缩结果到消息列表

        Args:
            compacted: 压缩后的 API 格式消息
            original: 原始的 API 格式消息（用于对比）
        """
        if not compacted:
            return

        # 找到保留的消息数量
        preserved_count = len(compacted)

        # 重建 Message 对象列表
        new_messages = []
        for msg in compacted:
            role = msg.get("role", "")
            content = msg.get("content", "")
            tool_call_id = msg.get("tool_call_id", "")

            if role == "system":
                new_messages.append(Message(role=role, content=content))
            elif role == "user":
                new_messages.append(Message(role=role, content=content))
            elif role == "assistant":
                new_messages.append(Message(role=role, content=content))
            elif role == "tool":
                new_messages.append(Message(role=role, content=content, tool_call_id=tool_call_id))

        self.messages = new_messages
        self._rebuild_id_index()

    def _compress_messages(self) -> None:
        """压缩消息历史，防止超出上下文限制"""
        max_tokens = self.config.max_context_tokens

        # 计算当前总 token 数
        total_tokens = 0
        for m in self.messages:
            total_tokens += self._count_tokens(m.content)

        # 如果没超过限制，无需压缩
        if total_tokens <= max_tokens:
            return

        # 保留策略：保留 system 消息，最近的 user 消息和 assistant 消息对
        # 压缩中间的消息历史

        system_msg = None
        compressed_history: list[Message] = []
        recent_messages: list[Message] = []
        middle_messages: list[Message] = []

        for i, m in enumerate(self.messages):
            if m.role == "system":
                system_msg = m
            elif i >= len(self.messages) - 10:
                # 保留最近 10 条消息
                recent_messages.append(m)
            else:
                middle_messages.append(m)

        # 估算中间消息的总长度，如果太长则压缩
        middle_tokens = sum(self._count_tokens(m.content) for m in middle_messages)
        recent_tokens = sum(self._count_tokens(m.content) for m in recent_messages)

        # 计算需要保留多少中间消息
        target_middle_tokens = max(0, max_tokens - recent_tokens -
                                   (self._count_tokens(system_msg.content) if system_msg else 0) - 5000)

        if middle_messages and middle_tokens > target_middle_tokens:
            # 压缩中间消息：只保留摘要
            compressed_summary = self._summarize_messages(middle_messages)
            compressed_history.append(Message(
                role="system",
                content=f"[之前的对话摘要]\n{compressed_summary}"
            ))

        # 重新构建消息列表
        self.messages = []
        if system_msg:
            self.messages.append(system_msg)
        self.messages.extend(compressed_history)
        self.messages.extend(recent_messages)
        self._rebuild_id_index()

    def _summarize_messages(self, messages: list[Message]) -> str:
        """将多条消息压缩为摘要"""
        if not messages:
            return ""

        parts = []
        for m in messages:
            if m.role == "user":
                # 截取用户消息前 100 字符
                content = m.content[:100] + "..." if len(m.content) > 100 else m.content
                parts.append(f"用户: {content}")
            elif m.role == "assistant" and m.content:
                # 截取助手回复前 100 字符
                content = m.content[:100] + "..." if len(m.content) > 100 else m.content
                parts.append(f"助手: {content}")
            elif m.role == "tool":
                # 工具结果更精简
                content = m.content[:50] + "..." if len(m.content) > 50 else m.content
                parts.append(f"工具结果: {content}")

        return "\n".join(parts[:20])  # 最多保留 20 条摘要

    async def _execute_tools_parallel(
        self,
        tool_calls: list[dict],
        yield_func: callable = None,
    ) -> list[tuple[dict, ToolResult]]:
        """
        并行执行多个独立的工具调用。

        Args:
            tool_calls: 工具调用列表，每个元素包含 name, input, id
            yield_func: 回调函数，用于 yield 事件

        Returns:
            [(tool_call, result), ...] 结果列表
        """
        if not self.config.parallel_tool_calls or len(tool_calls) == 1:
            # 串行执行：只有一个工具调用或禁用并行
            results = []
            for tc in tool_calls:
                if tc.get("name") == "Edit":
                    # Edit 工具需要特殊处理（流式输出）
                    result_text = ""
                    async for event in self._execute_edit_with_stream_simple(tc["name"], tc["input"]):
                        if yield_func:
                            yield_func(event)
                        if event.type == "tool_result":
                            result_text = self._format_tool_result(
                                ToolResult(success=event.success, data=event.data, error=event.error),
                                tool_name=tc["name"]
                            )
                    results.append((tc, ToolResult(success=True, data=result_text)))
                else:
                    result = await self._execute_tool(tc["name"], tc["input"])
                    results.append((tc, result))
            return results

        # 并行执行：创建任务
        async def execute_single(tc: dict) -> tuple[dict, ToolResult]:
            name = tc.get("name", "")
            args = tc.get("input", {})

            if name == "Edit":
                # Edit 工具串行执行（因为可能有文件冲突）
                result_text = ""
                async for event in self._execute_edit_with_stream_simple(name, args):
                    if yield_func:
                        yield_func(event)
                    if event.type == "tool_result":
                        result_text = self._format_tool_result(
                            ToolResult(success=event.success, data=event.data, error=event.error),
                            tool_name=name
                        )
                return (tc, ToolResult(success=True, data=result_text))
            else:
                return (tc, await self._execute_tool(name, args))

        # 批量并行执行（排除 Edit 工具）
        non_edit_calls = [tc for tc in tool_calls if tc.get("name") != "Edit"]
        edit_calls = [tc for tc in tool_calls if tc.get("name") == "Edit"]

        results = []

        # 并行执行非 Edit 工具
        if non_edit_calls:
            tasks = [execute_single(tc) for tc in non_edit_calls]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for item in batch_results:
                if isinstance(item, Exception):
                    results.append((None, ToolResult(success=False, data=None, error=str(item))))
                else:
                    tc, result = item
                    results.append((tc, result))

        # Edit 工具串行执行
        for tc in edit_calls:
            result_text = ""
            async for event in self._execute_edit_with_stream_simple(tc["name"], tc["input"]):
                if yield_func:
                    yield_func(event)
                if event.type == "tool_result":
                    result_text = self._format_tool_result(
                        ToolResult(success=event.success, data=event.data, error=event.error),
                        tool_name=tc["name"]
                    )
            results.append((tc, ToolResult(success=True, data=result_text)))

        # 按原始顺序排序
        call_index = {tc.get("id", i): i for i, tc in enumerate(tool_calls)}
        results.sort(key=lambda x: call_index.get(x[0].get("id", 0), 0))

        return results

    async def _execute_tool(
        self,
        tool_name: str,
        args: dict,
        yield_func: callable = None,
    ) -> ToolResult:
        """
        执行单个工具，支持流式进度输出。

        yield_func: 如果传入，在执行过程中会逐条 yield StreamEvent。
                     用于 Edit 工具显示错误恢复进度。
        """
        # 执行 PreToolUse Hook
        try:
            from datetime import datetime

            from .hooks import get_enhanced_hook_manager

            manager = get_enhanced_hook_manager()
            context = {
                "tool_name": tool_name,
                "tool_args": args,
                "timestamp": datetime.now().isoformat(),
            }

            result = await manager.trigger("PreToolUse", context)
            if not result.success:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"PreToolUse hook blocked: {result.error}"
                )
        except ImportError:
            pass  # Hook 系统未加载
        except Exception as e:
            logger.error(f"Hook execution error: {e}")

        # 路径保护检查
        is_protected, error_msg = self._check_path_protection(tool_name, args)
        if is_protected:
            return ToolResult(
                success=False,
                data=None,
                error=f"路径保护: {error_msg}"
            )

        # 先检查权限引擎，如果已允许则跳过自动分类检查
        perm = self._check_permission(tool_name, args)
        permission_allowed = perm.behavior == "allow"
        
        if permission_allowed:
            logger.info(f"[DEBUG] PermissionEngine allowed: {tool_name}")

        # 自动分类检查（只有权限引擎未明确允许时才检查）
        if not permission_allowed:
            should_block, class_msg = self._classify_operation(tool_name, args)
            if should_block:
                # 分类为需要确认的操作，设置 auth_required 以便请求用户授权
                logger.info(f"[DEBUG] AutoClassifier blocked: {tool_name}, permission behavior: {perm.behavior}")
                return ToolResult(
                    success=False,
                    data=None,
                    error=class_msg,
                    auth_required=(tool_name, args, class_msg)
                )

        tool = self.registry.find(tool_name)
        if tool is None:
            return ToolResult(success=False, data=None, error=f"工具不存在: {tool_name}")

        # 输入校验
        valid, err = tool.validate_input(args)
        if not valid:
            return ToolResult(success=False, data=None, error=f"输入校验失败: {err}")

        # 权限检查
        perm = self._check_permission(tool_name, args)
        if perm.behavior == "deny":
            return ToolResult(
                success=False, data=None, error=f"权限被拒绝: {perm.reason}"
            )

        # 需要用户确认时，返回特殊结果让调用方处理
        if perm.behavior == "ask":
            result = ToolResult(
                success=False, 
                data=None, 
                error=f"需要授权",
                auth_required=(tool_name, args, perm.reason)
            )
            # 发送 auth_required 事件
            if yield_func:
                yield_func(StreamEvent(
                    type="tool_auth_required",
                    tool=tool_name,
                    args=args,
                    auth_required=(tool_name, args, perm.reason),
                    error="需要授权",
                ))
            return result

        # 通知开始执行
        if yield_func:
            yield_func(StreamEvent(
                type="tool_start",
                tool=tool_name,
                args=args,
            ))

        # 对于 Edit 工具，特殊处理错误恢复的流式输出
        if tool_name == "Edit" and yield_func:
            result = await self._execute_edit_with_streaming(tool, args, yield_func)
            # 执行 AfterTool Hook
            await self._execute_after_tool_hook(tool_name, args, result)
            return result

        # 执行
        try:
            result = await tool.call(args, {})
            if yield_func:
                yield_func(StreamEvent(
                    type="tool_result",
                    tool=tool_name,
                    success=result.success,
                    data=result.data,
                    error=result.error or "",
                ))
            # 执行 AfterTool Hook
            await self._execute_after_tool_hook(tool_name, args, result)
            return result
        except Exception as e:
            if yield_func:
                yield_func(StreamEvent(type="tool_error", tool=tool_name, error=str(e)))
            return ToolResult(success=False, data=None, error=str(e))

    async def _execute_after_tool_hook(
        self,
        tool_name: str,
        tool_args: dict,
        tool_result: ToolResult
    ) -> None:
        """执行 AfterTool Hook"""
        try:
            from datetime import datetime

            from .hooks import get_enhanced_hook_manager

            manager = get_enhanced_hook_manager()
            context = {
                "tool_name": tool_name,
                "tool_args": tool_args,
                "tool_result": tool_result.data if tool_result else None,
                "success": tool_result.success if tool_result else False,
                "error": tool_result.error if tool_result else "",
                "timestamp": datetime.now().isoformat(),
            }

            # 触发 PostToolUse 事件
            await manager.trigger("PostToolUse", context)

            # 如果失败，触发 PostToolUseFailure 事件
            if tool_result and not tool_result.success:
                await manager.trigger("PostToolUseFailure", context)

        except ImportError:
            pass  # Hook 系统未加载
        except Exception as e:
            logger.error(f"AfterTool hook execution error: {e}")

    async def _execute_edit_with_streaming(
        self,
        tool: BaseTool,
        args: dict,
        yield_func: callable,
    ) -> ToolResult:
        """
        执行 Edit 工具，带流式进度输出和错误恢复可视化。
        
        内部委托给 _execute_edit_with_stream_simple，将事件转发给 yield_func。
        """
        result = None
        async for event in self._execute_edit_with_stream_simple(tool.name, args):
            if yield_func:
                yield_func(event)
            if event.type == "tool_result":
                result = ToolResult(success=event.success, data=event.data, error=event.error)
        return result or ToolResult(success=False, data=None, error="No result returned")

    def _line_similarity(self, s1: str, s2: str) -> float:
        """计算两行文本的相似度"""
        if not s1 and not s2:
            return 1.0
        if not s1 or not s2:
            return 0.0
        m, n = len(s1), len(s2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i - 1] == s2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
        max_len = max(m, n)
        return 1.0 - (dp[m][n] / max_len) if max_len > 0 else 1.0

    async def _execute_edit_with_stream_simple(
        self,
        tool_name: str,
        args: dict,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Edit 工具的流式执行包装器。
        内部调用 _execute_edit_with_streaming，将事件逐个 yield 出去。
        """
        tool = self.registry.find(tool_name)
        if tool is None:
            yield StreamEvent(
                type="tool_error",
                tool=tool_name,
                error=f"工具不存在: {tool_name}",
            )
            return

        import asyncio
        import os
        import re

        file_path = args.get("file_path", "")
        old_text = args.get("oldText", "")
        new_text = args.get("newText", "")

        # 阶段1: 检查文件是否存在
        if not os.path.exists(file_path):
            yield StreamEvent(
                type="tool_error",
                tool=tool_name,
                error=f"文件不存在: {file_path}",
            )
            return

        # 阶段2: 读取文件内容
        yield StreamEvent(
            type="tool_progress",
            tool=tool_name,
            content=f"读取文件 {file_path}...",
            recovered=False,
        )

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            yield StreamEvent(type="tool_error", tool=tool_name, error=f"读取文件失败: {e}")
            return

        # 阶段3: 精确匹配
        yield StreamEvent(
            type="tool_progress",
            tool=tool_name,
            content="搜索目标文本...",
            recovered=False,
        )

        if old_text in content:
            new_content = content.replace(old_text, new_text, 1)
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
            except Exception as e:
                yield StreamEvent(type="tool_error", tool=tool_name, error=f"写入文件失败: {e}")
                return

            yield StreamEvent(
                type="tool_result",
                tool=tool_name,
                success=True,
                data={
                    "file_path": file_path,
                    "bytes_before": len(content),
                    "bytes_after": len(new_content),
                },
            )
            return

        # ---- 错误恢复阶段 ----

        # 策略1: 去除首尾空白
        yield StreamEvent(
            type="tool_progress",
            tool=tool_name,
            content="精确匹配未找到，尝试策略1：去除首尾空白...",
            recovered=True,
        )
        await asyncio.sleep(0.05)

        stripped_old = old_text.strip()
        if stripped_old != old_text and stripped_old in content:
            prefix_len = len(old_text) - len(old_text.lstrip())
            suffix_len = len(old_text) - len(old_text.rstrip())
            prefix = old_text[:prefix_len]
            suffix = old_text[-suffix_len:] if suffix_len else ""
            adjusted_new = prefix + new_text + suffix
            new_content = content.replace(stripped_old, adjusted_new, 1)

            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
            except Exception as e:
                yield StreamEvent(type="tool_error", tool=tool_name, error=f"写入文件失败: {e}")
                return

            warning = f"oldText 匹配时自动去除了首尾空白\n原始: {old_text!r}\n实际匹配: {stripped_old!r}"
            yield StreamEvent(
                type="tool_recovered",
                tool=tool_name,
                content="恢复成功，已自动修复空白问题",
                recovered=True,
                warning=warning,
            )
            yield StreamEvent(
                type="tool_result",
                tool=tool_name,
                success=True,
                data={
                    "file_path": file_path,
                    "recovered": True,
                    "warning": warning,
                },
            )
            return

        # 策略2: 归一化空白
        yield StreamEvent(
            type="tool_progress",
            tool=tool_name,
            content="策略1失败，尝试策略2：归一化空白字符...",
            recovered=True,
        )
        await asyncio.sleep(0.05)

        normalized_old = re.sub(r'[ \t]+', ' ', old_text)
        normalized_content = re.sub(r'[ \t]+', ' ', content)
        if normalized_old != old_text and normalized_old in normalized_content:
            idx = normalized_content.find(normalized_old)
            original_segment = content[idx:idx + len(old_text)]
            p_len = len(original_segment) - len(original_segment.lstrip())
            s_len = len(original_segment) - len(original_segment.rstrip())
            prefix = original_segment[:p_len]
            suffix = original_segment[-s_len:] if s_len else ""
            adjusted_new = prefix + new_text + suffix
            new_content = content[:idx] + adjusted_new + content[idx + len(old_text):]

            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
            except Exception as e:
                yield StreamEvent(type="tool_error", tool=tool_name, error=f"写入文件失败: {e}")
                return

            warning = "oldText 匹配时自动归一化了空白字符（tab/space 互换）"
            yield StreamEvent(
                type="tool_recovered",
                tool=tool_name,
                content="恢复成功，已自动归一化空白",
                recovered=True,
                warning=warning,
            )
            yield StreamEvent(
                type="tool_result",
                tool=tool_name,
                success=True,
                data={"file_path": file_path, "recovered": True, "warning": warning},
            )
            return

        # 策略3: fuzzy 行匹配
        yield StreamEvent(
            type="tool_progress",
            tool=tool_name,
            content="策略2失败，尝试策略3：逐行 fuzzy 匹配...",
            recovered=True,
        )
        await asyncio.sleep(0.05)

        old_lines = old_text.split('\n')
        content_lines = content.split('\n')

        best_start = -1
        best_score = 0.0
        window_size = len(old_lines)

        for i in range(len(content_lines) - window_size + 1):
            score = 0.0
            matched_lines = 0
            for j in range(window_size):
                sim = self._line_similarity(old_lines[j].strip(), content_lines[i + j].strip())
                if sim > 0.5:
                    score += sim
                    matched_lines += 1
            if matched_lines >= window_size * 0.6 and score > best_score:
                best_score = score
                best_start = i

        if best_start >= 0:
            new_lines = content_lines.copy()
            new_lines[best_start:best_start + window_size] = [new_text]
            new_content = '\n'.join(new_lines)

            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
            except Exception as e:
                yield StreamEvent(type="tool_error", tool=tool_name, error=f"写入文件失败: {e}")
                return

            warning = f"oldText 未精确匹配，通过 fuzzy 行匹配找到第 {best_start + 1}-{best_start + window_size} 行\n匹配质量: {best_score:.0%}"
            yield StreamEvent(
                type="tool_recovered",
                tool=tool_name,
                content="恢复成功，已通过 fuzzy 匹配定位",
                recovered=True,
                warning=warning,
            )
            yield StreamEvent(
                type="tool_result",
                tool=tool_name,
                success=True,
                data={"file_path": file_path, "recovered": True, "warning": warning},
            )
            return

        # ---- 恢复全部失败 ----
        yield StreamEvent(
            type="tool_progress",
            tool=tool_name,
            content="所有恢复策略均失败",
            recovered=False,
        )

        # 找相似行作为提示（使用 _line_similarity 方法）
        candidates = []
        for i, line in enumerate(content_lines):
            sim = self._line_similarity(old_text.strip(), line.strip()) if len(old_lines) == 1 else (
                self._line_similarity(old_lines[0].strip(), line.strip()) + self._line_similarity(old_lines[-1].strip(), line.strip())
            ) / 2
            if sim > 0.3:
                candidates.append((i + 1, sim, line.strip()))
        candidates.sort(key=lambda x: x[1], reverse=True)

        error_msg = "oldText 在文件中未找到匹配"
        if candidates:
            error_msg += "\n\n最相似的行（可能你想要的是其中之一）：\n"
            for i, (line_no, sim, line_text) in enumerate(candidates[:5], 1):
                error_msg += f"  {i}. 第{line_no}行 (相似度 {sim:.0%}): {line_text[:60]!r}"

        yield StreamEvent(type="tool_error", tool=tool_name, error=error_msg)

    def _format_tool_result(self, result: ToolResult, tool_name: str = "") -> str:
        """格式化工具结果为用户友好的文本"""
        if result.error:
            return f"[错误] {result.error}"
        
        data = result.data
        if not isinstance(data, dict):
            # 非字典数据直接转字符串，限制长度
            text = str(data)
            return text[:2000] + "..." if len(text) > 2000 else text

        # 根据工具类型格式化输出
        if tool_name == "Edit":
            file_path = data.get("file_path", "")
            bytes_before = data.get("bytes_before", 0)
            bytes_after = data.get("bytes_after", 0)
            diff = bytes_after - bytes_before
            diff_str = f"+{diff}" if diff > 0 else str(diff)
            recovered = data.get("recovered", False)
            warning = data.get("warning", "")
            
            msg = f"[OK] {file_path} ({diff_str} bytes)"
            if recovered and warning:
                msg += f"\n[WARN] {warning}"
            return msg
        
        elif tool_name == "Write":
            file_path = data.get("file_path", "")
            size = data.get("size", 0)
            return f"[OK] {file_path} ({size} bytes)"
        
        elif tool_name == "Read":
            content = data.get("content", data.get("data", ""))
            if isinstance(content, str) and len(content) > 500:
                return content[:500] + "\n... (内容已截断)"
            return str(content)
        
        elif tool_name == "Bash":
            stdout = data.get("stdout", "")
            stderr = data.get("stderr", "")
            return stdout or stderr or "(无输出)"
        
        elif tool_name == "Glob":
            files = data.get("files", [])
            count = len(files)
            if count == 0:
                return "未找到匹配的文件"
            return f"找到 {count} 个文件:\n" + "\n".join(files[:20]) + ("\n... (更多)" if count > 20 else "")
        
        elif tool_name == "Grep":
            matches = data.get("matches", [])
            count = data.get("count", len(matches))
            if count == 0:
                return "未找到匹配"
            return f"找到 {count} 处匹配:\n" + "\n".join(matches[:10]) + ("\n... (更多)" if count > 10 else "")
        
        elif tool_name == "Agent":
            return f"子Agent任务完成，结果: {json.dumps(data, ensure_ascii=False)[:500]}"
        
        # 默认格式化为易读的dict
        return json.dumps(data, indent=2, ensure_ascii=False)

    def _build_api_messages(self) -> list[dict]:
        """构建发给 LLM 的消息列表（不进行压缩，压缩由 _compress_if_needed 处理）"""
        messages = []
        for m in self.messages:
            if m.role == "system":
                messages.append({"role": "system", "content": m.content})
            elif m.role == "assistant":
                tc = getattr(m, "tool_calls", None)
                if tc:
                    messages.append({"role": "assistant", "content": m.content, "tool_calls": tc})
                else:
                    messages.append({"role": "assistant", "content": m.content})
            elif m.role == "tool":
                messages.append({
                    "role": "tool",
                    "tool_call_id": getattr(m, "tool_call_id", ""),
                    "content": m.content,
                })
            else:
                messages.append({"role": "user", "content": m.content})
        # Debug: log internal messages structure
        logger.debug(f"[BUILD-MSGS] internal messages: {len(self.messages)}")
        return messages

    def _build_tools_list(self) -> list[dict]:
        """从注册表构建 Anthropic 格式的 tools 列表，支持工具限制"""
        tools = []
        allowed = self.config.allowed_tools
        for tool_def in self.registry.all():
            # 如果配置了 allowed_tools，则只包含允许的工具
            if allowed is not None and tool_def.name not in allowed:
                continue
            tools.append({
                "name": tool_def.name,
                "description": tool_def.description,
                "input_schema": tool_def.input_schema,
            })
        return tools

    async def run(self, user_message: str) -> str:
        """
        运行 Agent 处理用户消息（非流式版本，内部调用 run_stream）
        返回最终回复文本
        """
        final_text = ""
        async for event in self.run_stream(user_message):
            if event.type == "text":
                final_text = event.content
            elif event.type == "done":
                # done 事件 content 可能是最终文本或错误信息
                if event.content:
                    final_text = event.content
        return final_text

    async def _trigger_hook(self, event: str, context: dict) -> bool:
        """触发 Hook 事件，返回是否成功"""
        try:
            from .hooks import get_enhanced_hook_manager
            manager = get_enhanced_hook_manager()
            result = await manager.trigger(event, context)
            return result.success
        except ImportError:
            return True  # Hook 系统未加载时默认允许
        except Exception as e:
            logger.error(f"Hook {event} error: {e}")
            return True  # Hook 错误不影响主流程

    async def _handle_slash_command(self, user_message: str) -> str | tuple[str, str] | None:
        """
        处理 slash command（/skill-name args）

        Returns:
            - None: 不是 slash 命令
            - str: INLINE 模式下返回展开后的用户消息
            - tuple[str, str]: FORK 模式下返回 ("fork", result)
        """
        try:
            from scripts.skill.slash_parser import parse_slash_command
            from scripts.skill.loader import SkillLoader
        except ImportError:
            try:
                from skill.slash_parser import parse_slash_command
                from skill.loader import SkillLoader
            except ImportError:
                return None

        # 解析 slash 命令
        cmd = parse_slash_command(user_message)
        if cmd is None:
            return None

        # 查找 skill
        loader = SkillLoader()
        loader.discover_skills()

        skill = loader.get_skill(cmd.skill_name)
        if skill is None:
            # Skill 不存在，不拦截，继续正常处理
            logger.warning(f"Skill not found: {cmd.skill_name}")
            return None

        skill.config.content

        # 展开 skill 内容
        expanded_content = skill.config.expand_content(cmd.arguments)

        if skill.config.context.value == "fork":
            # FORK 模式：使用子代理执行
            try:
                from scripts.subagent.executor import get_subagent_executor
                from scripts.subagent.types import SubagentType

                executor = get_subagent_executor()

                # 获取 subagent type
                try:
                    subagent_type = SubagentType.from_string(skill.config.agent)
                except ValueError:
                    subagent_type = SubagentType.GENERAL_PURPOSE

                # 执行子代理
                agent_info = await executor.execute(
                    prompt=expanded_content,
                    subagent_type=subagent_type,
                    description=f"Skill: {skill.config.name}",
                )

                result = agent_info.result if agent_info.result else agent_info.error or "No result"
                return ("fork", result)
            except Exception as e:
                logger.error(f"Fork skill execution failed: {e}")
                return None
        else:
            # INLINE 模式：展开到用户消息中
            # 将 skill 内容作为上下文添加到用户消息
            inline_message = f"[使用技能: {skill.config.name}]\n\n{expanded_content}"
            return inline_message

    async def run_stream(self, user_message: str) -> AsyncGenerator[StreamEvent, None]:
        """
        运行 Agent 处理用户消息（流式版本）

        Yields:
            StreamEvent: 逐步输出的事件流
        """
        # 注册为当前 Agent（用于进程退出时保存）
        _set_current_agent(self)

        # StructuredIO 事件发送辅助方法（非阻塞）
        async def _emit_structured_event(event_type: str, content: str = "", **kwargs):
            """通过 StructuredIO 发送事件（如果有配置）"""
            if self._structured_io:
                await self._structured_io.send_stream_event(event_type, content, **kwargs)

        # 重置 Session 级别的显式保存标志
        self._session_explicit_save_detected = False

        # StructuredIO 启动（在 try 之外，确保 finally 可以 stop）
        if self._structured_io:
            await self._structured_io.start()

        try:
            # 创建或恢复 Session
            if self._session_manager and not self._session_id:
                session = self._session_manager.get_or_create_default()
                self._session_id = session.id
                self._load_session(self._session_id)
        except Exception:
            pass  # Session 加载失败不影响主流程

        # 初始化 system prompt
        if not self.messages:
            self._add_message_with_index(self._build_system_message())

        # 触发 SessionStart Hook
        session_start_context = {
            "session_id": id(self),
            "timestamp": datetime.now().isoformat(),
        }
        await self._trigger_hook("SessionStart", session_start_context)

        # ========== Slash Command 检测 ==========
        processed_message = await self._handle_slash_command(user_message)
        if processed_message:
            if isinstance(processed_message, tuple):
                # FORK 模式：返回子代理执行结果
                fork_result = processed_message[1]
                _set_current_agent(None)
                yield StreamEvent(type="done", content=fork_result)
                await _emit_structured_event("done", content=fork_result)
                return
            # INLINE 模式：使用展开后的消息
            user_message = processed_message
        # ========== Slash Command 结束 ==========

        # 添加用户消息
        user_context = {"user_message": user_message}
        await self._trigger_hook("UserPromptSubmit", user_context)
        self._add_message_with_index(Message(role="user", content=user_message))

        # 更新 SessionMemory
        self._update_session_memory("user_message", content=user_message)

        # 检测用户是否显式要求保存记忆（Session 级别互斥）
        if self._memory_extractor:
            try:
                from .memory.extract_memories import detect_explicit_save
                if detect_explicit_save(user_message):
                    self._session_explicit_save_detected = True
                    logger.info("Detected explicit save in user message, will skip auto extraction")
            except ImportError:
                pass

        # 注入相关记忆到系统提示（首次对话时）
        if self.turn_count == 0 and self._memory_retriever:
            memory_context = self._get_memory_context(user_message)
            if memory_context:
                # 将记忆注入到系统消息之后的第一条消息
                memory_msg = Message(role="system", content=f"[记忆上下文]\n{memory_context}")
                self.messages.insert(1, memory_msg)

        # 重置轮次计数（每次新对话独立计数）
        self.turn_count = 0

        # ========== Multi-Agent 复杂度路由 ==========
        # 检查是否启用 Multi-Agent 模式
        if self.config.multi_agent_enabled:
            from scripts.multi_agent import MultiAgentExecutor, ComplexityLevel

            # 创建 Multi-Agent 执行器
            multi_executor = MultiAgentExecutor(
                llm_client=self._get_llm_client_for_multi_agent(),
                session_manager=self._session_manager
            )

            # 进行路由决策
            route_result = await multi_executor.router.route(user_message)
            logger.info(f"[Multi-Agent] 路由决策: {route_result.level} (置信度: {route_result.confidence})")

            logger.debug(f"[ROUTE] level={route_result.level}, confidence={route_result.confidence}")

            # L2/L3 直接委托给 Multi-Agent 执行器
            if route_result.level != ComplexityLevel.L1:
                logger.info(f"[Multi-Agent] 委托给 MultiAgentExecutor 处理 {route_result.level} 级任务")
                async for event in multi_executor.run_stream(user_message):
                    # 转换 Multi-Agent 事件为 Agent 事件
                    yield self._convert_multi_agent_event(event)
                _set_current_agent(None)
                return
            else:
                # L1: 不委托，继续走正常 Agent loop（含工具系统）
                logger.info(f"[Multi-Agent] L1 任务，继续走正常 Agent loop")
        # ========== Multi-Agent 路由结束 ==========

        logger.debug(f"[AGENT-LOOP] entering main loop, multi_agent={self.config.multi_agent_enabled}")

        while self.turn_count < self.config.max_turns:
            self.turn_count += 1

            # 尝试自动压缩（在构建消息之前执行）
            try:
                await self._trigger_hook("PreCompact", {"token_count": sum(self._count_tokens(m.content) for m in self.messages)})
                await self._compress_if_needed()
            except Exception as e:
                logger.error(f"Pre-compact hook/compression error: {e}")

            # 构建 API 消息格式
            try:
                api_messages = self._build_api_messages()
                tools = self._build_tools_list()
            except Exception as e:
                yield StreamEvent(type="tool_error", error=f"[构建消息失败] {e}")
                yield StreamEvent(type="done", content=f"[错误] {e}")
                await _emit_structured_event("done", content=f"[错误] {e}")
                _set_current_agent(None)
                return

            # 通知 LLM 思考中
            yield StreamEvent(type="thinking", content="正在思考...")
            await _emit_structured_event("thinking", content="正在思考...")

            # 触发 LLMStart Hook
            await self._trigger_hook("LLMStart", {
                "model": self.config.model,
                "message_count": len(api_messages),
                "tools_count": len(tools) if tools else 0,
            })

            # 调用 LLM
            try:
                logger.debug(f"[CALL-LLM] tools={len(tools) if tools else 0}, turn={self.turn_count}")
                response = call_llm(
                    api_messages,
                    model=self.config.model,
                    api_url=self.config.api_url,
                    temperature=self.config.temperature,
                    timeout=self.config.timeout,
                    api_key=self.config.api_key,
                    tools=tools,
                )

                # 触发 LLMComplete Hook
                await self._trigger_hook("LLMComplete", {
                    "model": self.config.model,
                    "response_length": len(str(response)),
                })

                # 提取并保存 token usage
                self._last_usage = extract_usage_from_response(response)
                # 累加到总用量
                if self._last_usage:
                    self._total_usage.input_tokens += self._last_usage.input_tokens
                    self._total_usage.output_tokens += self._last_usage.output_tokens
                    self._total_usage.total_tokens += self._last_usage.total_tokens
                    # 发送 usage 事件更新进度条
                    yield StreamEvent(
                        type="usage",
                        usage={
                            "input_tokens": self._last_usage.input_tokens,
                            "output_tokens": self._last_usage.output_tokens,
                            "total_tokens": self._last_usage.total_tokens,
                        }
                    )
            except Exception as e:
                yield StreamEvent(type="tool_error", error=f"[LLM 调用失败] {e}")
                yield StreamEvent(type="done", content=f"[LLM 调用失败] {e}")
                await _emit_structured_event("done", content=f"[LLM 调用失败] {e}")

                # 尝试响应式压缩（如果错误是 context length 相关）
                if "too long" in str(e).lower() or "context" in str(e).lower() or "token" in str(e).lower():
                    from .compact.compact_manager import CompactConfig
                    from .compact.reactive_compact import try_reactive_compact

                    config = CompactConfig()
                    compact_result = await try_reactive_compact(api_messages, e, config)
                    if compact_result.success:
                        self._apply_compaction(compact_result)
                        yield StreamEvent(type="tool_result", tool="compact", success=True, data={"reactive_compact": True})

                _set_current_agent(None)
                return

            # 解析 LLM 响应的所有 content blocks
            try:
                blocks = parse_content_blocks(response)
                logger.debug(f"[PARSED] {len(blocks)} blocks: {[b.get('type') for b in blocks]}")
            except Exception as e:
                yield StreamEvent(type="tool_error", error=f"[解析响应失败] {e}\n响应: {str(response)[:300]}")
                yield StreamEvent(type="done", content=f"[解析错误] {e}")
                await _emit_structured_event("done", content=f"[解析错误] {e}")
                _set_current_agent(None)
                return

            if not blocks:
                # content 为空或解析失败，尝试把整个 response 作为文本输出
                raw = json.dumps(response, ensure_ascii=False)[:300]
                # 尝试从 response 的其他字段提取内容
                text = (
                    response.get("text") or
                    response.get("content", "") if isinstance(response.get("content"), str) else
                    response.get("message", {}).get("content", "") if isinstance(response.get("message"), dict) else
                    raw
                )
                if text and isinstance(text, str) and text.strip():
                    self._add_message_with_index(Message(role="assistant", content=text))
                    yield StreamEvent(type="text", content=text)
                    await _emit_structured_event("text", content=text)
                else:
                    yield StreamEvent(type="text", content=f"（无内容，请检查API响应）{raw}")
                    await _emit_structured_event("text", content=f"（无内容，请检查API响应）{raw}")
                yield StreamEvent(type="done", content="")
                await _emit_structured_event("done", content="")
                _set_current_agent(None)
                return

            # 收集所有 text 和 tool_use blocks
            has_tool_calls = False
            assistant_message = None
            tool_calls_list = []
            text_blocks = []

            for block in blocks:
                block_type = block.get("type", "")

                if block_type == "text" or block_type == "thinking_text":
                    text_blocks.append(block)
                elif block_type == "tool_use":
                    has_tool_calls = True
                    actual_id = block.get("id", f"call_{block.get('name', '')}_{self.turn_count}")
                    tool_calls_list.append({
                        "id": actual_id,
                        "name": block.get("name", ""),
                        "input": block.get("input", {}),
                    })

            # 输出所有文本 blocks
            # 如果有 tool_calls，所有文本合并到一个 assistant message 中
            # 否则每个文本块独立存储
            for block in text_blocks:
                text = block.get("text", "").strip()
                if text:
                    yield StreamEvent(type="text", content=text)
                    await _emit_structured_event("text", content=text)
                    if has_tool_calls:
                        # 合并文本到同一个 assistant message
                        if assistant_message is None:
                            assistant_message = Message(role="assistant", content=text)
                            self._add_message_with_index(assistant_message)
                        else:
                            assistant_message.content += "\n" + text
                    else:
                        msg = Message(role="assistant", content=text)
                        self._add_message_with_index(msg)
                        if assistant_message is None:
                            assistant_message = msg

            # 如果有 tool_use，确保有 assistant message 并添加 tool_calls
            if tool_calls_list:
                if assistant_message is None:
                    assistant_message = Message(
                        role="assistant",
                        content="",
                        tool_calls=tool_calls_list,
                    )
                    self._add_message_with_index(assistant_message)
                else:
                    assistant_message.tool_calls = tool_calls_list

                # 并行执行所有工具调用
                def yield_event(event):
                    yield event

                results = await self._execute_tools_parallel(tool_calls_list, yield_func=yield_event)

                # 检查是否需要授权
                auth_callback = self.config.auth_callback
                needs_auth = [(tc, r) for tc, r in results 
                              if not r.success and r.auth_required]
                
                if needs_auth and auth_callback:
                    auth_needed_calls = []
                    for tc, result in needs_auth:
                        tool_name, args, reason = result.auth_required
                        granted = auth_callback(tool_name, args)
                        if granted:
                            # 用户授权，临时允许该操作
                            pattern = f"{tool_name}({args.get('command', '*')})"
                            logger.info(f"[DEBUG] Adding allow rule: {pattern}")
                            self.config.permission_engine.allow(
                                pattern,
                                f"用户授权: {reason}"
                            )
                            auth_needed_calls.append(tc)
                        else:
                            # 用户拒绝，更新结果
                            idx = tool_calls_list.index(tc)
                            results[idx] = (tc, ToolResult(success=False, data=None, error="用户拒绝授权"))

                    # 只重新执行需要授权且被允许的工具调用
                    if auth_needed_calls:
                        auth_results = await self._execute_tools_parallel(auth_needed_calls, yield_func=yield_event)
                        for tc, result in auth_results:
                            idx = tool_calls_list.index(tc)
                            results[idx] = (tc, result)

                # 将工具结果添加到消息
                for tc, result in results:
                    tool_call_id = tc.get("id", "")
                    tool_name = tc.get("name", "")

                    # 发送 tool_result 事件
                    yield StreamEvent(
                        type="tool_result",
                        tool=tool_name,
                        success=result.success,
                        data=result.data,
                        error=getattr(result, "error", "") or "",
                    )

                    # 工具结果加入 messages
                    tool_result_text = self._format_tool_result(result)
                    self._add_message_with_index(Message(
                        role="tool",
                        content=tool_result_text,
                        tool_call_id=tool_call_id,
                    ))

                    # 更新 SessionMemory
                    tool_args = tc.get("input", {})
                    if result.success:
                        self._update_session_memory("tool_success", tool_name=tool_name, tool_args=tool_args, tool_result=result)
                    else:
                        error_msg = getattr(result, "error", "") or ""
                        if error_msg:
                            self._update_session_memory("tool_error", tool_name=tool_name, error=error_msg)

            # Micro-Compact: 工具执行后检查是否需要微压缩
            try:
                await self._trigger_hook("PreMicroCompact", {"message_count": len(self.messages)})
                self._micro_compact_if_needed()
            except Exception as e:
                logger.error(f"Micro-compact error: {e}")

            # 如果本轮有工具调用，LLM 下一轮会继续（给出总结或更多工具）
            # 继续循环获取 LLM 的下一轮响应
            if has_tool_calls:
                continue

            # 没有工具调用，检查 stop_reason
            stop_reason = response.get("stop_reason", "")
            if stop_reason in ("end_turn", "stop_sequence", None, ""):
                # 保存 Session 记忆
                if self._session_memory:
                    try:
                        self._session_memory.save()
                    except Exception as e:
                        logger.error(f"Failed to save session memory: {e}")
                # 触发自动记忆提取（确保异常不会中断流）
                try:
                    await self._trigger_auto_memory_extraction()
                except Exception as e:
                    logger.error(f"Memory extraction error: {e}")
                # 输出 token 使用信息
                self._print_usage()
                # 保存 Session
                self._save_session_if_needed()
                yield StreamEvent(type="done", content="")
                await _emit_structured_event("done", content="")
                _set_current_agent(None)
                return

            # 其他 stop_reason，继续循环
            continue

        # 保存 Session 记忆
        if self._session_memory:
            try:
                self._session_memory.save()
            except Exception as e:
                logger.error(f"Failed to save session memory: {e}")

        # 触发自动记忆提取（即使达到最大轮次也尝试提取）
        await self._trigger_auto_memory_extraction()

        # 触发 SessionEnd Hook
        await self._trigger_hook("SessionEnd", {
            "session_id": id(self),
            "turn_count": self.turn_count,
            "timestamp": datetime.now().isoformat(),
        })
        # 输出 token 使用信息
        self._print_usage()
        # 保存 Session
        self._save_session_if_needed()
        yield StreamEvent(type="done", content="达到最大轮次限制")
        await _emit_structured_event("done", content="达到最大轮次限制")

        # StructuredIO 停止
        if self._structured_io:
            await self._structured_io.stop()

        _set_current_agent(None)


def create_agent(
    tools: list[BaseTool],
    permission_engine: PermissionEngine | None = None,
    config: AgentConfig | None = None,
) -> Agent:
    """创建 Agent 的便捷函数"""
    for tool in tools:
        get_registry().register(tool)

    if config is None:
        config = AgentConfig(
            permission_engine=permission_engine,
            api_key=LLM_API_KEY,
            api_url=LLM_API_URL,
            model=LLM_MODEL,
        )
    else:
        if permission_engine is not None:
            config.permission_engine = permission_engine
    return Agent(config)
