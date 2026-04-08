"""
记忆梦境服务

将日志蒸馏为持久记忆。
支持 LLM 增强的智能分析。
"""
import json
import logging
import urllib.request
from pathlib import Path
from typing import Any

from .memory_store import MemoryStore
from .types import MemoryType

logger = logging.getLogger(__name__)

DEFAULT_LLM_API_URL = "https://api.minimaxi.com/anthropic/v1/messages"
DEFAULT_LLM_MODEL = "MiniMax-M2.7"


class MemoryDream:
    """记忆梦境服务 - 日志蒸馏为持久记忆"""

    def __init__(
        self,
        store: MemoryStore | None = None,
        llm_api_url: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ):
        """
        初始化记忆梦境服务。

        Args:
            store: 记忆存储实例
            llm_api_url: LLM API URL（可选，不提供则使用规则分析）
            llm_api_key: LLM API 密钥
            llm_model: LLM 模型名称
        """
        self._store = store or MemoryStore()
        self._llm_api_url = llm_api_url or DEFAULT_LLM_API_URL
        self._llm_api_key = llm_api_key or ""
        self._llm_model = llm_model or DEFAULT_LLM_MODEL
        self._llm_available = bool(llm_api_key)

    @property
    def llm_available(self) -> bool:
        """检查 LLM 是否可用"""
        return self._llm_available

    async def distill_session_log(
        self,
        session_log: str,
        project_name: str | None = None,
        use_llm: bool = True,
    ) -> list[dict]:
        """
        将会话日志蒸馏为潜在的记忆条目。

        Args:
            session_log: 会话日志内容
            project_name: 可选的项目名称
            use_llm: 是否优先使用 LLM（如果可用）

        Returns:
            建议创建的记忆条目列表
        """
        if use_llm and self._llm_available:
            try:
                return await self.distill_with_llm(session_log, project_name)
            except Exception as e:
                logger.warning(f"LLM distillation failed, falling back to rules: {e}")

        return await self._distill_with_rules(session_log, project_name)

    async def distill_with_llm(
        self,
        session_log: str,
        project_name: str | None = None,
    ) -> list[dict]:
        """
        使用 LLM 智能分析会话日志，提取记忆条目。

        Args:
            session_log: 会话日志内容
            project_name: 可选的项目名称

        Returns:
            LLM 提取的记忆条目列表
        """
        prompt = self._build_llm_prompt(session_log, project_name)

        try:
            response_text = await self._call_llm_async(prompt)
            return self._parse_llm_response(response_text, project_name)
        except Exception as e:
            logger.error(f"LLM distillation error: {e}")
            raise

    def _build_llm_prompt(self, session_log: str, project_name: str | None) -> str:
        """构建 LLM 分析提示词"""
        project_context = f"项目: {project_name}" if project_name else "通用会话"

        return f"""你是一个记忆蒸馏专家。请分析以下会话日志，提取有价值的持久记忆。

{project_context}

会话日志:
---
{session_log}
---

请分析上述日志，识别以下类型的记忆条目：

1. **项目知识 (PROJECT)**: 项目特定的工作流程、文件结构、技术栈、约定俗成
2. **经验反馈 (FEEDBACK)**: 成功经验、失败教训、需要避免的问题
3. **错误模式 (ERROR)**: 遇到的错误及其解决方案
4. **上下文 (CONTEXT)**: 当前工作状态、未完成的任务、待处理的问题

请以 JSON 数组格式返回记忆条目列表，每个条目包含：
- type: 记忆类型 (PROJECT/FEEDBACK/ERROR/CONTEXT)
- name: 简洁的记忆名称
- description: 简短描述
- content: 详细记忆内容（包含具体信息）

只返回有价值的记忆，忽略普通的对话内容。

JSON 响应:"""

    async def _call_llm_async(self, prompt: str) -> str:
        """异步调用 LLM API"""
        anthropic_message = {"role": "user", "content": prompt}

        data = {
            "model": self._llm_model,
            "messages": [anthropic_message],
            "max_tokens": 150000,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._llm_api_key}",
            "anthropic-version": "2023-06-01",
            "anthropic-dangerous-direct-browser-access": "true",
        }

        req = urllib.request.Request(
            self._llm_api_url,
            data=json.dumps(data).encode("utf-8"),
            headers=headers,
        )

        loop = __import__("asyncio").get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: urllib.request.urlopen(req, timeout=60)
        )
        result = json.loads(resp.read().decode("utf-8"))

        return result.get("content", [{}])[0].get("text", "")

    def _parse_llm_response(self, response: str, project_name: str | None) -> list[dict]:
        """解析 LLM 响应，提取记忆条目"""
        suggestions = []

        try:
            json_start = response.find("[")
            json_end = response.rfind("]") + 1

            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]
                items = json.loads(json_str)

                for item in items:
                    mem_type_str = item.get("type", "PROJECT").upper()
                    try:
                        mem_type = MemoryType(mem_type_str)
                    except ValueError:
                        mem_type = MemoryType.PROJECT

                    suggestions.append({
                        "type": mem_type,
                        "name": item.get("name", f"{project_name or 'Session'} memory"),
                        "description": item.get("description", ""),
                        "content": item.get("content", ""),
                    })
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}")
            for line in response.split("\n"):
                line = line.strip()
                if line.startswith("-") or line.startswith("*"):
                    content = line[1:].strip()
                    if content:
                        suggestions.append({
                            "type": MemoryType.PROJECT,
                            "name": content[:50],
                            "description": "Extracted from session",
                            "content": content,
                        })

        return suggestions

    async def _distill_with_rules(
        self,
        session_log: str,
        project_name: str | None = None,
    ) -> list[dict]:
        """
        使用规则分析会话日志（fallback 方案）。

        Args:
            session_log: 会话日志内容
            project_name: 可选的项目名称

        Returns:
            基于规则提取的记忆条目列表
        """
        suggestions = []

        lines = session_log.split('\n')
        current_section = None
        section_content = []

        for line in lines:
            if line.startswith('# '):
                if current_section and section_content:
                    suggestion = self._analyze_section(
                        current_section,
                        '\n'.join(section_content),
                        project_name,
                    )
                    if suggestion:
                        suggestions.append(suggestion)

                current_section = line[2:].strip()
                section_content = []
            else:
                section_content.append(line)

        if current_section and section_content:
            suggestion = self._analyze_section(
                current_section,
                '\n'.join(section_content),
                project_name,
            )
            if suggestion:
                suggestions.append(suggestion)

        return suggestions

    def _analyze_section(
        self,
        section_title: str,
        content: str,
        project_name: str | None,
    ) -> dict | None:
        """分析单个部分，生成记忆建议"""
        if not content.strip():
            return None

        section_lower = section_title.lower()

        if 'learnings' in section_lower or 'what to avoid' in section_lower:
            return {
                "type": MemoryType.FEEDBACK,
                "name": f"{project_name or 'Session'} learnings" if project_name else "learnings",
                "description": "Key learnings from session",
                "content": content,
            }
        elif 'workflow' in section_lower or 'worklog' in section_lower:
            return {
                "type": MemoryType.PROJECT,
                "name": f"{project_name or 'Session'} workflow" if project_name else "workflow",
                "description": "Project workflow patterns",
                "content": content,
            }
        elif 'files' in section_lower or 'functions' in section_lower:
            return {
                "type": MemoryType.PROJECT,
                "name": f"{project_name or 'Session'} file structure" if project_name else "file structure",
                "description": "Important files and their purposes",
                "content": content,
            }
        elif 'errors' in section_lower or 'corrections' in section_lower:
            return {
                "type": MemoryType.FEEDBACK,
                "name": f"{project_name or 'Session'} error patterns" if project_name else "error patterns",
                "description": "Errors encountered and solutions",
                "content": content,
            }

        return None

    async def create_memories_from_log(
        self,
        session_log: str,
        project_name: str | None = None,
        use_llm: bool = True,
    ) -> list[Path]:
        """
        从会话日志创建记忆。

        Args:
            session_log: 会话日志内容
            project_name: 可选的项目名称
            use_llm: 是否优先使用 LLM

        Returns:
            创建的记忆文件路径列表
        """
        suggestions = await self.distill_session_log(session_log, project_name, use_llm)

        created = []
        for suggestion in suggestions:
            path = self._store.write_memory(
                content=suggestion.get("content", ""),
                memory_type=suggestion.get("type"),
                name=suggestion.get("name"),
                description=suggestion.get("description"),
            )
            created.append(path)
            logger.info(f"Created memory: {path}")

        return created
