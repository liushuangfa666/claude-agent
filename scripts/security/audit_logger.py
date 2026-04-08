"""
审计日志 - Audit Logger

记录所有安全相关的操作事件，用于合规和审计追踪。
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class AuditEventType(Enum):
    """审计事件类型"""
    TOOL_EXECUTION = "tool_execution"
    PERMISSION_REQUEST = "permission_request"
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"
    FILE_ACCESS = "file_access"
    NETWORK_REQUEST = "network_request"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    SECURITY_VIOLATION = "security_violation"


class AuditResult(Enum):
    """操作结果"""
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    ERROR = "error"


@dataclass
class AuditEvent:
    """
    审计事件

    Attributes:
        event_id: 事件唯一 ID
        event_type: 事件类型
        timestamp: 时间戳
        session_id: 会话 ID
        agent_id: Agent ID (如果有)
        tool_name: 工具名称 (如果有)
        action: 具体操作
        result: 操作结果
        details: 额外详情
        duration_ms: 执行时长(毫秒)
        user: 执行用户
        source_ip: 来源 IP (如果有)
    """
    event_id: str
    event_type: str
    timestamp: str
    session_id: str | None
    agent_id: str | None
    tool_name: str | None
    action: str
    result: str
    details: dict[str, Any]
    duration_ms: int | None
    user: str | None
    source_ip: str | None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditEvent:
        """从字典创建"""
        return cls(**data)


class AuditLogger:
    """
    审计日志记录器

    记录所有安全相关事件到文件或外部系统。

    Attributes:
        log_dir: 日志目录
        max_file_size: 单个日志文件最大大小(MB)
        retention_days: 日志保留天数
    """

    def __init__(
        self,
        log_dir: str | Path | None = None,
        max_file_size: int = 10,
        retention_days: int = 30,
    ) -> None:
        """
        初始化审计日志记录器

        Args:
            log_dir: 日志目录，默认 ~/.claude-agent/audit
            max_file_size: 单个日志文件最大大小(MB)
            retention_days: 日志保留天数
        """
        if log_dir is None:
            self.log_dir = Path(os.path.expanduser("~/.claude-agent/audit"))
        else:
            self.log_dir = Path(log_dir)

        self.max_file_size = max_file_size * 1024 * 1024  # MB to bytes
        self.retention_days = retention_days
        self._current_file: Path | None = None
        self._event_count = 0

        # 确保目录存在
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_file(self) -> Path:
        """获取当前日志文件路径"""
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self.log_dir / f"audit-{today}.jsonl"

        # 检查文件大小
        if log_file.exists() and log_file.stat().st_size >= self.max_file_size:
            # 轮转日志
            counter = 1
            while True:
                new_file = self.log_dir / f"audit-{today}-{counter}.jsonl"
                if not new_file.exists():
                    log_file = new_file
                    break
                counter += 1

        return log_file

    def _write_event(self, event: AuditEvent) -> None:
        """写入事件到日志文件"""
        log_file = self._get_log_file()
        event_line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(event_line)

    def log_event(
        self,
        event_type: AuditEventType | str,
        action: str,
        session_id: str | None = None,
        agent_id: str | None = None,
        tool_name: str | None = None,
        result: AuditResult | str = AuditResult.SUCCESS,
        details: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        user: str | None = None,
        source_ip: str | None = None,
    ) -> str:
        """
        记录审计事件

        Args:
            event_type: 事件类型
            action: 具体操作
            session_id: 会话 ID
            agent_id: Agent ID
            tool_name: 工具名称
            result: 操作结果
            details: 额外详情
            duration_ms: 执行时长
            user: 执行用户
            source_ip: 来源 IP

        Returns:
            事件 ID
        """
        event_id = str(uuid.uuid4())[:8]

        if isinstance(event_type, AuditEventType):
            event_type_str = event_type.value
        else:
            event_type_str = event_type

        if isinstance(result, AuditResult):
            result_str = result.value
        else:
            result_str = result

        event = AuditEvent(
            event_id=event_id,
            event_type=event_type_str,
            timestamp=datetime.now().isoformat(),
            session_id=session_id,
            agent_id=agent_id,
            tool_name=tool_name,
            action=action,
            result=result_str,
            details=details or {},
            duration_ms=duration_ms,
            user=user,
            source_ip=source_ip,
        )

        self._write_event(event)
        self._event_count += 1

        return event_id

    def log_tool_execution(
        self,
        tool_name: str,
        session_id: str | None,
        execution_time_ms: int,
        result: AuditResult | str = AuditResult.SUCCESS,
        args: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> str:
        """
        记录工具执行

        Args:
            tool_name: 工具名称
            session_id: 会话 ID
            execution_time_ms: 执行时长(毫秒)
            result: 执行结果
            args: 工具参数
            error: 错误信息

        Returns:
            事件 ID
        """
        details: dict[str, Any] = {"args": args} if args else {}
        if error:
            details["error"] = error

        return self.log_event(
            event_type=AuditEventType.TOOL_EXECUTION,
            action=f"execute:{tool_name}",
            session_id=session_id,
            tool_name=tool_name,
            result=result,
            details=details,
            duration_ms=execution_time_ms,
        )

    def log_permission_request(
        self,
        tool_name: str,
        session_id: str | None,
        details: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> str:
        """
        记录权限请求

        Args:
            tool_name: 工具名称
            session_id: 会话 ID
            details: 请求详情
            reason: 请求原因

        Returns:
            事件 ID
        """
        event_details = dict(details) if details else {}
        if reason:
            event_details["reason"] = reason

        return self.log_event(
            event_type=AuditEventType.PERMISSION_REQUEST,
            action=f"request:{tool_name}",
            session_id=session_id,
            tool_name=tool_name,
            result=AuditResult.SUCCESS.value,
            details=event_details,
        )

    def log_permission_decision(
        self,
        tool_name: str,
        session_id: str | None,
        granted: bool,
        reason: str | None = None,
    ) -> str:
        """
        记录权限决策

        Args:
            tool_name: 工具名称
            session_id: 会话 ID
            granted: 是否授权
            reason: 决策原因

        Returns:
            事件 ID
        """
        event_type = AuditEventType.PERMISSION_GRANTED if granted else AuditEventType.PERMISSION_DENIED
        event_details = {}
        if reason:
            event_details["reason"] = reason

        return self.log_event(
            event_type=event_type,
            action=f"{'grant' if granted else 'deny'}:{tool_name}",
            session_id=session_id,
            tool_name=tool_name,
            result=AuditResult.SUCCESS if granted else AuditResult.DENIED,
            details=event_details,
        )

    def log_security_violation(
        self,
        violation_type: str,
        details: dict[str, Any],
        session_id: str | None = None,
    ) -> str:
        """
        记录安全违规

        Args:
            violation_type: 违规类型
            details: 违规详情
            session_id: 会话 ID

        Returns:
            事件 ID
        """
        event_details = {"violation_type": violation_type, **details}

        return self.log_event(
            event_type=AuditEventType.SECURITY_VIOLATION,
            action=f"violation:{violation_type}",
            session_id=session_id,
            result=AuditResult.FAILURE,
            details=event_details,
        )

    def log_session_start(
        self,
        session_id: str,
        agent_id: str | None = None,
        user: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        记录会话开始

        Args:
            session_id: 会话 ID
            agent_id: Agent ID
            user: 用户
            metadata: 元数据

        Returns:
            事件 ID
        """
        return self.log_event(
            event_type=AuditEventType.SESSION_START,
            action="session:start",
            session_id=session_id,
            agent_id=agent_id,
            user=user,
            result=AuditResult.SUCCESS,
            details=metadata or {},
        )

    def log_session_end(
        self,
        session_id: str,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        记录会话结束

        Args:
            session_id: 会话 ID
            duration_ms: 会话时长
            metadata: 元数据

        Returns:
            事件 ID
        """
        return self.log_event(
            event_type=AuditEventType.SESSION_END,
            action="session:end",
            session_id=session_id,
            result=AuditResult.SUCCESS,
            details=metadata or {},
            duration_ms=duration_ms,
        )

    def query_events(
        self,
        event_type: AuditEventType | str | None = None,
        session_id: str | None = None,
        tool_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """
        查询审计事件

        Args:
            event_type: 事件类型过滤
            session_id: 会话 ID 过滤
            tool_name: 工具名称过滤
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回数量限制

        Returns:
            审计事件列表
        """
        events = []

        if isinstance(event_type, AuditEventType):
            event_type_str = event_type.value
        else:
            event_type_str = event_type

        # 扫描所有日志文件
        for log_file in sorted(self.log_dir.glob("audit-*.jsonl")):
            try:
                for line in log_file.read_text().splitlines():
                    if not line.strip():
                        continue
                    try:
                        event = AuditEvent.from_dict(json.loads(line))
                    except (json.JSONDecodeError, TypeError):
                        continue

                    # 应用过滤器
                    if event_type_str and event.event_type != event_type_str:
                        continue
                    if session_id and event.session_id != session_id:
                        continue
                    if tool_name and event.tool_name != tool_name:
                        continue
                    if start_time:
                        event_time = datetime.fromisoformat(event.timestamp)
                        if event_time < start_time:
                            continue
                    if end_time:
                        event_time = datetime.fromisoformat(event.timestamp)
                        if event_time > end_time:
                            continue

                    events.append(event)

                    if len(events) >= limit:
                        return events

            except (OSError, IOError):
                continue

        return events

    def cleanup_old_logs(self) -> int:
        """
        清理过期的日志文件

        Returns:
            删除的文件数量
        """
        import time as time_module

        cutoff = time_module.time() - (self.retention_days * 24 * 60 * 60)
        deleted_count = 0

        for log_file in self.log_dir.glob("audit-*.jsonl"):
            try:
                if log_file.stat().st_mtime < cutoff:
                    log_file.unlink()
                    deleted_count += 1
            except OSError:
                continue

        return deleted_count


# 全局审计日志实例
_default_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """
    获取全局审计日志实例

    Returns:
        AuditLogger 实例
    """
    global _default_logger
    if _default_logger is None:
        _default_logger = AuditLogger()
    return _default_logger


def log_tool_execution(
    tool_name: str,
    session_id: str | None,
    execution_time_ms: int,
    result: AuditResult | str = AuditResult.SUCCESS,
    args: dict[str, Any] | None = None,
) -> str:
    """
    便捷函数：记录工具执行

    Args:
        tool_name: 工具名称
        session_id: 会话 ID
        execution_time_ms: 执行时长
        result: 执行结果
        args: 工具参数

    Returns:
        事件 ID
    """
    return get_audit_logger().log_tool_execution(
        tool_name=tool_name,
        session_id=session_id,
        execution_time_ms=execution_time_ms,
        result=result,
        args=args,
    )


def log_permission_decision(
    tool_name: str,
    session_id: str | None,
    granted: bool,
    reason: str | None = None,
) -> str:
    """
    便捷函数：记录权限决策

    Args:
        tool_name: 工具名称
        session_id: 会话 ID
        granted: 是否授权
        reason: 决策原因

    Returns:
        事件 ID
    """
    return get_audit_logger().log_permission_decision(
        tool_name=tool_name,
        session_id=session_id,
        granted=granted,
        reason=reason,
    )


if __name__ == "__main__":
    # 简单测试
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(log_dir=tmpdir)

        # 测试记录事件
        event_id = logger.log_tool_execution(
            tool_name="Read",
            session_id="test-session-1",
            execution_time_ms=100,
            args={"file_path": "/test/file.py"},
        )
        print(f"Logged tool execution: {event_id}")

        event_id = logger.log_permission_decision(
            tool_name="Bash",
            session_id="test-session-1",
            granted=False,
            reason="Dangerous command detected",
        )
        print(f"Logged permission decision: {event_id}")

        # 查询事件
        events = logger.query_events(session_id="test-session-1")
        print(f"Found {len(events)} events")

        for event in events:
            print(f"  - {event.event_type}: {event.action} -> {event.result}")
