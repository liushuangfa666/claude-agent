"""
Lockfile - 跨平台进程锁，防止重复启动
"""
from __future__ import annotations

import os
import sys
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional


class Lockfile:
    """
    进程锁文件，防止重复启动

    使用平台特定实现:
    - Windows: os.open 独占模式
    - Unix: fcntl.flock
    """

    LOCK_DIR = tempfile.gettempdir()
    LOCK_FILE = os.path.join(LOCK_DIR, "claude-agent.lock")

    def __init__(self, lock_file: "Optional[str]" = None) -> None:
        """
        初始化 Lockfile

        Args:
            lock_file: 自定义锁文件路径，默认使用临时目录下的 claude-agent.lock
        """
        self.lock_file = lock_file or self.LOCK_FILE
        self._handle: "Optional[int]" = None
        self._owned = False

    def acquire(self) -> bool:
        """
        获取锁

        Returns:
            True 获取成功，False 锁已被其他进程持有
        """
        try:
            if sys.platform == "win32":
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
                self._handle = os.open(self.lock_file, flags)
                os.write(self._handle, str(os.getpid()).encode("utf-8"))
                self._owned = True
            else:
                import fcntl

                self._handle = open(self.lock_file, "w")
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._handle.write(str(os.getpid()))
                self._handle.flush()
                self._owned = True

            return True

        except (OSError, IOError):
            self._handle = None
            self._owned = False
            return False

    def release(self) -> None:
        """释放锁"""
        if self._handle is not None:
            try:
                if sys.platform == "win32":
                    os.close(self._handle)
                else:
                    import fcntl

                    fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
                    self._handle.close()
            except Exception:
                pass
            finally:
                self._handle = None
                self._owned = False

        try:
            if os.path.exists(self.lock_file):
                os.remove(self.lock_file)
        except OSError:
            pass

    def is_locked(self) -> bool:
        """检查锁是否被持有"""
        return self._owned

    def __enter__(self) -> "Lockfile":
        """上下文管理器入口"""
        if not self.acquire():
            raise RuntimeError(
                "Failed to acquire lock: another instance may be running"
            )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口"""
        self.release()
