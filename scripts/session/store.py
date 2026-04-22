"""
Session 存储服务
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from .metadata import SessionMetadata

logger = logging.getLogger(__name__)


class SessionStore:
    """会话存储服务"""

    def __init__(self, base_dir: Path | None = None):
        if base_dir is None:
            base_dir = Path.home() / ".claude-agent" / "sessions"
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._worktrees_dir = self._base_dir / "worktrees"
        self._worktrees_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_dir(self, session_id: str) -> Path:
        session_dir = self._base_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def _get_lock(self, session_id: str):
        from filelock import FileLock
        session_dir = self._get_session_dir(session_id)
        return FileLock(session_dir / ".lock", timeout=10)

    def _get_metadata_path(self, session_id: str) -> Path:
        return self._get_session_dir(session_id) / "metadata.json"

    def _get_messages_path(self, session_id: str) -> Path:
        return self._get_session_dir(session_id) / "messages.json"

    def save_metadata(self, metadata: SessionMetadata) -> None:
        lock = self._get_lock(metadata.id)
        with lock:
            metadata.updated_at = datetime.now()
            path = self._get_metadata_path(metadata.id)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(metadata.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"Saved metadata for session {metadata.id}")

    def load_metadata(self, session_id: str) -> SessionMetadata | None:
        path = self._get_metadata_path(session_id)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return SessionMetadata.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load metadata for session {session_id}: {e}")
            return None

    def save_messages(self, session_id: str, messages: list[dict]) -> None:
        lock = self._get_lock(session_id)
        with lock:
            path = self._get_messages_path(session_id)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(messages, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(messages)} messages for session {session_id}")

    def load_messages(self, session_id: str) -> list[dict]:
        path = self._get_messages_path(session_id)
        if not path.exists():
            return []
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load messages for session {session_id}: {e}")
            return []

    def delete_session(self, session_id: str) -> bool:
        lock = self._get_lock(session_id)
        with lock:
            session_dir = self._get_session_dir(session_id)
            if session_dir.exists():
                import shutil
                shutil.rmtree(session_dir)
                logger.info(f"Deleted session {session_id}")
                return True
            return False

    def list_sessions(self) -> list[SessionMetadata]:
        sessions = []
        for session_dir in self._base_dir.iterdir():
            if session_dir.is_dir() and session_dir.name != "worktrees":
                metadata = self.load_metadata(session_dir.name)
                if metadata:
                    sessions.append(metadata)
        return sorted(sessions, key=lambda s: s.updated_at, reverse=True)
