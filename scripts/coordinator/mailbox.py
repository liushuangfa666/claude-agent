"""
Team Mailbox - 消息收件箱
"""
from __future__ import annotations

from datetime import datetime

from .constants import TEAM_MEM_DIR
from .team import Message, Team, TeamStorage

_mailbox: TeamMailbox | None = None


def get_mailbox() -> TeamMailbox:
    global _mailbox
    if _mailbox is None:
        _mailbox = TeamMailbox()
    return _mailbox


class TeamMailbox:
    """团队消息收件箱"""

    def __init__(self, storage_dir: str = TEAM_MEM_DIR):
        self.storage = TeamStorage(storage_dir)
        self._cache: dict[str, Team] = {}

    def _get_team(self, team_name: str) -> Team | None:
        if team_name not in self._cache:
            self._cache[team_name] = self.storage.load_team(team_name)
        return self._cache[team_name]

    def _save_team(self, team: Team) -> None:
        self.storage.save_team(team)
        self._cache[team.name] = team

    def send(
        self,
        team_name: str,
        from_agent: str,
        to_agent: str,
        message: str,
        summary: str,
        message_type: str = "text",
    ) -> bool:
        team = self._get_team(team_name)
        if team is None:
            return False

        msg = Message(
            from_agent=from_agent,
            to_agent=to_agent,
            content=message,
            summary=summary,
            timestamp=datetime.now(),
            message_type=message_type,
        )

        recipient = team.get_member(to_agent)
        if recipient is None:
            return False

        recipient.mailbox.append(msg)
        self._save_team(team)
        return True

    def receive(self, team_name: str, agent_id: str) -> list[Message]:
        team = self._get_team(team_name)
        if team is None:
            return []

        member = team.get_member(agent_id)
        if member is None:
            return []

        return member.mailbox.copy()

    def receive_and_clear(self, team_name: str, agent_id: str) -> list[Message]:
        team = self._get_team(team_name)
        if team is None:
            return []

        member = team.get_member(agent_id)
        if member is None:
            return []

        messages = member.mailbox.copy()
        member.mailbox.clear()
        self._save_team(team)
        return messages

    def broadcast(
        self,
        team_name: str,
        from_agent: str,
        message: str,
        summary: str = "",
    ) -> int:
        team = self._get_team(team_name)
        if team is None:
            return 0

        count = 0
        for member in team.members:
            if member.agent_id == from_agent:
                continue

            msg = Message(
                from_agent=from_agent,
                to_agent=member.agent_id,
                content=message,
                summary=summary or message[:50],
                timestamp=datetime.now(),
                message_type="broadcast",
            )
            member.mailbox.append(msg)
            count += 1

        if count > 0:
            self._save_team(team)
        return count

    def get_unread_count(self, team_name: str, agent_id: str) -> int:
        team = self._get_team(team_name)
        if team is None:
            return 0

        member = team.get_member(agent_id)
        if member is None:
            return 0

        return len(member.mailbox)

    def clear_mailbox(self, team_name: str, agent_id: str) -> int:
        team = self._get_team(team_name)
        if team is None:
            return 0

        member = team.get_member(agent_id)
        if member is None:
            return 0

        count = len(member.mailbox)
        member.mailbox.clear()
        self._save_team(team)
        return count
