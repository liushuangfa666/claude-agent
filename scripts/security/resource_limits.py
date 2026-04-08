"""
资源限制 - Resource Limits

提供操作频率、CPU/内存、文件大小等资源限制功能。
"""
from __future__ import annotations

import os
import psutil
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RateLimitOperation(Enum):
    """可限制的操作类型"""
    TOOL_EXECUTION = "tool_execution"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    NETWORK_REQUEST = "network_request"
    COMMAND_EXECUTION = "command_execution"
    API_CALL = "api_call"


@dataclass
class RateLimitConfig:
    """频率限制配置"""
    max_requests: int  # 时间窗口内最大请求数
    window_seconds: int  # 时间窗口秒数
    burst: int = 0  # 突发允许数量


@dataclass
class RateLimitResult:
    """频率限制检查结果"""
    allowed: bool
    reason: str
    remaining: int
    reset_in: float  # 距离重置的秒数


class RateLimiter:
    """
    操作频率限制器

    使用滑动窗口算法限制操作频率。

    Attributes:
        configs: 各操作的限制配置
    """
    # 默认限制配置
    DEFAULT_CONFIGS: dict[RateLimitOperation, RateLimitConfig] = {
        RateLimitOperation.TOOL_EXECUTION: RateLimitConfig(max_requests=100, window_seconds=60),
        RateLimitOperation.FILE_READ: RateLimitConfig(max_requests=200, window_seconds=60),
        RateLimitOperation.FILE_WRITE: RateLimitConfig(max_requests=50, window_seconds=60),
        RateLimitOperation.NETWORK_REQUEST: RateLimitConfig(max_requests=30, window_seconds=60),
        RateLimitOperation.COMMAND_EXECUTION: RateLimitConfig(max_requests=20, window_seconds=60),
        RateLimitOperation.API_CALL: RateLimitConfig(max_requests=60, window_seconds=60),
    }

    def __init__(self, configs: dict[RateLimitOperation, RateLimitConfig] | None = None) -> None:
        """
        初始化频率限制器

        Args:
            configs: 自定义限制配置
        """
        self.configs = configs or dict(self.DEFAULT_CONFIGS)
        self._buckets: dict[RateLimitOperation, list[float]] = {
            op: [] for op in RateLimitOperation
        }

    def check_rate_limit(self, operation: RateLimitOperation | str) -> RateLimitResult:
        """
        检查操作是否允许

        Args:
            operation: 操作类型

        Returns:
            RateLimitResult，包含是否允许及详情
        """
        if isinstance(operation, str):
            try:
                operation = RateLimitOperation(operation)
            except ValueError:
                return RateLimitResult(
                    allowed=True,
                    reason=f"Unknown operation: {operation}",
                    remaining=-1,
                    reset_in=0,
                )

        config = self.configs.get(operation)
        if not config:
            return RateLimitResult(
                allowed=True,
                reason="No limit configured",
                remaining=-1,
                reset_in=0,
            )

        now = time.time()
        window_start = now - config.window_seconds

        # 清理过期的请求记录
        bucket = self._buckets[operation]
        bucket[:] = [t for t in bucket if t > window_start]

        # 检查限制
        if len(bucket) >= config.max_requests:
            oldest = min(bucket)
            reset_in = oldest + config.window_seconds - now
            return RateLimitResult(
                allowed=False,
                reason=f"Rate limit exceeded: {len(bucket)}/{config.max_requests} in {config.window_seconds}s",
                remaining=0,
                reset_in=max(0, reset_in),
            )

        remaining = config.max_requests - len(bucket)
        return RateLimitResult(
            allowed=True,
            reason="Allowed",
            remaining=remaining,
            reset_in=0,
        )

    def record_request(self, operation: RateLimitOperation | str) -> None:
        """
        记录一次请求

        Args:
            operation: 操作类型
        """
        if isinstance(operation, str):
            try:
                operation = RateLimitOperation(operation)
            except ValueError:
                return

        now = time.time()
        if operation in self._buckets:
            self._buckets[operation].append(now)

    def get_status(self, operation: RateLimitOperation | str) -> dict[str, Any]:
        """
        获取操作限制状态

        Args:
            operation: 操作类型

        Returns:
            状态字典
        """
        result = self.check_rate_limit(operation)
        return {
            "operation": operation.value if isinstance(operation, RateLimitOperation) else operation,
            "allowed": result.allowed,
            "remaining": result.remaining,
            "reset_in": result.reset_in,
            "reason": result.reason,
        }


@dataclass
class ResourceCheckResult:
    """资源检查结果"""
    allowed: bool
    reason: str
    current_value: float | None = None
    limit: float | None = None


