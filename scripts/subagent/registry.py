"""
子代理注册表 - Subagent Registry
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .types import SubagentType


@dataclass
class SubagentInfo:
    """子代理信息"""
    agent_id: str
    name: str
    subagent_type: SubagentType
    description: str
    prompt: str
    status: str = "pending"
    messages: list[dict] = field(default_factory=list)
    result: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    ended_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> int | None:
        """获取运行时间（毫秒）"""
        if self.started_at is None:
            return None
        end = self.ended_at or time.time()
        return int((end - self.started_at) * 1000)

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    @property
    def is_completed(self) -> bool:
        return self.status == "completed"

    def to_dict(self) -> dict:
        return {
            "agentId": self.agent_id,
            "name": self.name,
            "subagentType": self.subagent_type.value,
            "description": self.description,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "durationMs": self.duration_ms,
            "createdAt": datetime.fromtimestamp(self.created_at).isoformat(),
            "metadata": self.metadata,
        }


class SubagentRegistry:
    """子代理注册表"""

    def __init__(self):
        self._agents: dict[str, SubagentInfo] = {}
        self._id_counter: int = 0

    def create(
        self,
        name: str,
        subagent_type: SubagentType,
        description: str = "",
        prompt: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SubagentInfo:
        self._id_counter += 1
        agent_id = f"subagent_{self._id_counter}_{uuid.uuid4().hex[:8]}"

        info = SubagentInfo(
            agent_id=agent_id,
            name=name,
            subagent_type=subagent_type,
            description=description,
            prompt=prompt,
            metadata=metadata or {},
        )

        self._agents[agent_id] = info
        return info

    def get(self, agent_id: str) -> SubagentInfo | None:
        return self._agents.get(agent_id)

    def list(self, status: str | None = None) -> list[SubagentInfo]:
        agents = list(self._agents.values())

        if status:
            agents = [a for a in agents if a.status == status]

        agents.sort(key=lambda a: a.created_at, reverse=True)
        return agents

    def update_status(
        self,
        agent_id: str,
        status: str,
        result: str | None = None,
        error: str | None = None,
    ) -> bool:
        info = self._agents.get(agent_id)
        if not info:
            return False

        info.status = status

        if status == "running" and info.started_at is None:
            info.started_at = time.time()

        if status in ("completed", "failed", "stopped"):
            info.ended_at = time.time()

        if result is not None:
            info.result = result

        if error is not None:
            info.error = error

        return True

    def remove(self, agent_id: str) -> bool:
        if agent_id in self._agents:
            del self._agents[agent_id]
            return True
        return False

    def clear_completed(self) -> int:
        completed = [
            agent_id
            for agent_id, info in self._agents.items()
            if info.status in ("completed", "failed", "stopped")
        ]

        for agent_id in completed:
            del self._agents[agent_id]

        return len(completed)


_registry = SubagentRegistry()


def get_subagent_registry() -> SubagentRegistry:
    """获取全局子代理注册表"""
    return _registry
