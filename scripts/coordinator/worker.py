"""
WorkerAgent - Worker 代理
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from .constants import AGENT_TYPE_WORKER, ASYNC_AGENT_ALLOWED_TOOLS, TEAM_LEAD_NAME
from .mailbox import TeamMailbox, get_mailbox
from .team import Message as TeamMessage
from .team import Teammate, create_agent_id


@dataclass
class WorkerContext:
    team_name: str
    agent_id: str
    mailbox: TeamMailbox
    config: dict[str, Any] = field(default_factory=dict)


class WorkerAgent:
    """Worker Agent - 团队中的执行者"""

    def __init__(
        self,
        config: Any = None,
        team_name: str = "",
        agent_name: str = "",
        model: str = "MiniMax-M2",
        context: WorkerContext | None = None,
    ):
        self._agent_config = config
        self.team_name = team_name
        self.agent_id = create_agent_id(AGENT_TYPE_WORKER)
        self.agent_name = agent_name or self.agent_id
        self.model = model
        self.context = context or WorkerContext(
            team_name=team_name,
            agent_id=self.agent_id,
            mailbox=get_mailbox(),
        )
        self._messages: list = []
        self._available_tools = self._filter_tools()

    def _filter_tools(self) -> list:
        try:
            from ..tool import get_registry
        except ImportError:
            from tool import get_registry

        registry = get_registry()
        all_tools = registry.all()

        allowed_tools = []
        for tool_def in all_tools:
            if tool_def.name in ASYNC_AGENT_ALLOWED_TOOLS:
                tool = registry.get(tool_def.name)
                if tool is not None:
                    allowed_tools.append(tool)

        return allowed_tools

    async def check_mailbox(self) -> list[TeamMessage]:
        return self.context.mailbox.receive(
            team_name=self.team_name,
            agent_id=self.agent_id,
        )

    async def run_with_mailbox_check(self, user_message: str) -> str:
        """Run agent with periodic mailbox checks for incoming messages."""
        final_text = ""

        if not hasattr(self, '_messages'):
            self._messages = []

        self.turn_count = 0
        max_turns = getattr(self._agent_config, 'max_turns', 20) if self._agent_config else 20

        while self.turn_count < max_turns:
            self.turn_count += 1

            messages = await self.check_mailbox()
            if messages:
                for msg in messages:
                    if msg.message_type == "shutdown_request":
                        await self.handle_shutdown(msg)
                        return final_text

            await asyncio.sleep(0.1)

        return final_text

    async def handle_shutdown(self, message: TeamMessage) -> None:
        self.context.mailbox.receive_and_clear(
            team_name=self.team_name,
            agent_id=self.agent_id,
        )
        team = self.context.mailbox.storage.load_team(self.team_name)
        if team:
            member = team.get_member(self.agent_id)
            if member:
                member.status = "stopped"
                self.context.mailbox.storage.save_team(team)

    def get_teammate_info(self) -> Teammate:
        return Teammate(
            agent_id=self.agent_id,
            name=self.agent_name,
            agent_type=AGENT_TYPE_WORKER,
            model=self.model,
            color="",
            status="running",
            mailbox=[],
        )


class TeamLeadAgent(WorkerAgent):
    """Team Lead Agent"""

    def __init__(
        self,
        config: Any = None,
        team_name: str = "",
        agent_name: str = TEAM_LEAD_NAME,
        model: str = "MiniMax-M2",
    ):
        super().__init__(config, team_name, agent_name, model)
        self.agent_type = "coordinator"

    def _filter_tools(self) -> list:
        try:
            from ..tool import get_registry
        except ImportError:
            from tool import get_registry

        return list(get_registry().all())