class ResourceLimiter:
    """
    系统资源限制器

    检查 CPU、内存、磁盘等资源使用情况。
    """

    def __init__(
        self,
        max_memory_percent: float = 80.0,
        max_disk_percent: float = 90.0,
        max_cpu_percent: float = 95.0,
    ) -> None:
        """
        初始化资源限制器

        Args:
            max_memory_percent: 最大内存使用百分比
            max_disk_percent: 最大磁盘使用百分比
            max_cpu_percent: 最大 CPU 使用百分比
        """
        self.max_memory_percent = max_memory_percent
        self.max_disk_percent = max_disk_percent
        self.max_cpu_percent = max_cpu_percent

    def check_memory(self) -> ResourceCheckResult:
        """
        检查内存使用

        Returns:
            资源检查结果
        """
        memory = psutil.virtual_memory()
        percent = memory.percent

        if percent >= self.max_memory_percent:
            return ResourceCheckResult(
                allowed=False,
                reason=f"Memory usage critical: {percent:.1f}%",
                current_value=percent,
                limit=self.max_memory_percent,
            )

        return ResourceCheckResult(
            allowed=True,
            reason=f"Memory usage OK: {percent:.1f}%",
            current_value=percent,
            limit=self.max_memory_percent,
        )

    def check_disk(self, path: str | None = None) -> ResourceCheckResult:
        """
        检查磁盘使用

        Args:
            path: 路径，默认为系统根目录

        Returns:
            资源检查结果
        """
        if path is None:
            disk = psutil.disk_usage("/")
        else:
            disk = psutil.disk_usage(path)

        percent = disk.percent

        if percent >= self.max_disk_percent:
            return ResourceCheckResult(
                allowed=False,
                reason=f"Disk usage critical: {percent:.1f}%",
                current_value=percent,
                limit=self.max_disk_percent,
            )

        return ResourceCheckResult(
            allowed=True,
            reason=f"Disk usage OK: {percent:.1f}%",
            current_value=percent,
            limit=self.max_disk_percent,
        )

    def check_cpu(self) -> ResourceCheckResult:
        """
        检查 CPU 使用

        Returns:
            资源检查结果
        """
        percent = psutil.cpu_percent(interval=0.1)

        if percent >= self.max_cpu_percent:
            return ResourceCheckResult(
                allowed=False,
                reason=f"CPU usage critical: {percent:.1f}%",
                current_value=percent,
                limit=self.max_cpu_percent,
            )

        return ResourceCheckResult(
            allowed=True,
            reason=f"CPU usage OK: {percent:.1f}%",
            current_value=percent,
            limit=self.max_cpu_percent,
        )

    def check_all(self) -> dict[str, ResourceCheckResult]:
        """
        检查所有资源

        Returns:
            各资源检查结果字典
        """
        return {
            "memory": self.check_memory(),
            "disk": self.check_disk(),
            "cpu": self.check_cpu(),
        }

    def get_system_status(self) -> dict[str, Any]:
        """
        获取系统资源状态摘要

        Returns:
            状态字典
        """
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        cpu = psutil.cpu_percent(interval=0.1)

        return {
            "memory": {
                "total_gb": memory.total / (1024 ** 3),
                "available_gb": memory.available / (1024 ** 3),
                "used_percent": memory.percent,
            },
            "disk": {
                "total_gb": disk.total / (1024 ** 3),
                "free_gb": disk.free / (1024 ** 3),
                "used_percent": disk.percent,
            },
            "cpu": {
                "usage_percent": cpu,
                "count": psutil.cpu_count(),
            },
        }


def check_file_size(file_path: str, max_size_bytes: int) -> tuple[bool, str]:
    """
    检查文件大小

    Args:
        file_path: 文件路径
        max_size_bytes: 最大大小（字节）

    Returns:
        (是否允许, 原因)
    """
    try:
        size = os.path.getsize(file_path)
        if size > max_size_bytes:
            return False, f"File too large: {size} > {max_size_bytes} bytes"
        return True, "OK"
    except OSError as e:
        return False, f"Cannot access file: {e}"


# 全局限流器实例
_rate_limiter: RateLimiter | None = None
_resource_limiter: ResourceLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """获取全局频率限制器"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def get_resource_limiter() -> ResourceLimiter:
    """获取全局资源限制器"""
    global _resource_limiter
    if _resource_limiter is None:
        _resource_limiter = ResourceLimiter()
    return _resource_limiter


if __name__ == "__main__":
    # 简单测试
    print("RateLimiter tests:")
    limiter = RateLimiter()

    for i in range(5):
        result = limiter.check_rate_limit(RateLimitOperation.TOOL_EXECUTION)
        print(f"  Check {i+1}: allowed={result.allowed}, remaining={result.remaining}")
        limiter.record_request(RateLimitOperation.TOOL_EXECUTION)

    print("\nResourceLimiter tests:")
    resource_limiter = ResourceLimiter()

    print(f"  Memory: {resource_limiter.check_memory()}")
    print(f"  Disk: {resource_limiter.check_disk()}")
    print(f"  CPU: {resource_limiter.check_cpu()}")
