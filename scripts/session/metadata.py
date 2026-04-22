"""
Session 元数据定义
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SessionMetadata:
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    worktree_path: str | None = None
    parent_session_id: str | None = None
    root: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "worktree_path": self.worktree_path,
            "parent_session_id": self.parent_session_id,
            "root": self.root,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionMetadata:
        return cls(
            id=data["id"],
            name=data["name"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            worktree_path=data.get("worktree_path"),
            parent_session_id=data.get("parent_session_id"),
            root=data.get("root", ""),
            metadata=data.get("metadata", {}),
        )
