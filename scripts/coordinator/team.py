"""
Team 数据模型
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import (
    AGENT_TYPE_WORKER,
    STATUS_RUNNING,
    TEAM_MEM_DIR,
)


@dataclass
class Message:
    from_agent: str
    to_agent: str
    content: str
    summary: str
    timestamp: datetime
    message_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "content": self.content,
            "summary": self.summary,
            "timestamp": self.timestamp.isoformat(),
            "message_type": self.message_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        return cls(
            from_agent=data["from_agent"],
            to_agent=data["to_agent"],
            content=data["content"],
            summary=data["summary"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            message_type=data["message_type"],
        )


@dataclass
class Teammate:
    agent_id: str
    name: str
    agent_type: str
    model: str
    color: str
    status: str = STATUS_RUNNING
    mailbox: list[Message] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "agent_type": self.agent_type,
            "model": self.model,
            "color": self.color,
            "status": self.status,
            "mailbox": [m.to_dict() for m in self.mailbox],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Teammate:
        mailbox = [Message.from_dict(m) for m in data.get("mailbox", [])]
        return cls(
            agent_id=data["agent_id"],
            name=data["name"],
            agent_type=data["agent_type"],
            model=data["model"],
            color=data["color"],
            status=data.get("status", STATUS_RUNNING),
            mailbox=mailbox,
        )


@dataclass
class Team:
    name: str
    lead_agent_id: str
    members: list[Teammate] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    team_file_path: str = ""

    def add_member(self, member: Teammate) -> None:
        self.members.append(member)

    def remove_member(self, agent_id: str) -> bool:
        for i, m in enumerate(self.members):
            if m.agent_id == agent_id:
                self.members.pop(i)
                return True
        return False

    def get_member(self, agent_id: str) -> Teammate | None:
        for m in self.members:
            if m.agent_id == agent_id:
                return m
        return None

    def get_member_by_name(self, name: str) -> Teammate | None:
        for m in self.members:
            if m.name == name:
                return m
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "lead_agent_id": self.lead_agent_id,
            "members": [m.to_dict() for m in self.members],
            "created_at": self.created_at.isoformat(),
            "team_file_path": self.team_file_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Team:
        members = [Teammate.from_dict(m) for m in data.get("members", [])]
        return cls(
            name=data["name"],
            lead_agent_id=data["lead_agent_id"],
            members=members,
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(),
            team_file_path=data.get("team_file_path", ""),
        )


class TeamStorage:
    """团队存储管理"""

    def __init__(self, base_dir: str = TEAM_MEM_DIR):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_team_file(self, team_name: str) -> Path:
        safe_name = team_name.replace("/", "_").replace("\\", "_")
        return self.base_dir / f"{safe_name}.json"

    def save_team(self, team: Team) -> str:
        team.team_file_path = str(self._get_team_file(team.name))
        data = team.to_dict()
        with open(team.team_file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return team.team_file_path

    def load_team(self, team_name: str) -> Team | None:
        file_path = self._get_team_file(team_name)
        if not file_path.exists():
            return None
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            return Team.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def delete_team(self, team_name: str) -> bool:
        file_path = self._get_team_file(team_name)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def list_teams(self) -> list[str]:
        teams = []
        for f in self.base_dir.glob("*.json"):
            teams.append(f.stem)
        return teams

    def team_exists(self, team_name: str) -> bool:
        return self._get_team_file(team_name).exists()


def create_team_id() -> str:
    return f"team_{uuid.uuid4().hex[:8]}"


def create_agent_id(agent_type: str = "worker") -> str:
    prefix = "worker" if agent_type == AGENT_TYPE_WORKER else "coord"
    return f"{prefix}_{uuid.uuid4().hex[:8]}"
