"""
Web 缓存实现

提供 LRU 缓存功能。
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    """缓存条目"""
    value: Any
    timestamp: float
    size: int


class LRUCache:
    """LRU 缓存实现
    
    支持大小限制（字节）和 TTL（时间）。
    """

    def __init__(
        self,
        max_size_bytes: int = 50 * 1024 * 1024,
        ttl_seconds: int = 900,
    ):
        """
        初始化缓存
        
        Args:
            max_size_bytes: 最大缓存大小（字节）
            ttl_seconds: 缓存过期时间（秒）
        """
        self._max_size = max_size_bytes
        self._ttl = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._current_size = 0
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        """
        获取缓存值
        
        Args:
            key: 缓存键
        
        Returns:
            缓存值，如果不存在或已过期返回 None
        """
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                return None

            if time.time() - entry.timestamp > self._ttl:
                self._remove(key)
                return None

            self._cache.move_to_end(key)

            return entry.value

    def set(self, key: str, value: Any, size: int | None = None) -> None:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            size: 值的估计大小（字节），如果为 None 则自动计算
        """
        if size is None:
            if isinstance(value, dict):
                import json
                size = len(json.dumps(value))
            elif isinstance(value, str):
                size = len(value)
            else:
                size = 1

        with self._lock:
            if key in self._cache:
                self._remove(key)

            while self._current_size + size > self._max_size and self._cache:
                self._remove_oldest()

            entry = CacheEntry(value=value, timestamp=time.time(), size=size)
            self._cache[key] = entry
            self._current_size += size
            self._cache.move_to_end(key)

    def _remove(self, key: str) -> None:
        """移除缓存条目"""
        entry = self._cache.pop(key, None)
        if entry:
            self._current_size -= entry.size

    def _remove_oldest(self) -> None:
        """移除最老的缓存条目"""
        if self._cache:
            key = next(iter(self._cache))
            self._remove(key)

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._current_size = 0

    def remove_expired(self) -> int:
        """移除所有过期条目，返回移除数量"""
        with self._lock:
            current_time = time.time()
            expired_keys = []

            for key, entry in self._cache.items():
                if current_time - entry.timestamp > self._ttl:
                    expired_keys.append(key)

            for key in expired_keys:
                self._remove(key)

            return len(expired_keys)

    @property
    def size(self) -> int:
        """获取当前缓存大小（字节）"""
        with self._lock:
            return self._current_size

    @property
    def count(self) -> int:
        """获取缓存条目数量"""
        with self._lock:
            return len(self._cache)

    @property
    def max_size(self) -> int:
        """获取最大缓存大小"""
        return self._max_size

    @property
    def ttl(self) -> int:
        """获取 TTL（秒）"""
        return self._ttl


class URLCache:
    """URL 专用缓存"""

    def __init__(
        self,
        max_size_mb: int = 50,
        ttl_minutes: int = 15,
    ):
        self._cache = LRUCache(
            max_size_bytes=max_size_mb * 1024 * 1024,
            ttl_seconds=ttl_minutes * 60,
        )

    def get(self, url: str) -> dict[str, Any] | None:
        """获取 URL 缓存"""
        return self._cache.get(url)

    def set(self, url: str, data: dict[str, Any]) -> None:
        """设置 URL 缓存"""
        import json
        size = len(json.dumps(data))
        self._cache.set(url, data, size)

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()

    def remove_expired(self) -> int:
        """移除过期条目"""
        return self._cache.remove_expired()
