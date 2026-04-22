"""
Session 管理器
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

from .metadata import SessionMetadata
from .store import SessionStore

logger = logging.getLogger(__name__)


class SessionManager:
    """会话管理器"""

    SESSION_DIR = Path.home() / ".claude-agent" / "sessions"

    def __init__(self, store: SessionStore | None = None):
        self._store = store or SessionStore(self.SESSION_DIR)

    def create_session(
        self,
        name: str,
        parent_id: str | None = None,
        worktree_path: str | None = None,
        root: str | None = None,
    ) -> SessionMetadata:
        session_id = str(uuid.uuid4())[:8]
        now = datetime.now()

        metadata = SessionMetadata(
            id=session_id,
            name=name,
            created_at=now,
            updated_at=now,
            worktree_path=worktree_path,
            parent_session_id=parent_id,
            root=root or os.getcwd(),
        )

        self._store.save_metadata(metadata)
        self._store.save_messages(session_id, [])
        logger.info(f"Created session {session_id} ({name})")

        return metadata

    def get_session(self, session_id: str) -> SessionMetadata | None:
        return self._store.load_metadata(session_id)

    def list_sessions(self) -> list[SessionMetadata]:
        return self._store.list_sessions()

    def fork_session(self, parent_id: str, new_name: str) -> SessionMetadata | None:
        parent = self._store.load_metadata(parent_id)
        if not parent:
            logger.error(f"Parent session {parent_id} not found")
            return None

        new_session = self.create_session(
            name=new_name,
            parent_id=parent_id,
            worktree_path=None,
            root=parent.root,
        )

        messages = self._store.load_messages(parent_id)
        self._store.save_messages(new_session.id, messages)

        logger.info(f"Forked session {parent_id} -> {new_session.id} ({new_name})")
        return new_session

    def save_messages(self, session_id: str, messages: list[dict]) -> None:
        self._store.save_messages(session_id, messages)

    def load_messages(self, session_id: str) -> list[dict]:
        return self._store.load_messages(session_id)

    def delete_session(self, session_id: str) -> bool:
        return self._store.delete_session(session_id)

    def get_or_create_default(self) -> SessionMetadata:
        sessions = self.list_sessions()
        if sessions:
            return sessions[0]
        return self.create_session(name="default")

    def resume_session(self, session_id: str) -> SessionMetadata | None:
        return self.get_session(session_id)

    def create_worktree_session(
        self,
        name: str,
        branch: str | None = None,
        parent_id: str | None = None,
    ) -> SessionMetadata | None:
        import subprocess

        worktree_name = name.replace(" ", "-").lower()
        worktree_path = self.SESSION_DIR / "worktrees" / worktree_name

        try:
            cmd = ["git", "worktree", "add"]
            if branch:
                cmd.extend(["-b", branch])
            cmd.append(str(worktree_path))

            result = subprocess.run(
                cmd,
                cwd=self.SESSION_DIR.parent,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.error(f"Failed to create worktree: {result.stderr}")
                return None

            metadata = self.create_session(
                name=name,
                parent_id=parent_id,
                worktree_path=str(worktree_path),
                root=str(worktree_path),
            )

            logger.info(f"Created worktree session {metadata.id} at {worktree_path}")
            return metadata

        except Exception as e:
            logger.error(f"Failed to create worktree session: {e}")
            return None
