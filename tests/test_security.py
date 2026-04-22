"""
Security module tests
"""
import tempfile
from datetime import datetime

import pytest

from scripts.security.auto_classifier import (
    AutoClassifier,
    AutoAction,
    ClassificationLevel,
    INJECTION_PATTERNS,
)
from scripts.tools import validate_path_security


class TestAutoClassifierInjectionDetection:
    def test_sql_injection_detection(self):
        classifier = AutoClassifier()
        result = classifier.classify({
            "tool_name": "Bash",
            "input": {"command": "SELECT * FROM users WHERE id='1' OR '1'='1'"}
        })
        assert result.level in (ClassificationLevel.DANGEROUS, ClassificationLevel.CAUTION)
        assert result.should_deny or result.should_ask

    def test_xss_script_tag_in_bash(self):
        """XSS in Bash (e.g., writing malicious scripts) should be detected."""
        classifier = AutoClassifier()
        result = classifier.classify({
            "tool_name": "Bash",
            "input": {"command": "echo '<script>alert(1)</script>' > malicious.js"}
        })
        assert result.level in (ClassificationLevel.DANGEROUS, ClassificationLevel.CAUTION)

    def test_xss_event_handler_in_bash(self):
        """XSS patterns in Bash commands should be detected."""
        classifier = AutoClassifier()
        result = classifier.classify({
            "tool_name": "Bash",
            "input": {"command": "echo '<img src=x onerror=alert(1)>' > page.html"}
        })
        assert result.level in (ClassificationLevel.DANGEROUS, ClassificationLevel.CAUTION)

    def test_path_traversal_via_auto_classifier(self):
        """Path traversal patterns in Bash commands should be detected."""
        classifier = AutoClassifier()
        result = classifier.classify({
            "tool_name": "Bash",
            "input": {"command": "cat ../../../etc/passwd"}
        })
        assert result.level in (ClassificationLevel.DANGEROUS, ClassificationLevel.CAUTION)

    def test_command_injection_pipe_detection(self):
        classifier = AutoClassifier()
        result = classifier.classify({
            "tool_name": "Bash",
            "input": {"command": "echo test | bash -c whoami"}
        })
        assert result.level == ClassificationLevel.DANGEROUS
        assert result.should_deny

    def test_command_substitution_detection(self):
        classifier = AutoClassifier()
        result = classifier.classify({
            "tool_name": "Bash",
            "input": {"command": "$(whoami)"}
        })
        assert result.level == ClassificationLevel.DANGEROUS
        assert result.should_ask

    def test_dangerous_function_eval_detection(self):
        classifier = AutoClassifier()
        result = classifier.classify({
            "tool_name": "Bash",
            "input": {"command": "eval('malicious code')"}
        })
        assert result.level == ClassificationLevel.DANGEROUS
        assert result.should_deny

    def test_base64_decode_detection(self):
        classifier = AutoClassifier()
        result = classifier.classify({
            "tool_name": "Bash",
            "input": {"command": "echo base64_decode('aGhoaA==')"}
        })
        assert result.level == ClassificationLevel.DANGEROUS
        assert result.should_deny

    def test_injection_disabled_allows_sql(self):
        classifier = AutoClassifier(enable_injection_detection=False)
        result = classifier.classify({
            "tool_name": "Bash",
            "input": {"command": "SELECT * FROM users WHERE id='1' OR '1'='1'"}
        })
        assert result.level != ClassificationLevel.DANGEROUS

    def test_safe_operation_not_blocked_by_injection(self):
        classifier = AutoClassifier()
        result = classifier.classify({
            "tool_name": "Grep",
            "input": {"pattern": "hello", "path": "."}
        })
        assert result.level == ClassificationLevel.CAUTION
        assert result.should_ask

    def test_injection_patterns_compiled(self):
        assert len(INJECTION_PATTERNS) > 0
        for pattern_info in INJECTION_PATTERNS:
            assert "pattern" in pattern_info
            assert "description" in pattern_info
            assert "severity" in pattern_info


class TestAutoClassifier:
    def test_default_config(self):
        classifier = AutoClassifier()
        assert classifier.strict_mode is True
        assert classifier.enable_injection_detection is True

    def test_custom_config(self):
        classifier = AutoClassifier(strict_mode=False, enable_injection_detection=False)
        assert classifier.strict_mode is False
        assert classifier.enable_injection_detection is False


class TestPathSecurityValidation:
    """测试路径安全验证功能"""

    def test_path_traversal_detected(self):
        """路径穿越模式应该被检测"""
        is_safe, msg = validate_path_security("../etc/passwd")
        assert is_safe is False
        assert "敏感模式" in msg

    def test_path_traversal_windows(self):
        """Windows 路径穿越应该被检测"""
        is_safe, msg = validate_path_security("..\\..\\Windows\\System32")
        assert is_safe is False
        assert "敏感模式" in msg

    def test_url_encoded_traversal(self):
        """URL 编码的路径穿越应该被检测"""
        is_safe, msg = validate_path_security("%2e%2e%2f%2e%2e%2fetc%2fpasswd")
        assert is_safe is False
        assert "敏感模式" in msg

    def test_mixed_encoding_traversal(self):
        """混合编码的路径穿越应该被检测"""
        is_safe, msg = validate_path_security("..%2f..%5cetc%2fpasswd")
        assert is_safe is False

    def test_safe_relative_path(self):
        """安全的相对路径应该通过"""
        is_safe, msg = validate_path_security("src/main.py")
        assert is_safe is True
        assert msg == ""

    def test_safe_nested_path(self):
        """安全的嵌套路径应该通过"""
        is_safe, msg = validate_path_security("src/components/Button.tsx")
        assert is_safe is True
        assert msg == ""

    def test_protected_etc_passwd(self):
        """系统保护路径 /etc/passwd 应该被阻止"""
        is_safe, msg = validate_path_security("/etc/passwd")
        assert is_safe is False
        assert "系统保护路径" in msg

    def test_protected_windows_system32(self):
        """Windows 系统目录应该被保护"""
        is_safe, msg = validate_path_security("C:\\Windows\\System32\\config")
        assert is_safe is False
        assert "系统保护路径" in msg

    def test_protected_program_files(self):
        """Program Files 目录应该被保护"""
        is_safe, msg = validate_path_security("C:\\Program Files\\app\\bin")
        assert is_safe is False
        assert "系统保护路径" in msg


class TestAuditEventType:
    """AuditEventType 枚举测试"""

    def test_event_type_values(self):
        """测试事件类型枚举值"""
        from scripts.security.audit_logger import AuditEventType

        assert AuditEventType.TOOL_EXECUTION.value == "tool_execution"
        assert AuditEventType.PERMISSION_REQUEST.value == "permission_request"
        assert AuditEventType.PERMISSION_GRANTED.value == "permission_granted"
        assert AuditEventType.PERMISSION_DENIED.value == "permission_denied"
        assert AuditEventType.SESSION_START.value == "session_start"
        assert AuditEventType.SESSION_END.value == "session_end"
        assert AuditEventType.SECURITY_VIOLATION.value == "security_violation"


class TestAuditResult:
    """AuditResult 枚举测试"""

    def test_result_values(self):
        """测试结果枚举值"""
        from scripts.security.audit_logger import AuditResult

        assert AuditResult.SUCCESS.value == "success"
        assert AuditResult.FAILURE.value == "failure"
        assert AuditResult.DENIED.value == "denied"
        assert AuditResult.ERROR.value == "error"


class TestAuditEvent:
    """AuditEvent 数据类测试"""

    def test_event_creation(self):
        """测试事件创建"""
        from scripts.security.audit_logger import AuditEvent

        event = AuditEvent(
            event_id="test-123",
            event_type="tool_execution",
            timestamp=datetime.now().isoformat(),
            session_id="session-1",
            agent_id="agent-1",
            tool_name="Read",
            action="execute:Read",
            result="success",
            details={"file": "test.py"},
            duration_ms=100,
            user="testuser",
            source_ip="127.0.0.1",
        )

        assert event.event_id == "test-123"
        assert event.event_type == "tool_execution"
        assert event.tool_name == "Read"
        assert event.result == "success"

    def test_event_to_dict(self):
        """测试事件转字典"""
        from scripts.security.audit_logger import AuditEvent

        event = AuditEvent(
            event_id="test-123",
            event_type="tool_execution",
            timestamp=datetime.now().isoformat(),
            session_id="session-1",
            agent_id=None,
            tool_name="Read",
            action="execute:Read",
            result="success",
            details={},
            duration_ms=None,
            user=None,
            source_ip=None,
        )

        data = event.to_dict()

        assert data["event_id"] == "test-123"
        assert data["event_type"] == "tool_execution"

    def test_event_from_dict(self):
        """测试从字典创建事件"""
        from scripts.security.audit_logger import AuditEvent

        data = {
            "event_id": "test-123",
            "event_type": "tool_execution",
            "timestamp": datetime.now().isoformat(),
            "session_id": "session-1",
            "agent_id": None,
            "tool_name": "Read",
            "action": "execute:Read",
            "result": "success",
            "details": {},
            "duration_ms": None,
            "user": None,
            "source_ip": None,
        }

        event = AuditEvent.from_dict(data)

        assert event.event_id == "test-123"
        assert event.event_type == "tool_execution"


class TestAuditLogger:
    """AuditLogger 测试"""

    def test_logger_init(self):
        """测试日志器初始化"""
        from scripts.security.audit_logger import AuditLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            assert logger.log_dir.exists()
            assert logger.max_file_size > 0
            assert logger.retention_days > 0

    def test_logger_default_init(self):
        """测试默认初始化"""
        from scripts.security.audit_logger import AuditLogger

        logger = AuditLogger()

        assert logger.log_dir is not None

    def test_log_event(self):
        """测试记录事件"""
        from scripts.security.audit_logger import AuditLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            event_id = logger.log_event(
                event_type="tool_execution",
                action="test:action",
                session_id="test-session",
                result="success",
            )

            assert event_id is not None
            assert len(event_id) == 8

    def test_log_tool_execution(self):
        """测试记录工具执行"""
        from scripts.security.audit_logger import AuditLogger, AuditResult

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            event_id = logger.log_tool_execution(
                tool_name="Read",
                session_id="test-session",
                execution_time_ms=150,
                result=AuditResult.SUCCESS,
                args={"file_path": "test.py"},
            )

            assert event_id is not None

    def test_log_permission_request(self):
        """测试记录权限请求"""
        from scripts.security.audit_logger import AuditLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            event_id = logger.log_permission_request(
                tool_name="Bash",
                session_id="test-session",
                reason="User requested",
            )

            assert event_id is not None

    def test_log_permission_decision_granted(self):
        """测试记录权限授权"""
        from scripts.security.audit_logger import AuditLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            event_id = logger.log_permission_decision(
                tool_name="Read",
                session_id="test-session",
                granted=True,
                reason="File is safe",
            )

            assert event_id is not None

    def test_log_permission_decision_denied(self):
        """测试记录权限拒绝"""
        from scripts.security.audit_logger import AuditLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            event_id = logger.log_permission_decision(
                tool_name="Bash",
                session_id="test-session",
                granted=False,
                reason="Dangerous command",
            )

            assert event_id is not None

    def test_log_security_violation(self):
        """测试记录安全违规"""
        from scripts.security.audit_logger import AuditLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            event_id = logger.log_security_violation(
                violation_type="path_traversal",
                details={"path": "/etc/passwd"},
                session_id="test-session",
            )

            assert event_id is not None

    def test_log_session_start(self):
        """测试记录会话开始"""
        from scripts.security.audit_logger import AuditLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            event_id = logger.log_session_start(
                session_id="test-session",
                agent_id="agent-1",
                user="testuser",
            )

            assert event_id is not None

    def test_log_session_end(self):
        """测试记录会话结束"""
        from scripts.security.audit_logger import AuditLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            event_id = logger.log_session_end(
                session_id="test-session",
                duration_ms=60000,
            )

            assert event_id is not None

    def test_query_events(self):
        """测试查询事件"""
        from scripts.security.audit_logger import AuditLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            logger.log_event(
                event_type="tool_execution",
                action="test:action1",
                session_id="session-1",
                result="success",
            )
            logger.log_event(
                event_type="tool_execution",
                action="test:action2",
                session_id="session-2",
                result="success",
            )

            events = logger.query_events(session_id="session-1")
            assert len(events) == 1
            assert events[0].session_id == "session-1"

    def test_query_events_with_limit(self):
        """测试查询事件限制"""
        from scripts.security.audit_logger import AuditLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = AuditLogger(log_dir=tmpdir)

            for i in range(10):
                logger.log_event(
                    event_type="tool_execution",
                    action=f"test:action{i}",
                    session_id="session-1",
                    result="success",
                )

            events = logger.query_events(session_id="session-1", limit=5)
            assert len(events) == 5


class TestNetworkControl:
    """NetworkControl 测试"""

    def test_init(self):
        """测试初始化"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl()

        assert control.allow_private is False
        assert control.allow_reserved is False

    def test_init_with_params(self):
        """测试带参数初始化"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl(
            allow_private=True,
            allow_reserved=True,
        )

        assert control.allow_private is True
        assert control.allow_reserved is True

    def test_check_domain_whitelisted(self):
        """测试白名单域名"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl()

        allowed, reason = control.check_domain("api.github.com")

        assert allowed is True

    def test_check_domain_blocked(self):
        """测试黑名单域名"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl()
        control.add_blacklist("evil.com")

        allowed, reason = control.check_domain("evil.com")

        assert allowed is False
        assert "blocked" in reason.lower()

    def test_check_domain_localhost(self):
        """测试 localhost"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl()

        allowed, reason = control.check_domain("localhost")

        assert allowed is False

    def test_check_ip_public(self):
        """测试公共 IP"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl()

        allowed, reason = control.check_ip("8.8.8.8")

        assert allowed is True

    def test_check_ip_private(self):
        """测试私有 IP"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl()

        allowed, reason = control.check_ip("192.168.1.1")

        assert allowed is False
        assert "private" in reason.lower()

    def test_check_ip_private_allowed(self):
        """测试允许私有 IP"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl(allow_private=True)

        allowed, reason = control.check_ip("192.168.1.1")

        assert allowed is True

    def test_check_ip_loopback(self):
        """测试回环地址"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl()

        allowed, reason = control.check_ip("127.0.0.1")

        assert allowed is False

    def test_check_ip_multicast(self):
        """测试多播地址"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl()

        allowed, reason = control.check_ip("224.0.0.1")

        assert allowed is False
        assert "multicast" in reason.lower() or "reserved" in reason.lower()

    def test_check_ip_invalid(self):
        """测试无效 IP"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl()

        allowed, reason = control.check_ip("not.an.ip")

        assert allowed is False
        assert "invalid" in reason.lower()

    def test_resolve_and_check(self):
        """测试 DNS 解析检查"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl()

        allowed, reason = control.resolve_and_check("api.github.com")

        assert allowed is True

    def test_add_whitelist(self):
        """测试添加白名单"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl()
        control.add_whitelist("my-trusted-site.com")

        allowed, reason = control.check_domain("my-trusted-site.com")

        assert allowed is True
        assert "whitelist" in reason.lower()

    def test_add_blacklist(self):
        """测试添加黑名单"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl()
        control.add_blacklist("bad-site.com")

        allowed, reason = control.check_domain("bad-site.com")

        assert allowed is False

    def test_check_domain_with_port(self):
        """测试带端口的域名"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl()

        allowed, reason = control.check_domain("api.github.com:443")

        assert allowed is True

    def test_check_domain_with_path(self):
        """测试带路径的域名"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl()

        allowed, reason = control.check_domain("api.github.com/users")

        assert allowed is True

    def test_check_domain_with_protocol(self):
        """测试带协议的域名"""
        from scripts.security.network_control import NetworkControl

        control = NetworkControl()

        allowed, reason = control.check_domain("https://api.github.com")

        assert allowed is True


class TestNetworkControlConvenience:
    """网络控制便捷函数测试"""

    def test_check_domain_convenience(self):
        """测试便捷函数"""
        from scripts.security.network_control import check_domain

        allowed, reason = check_domain("api.github.com")

        assert allowed is True

    def test_check_ip_convenience(self):
        """测试 IP 检查便捷函数"""
        from scripts.security.network_control import check_ip

        allowed, reason = check_ip("8.8.8.8")

        assert allowed is True

    def test_get_network_control(self):
        """测试获取全局控制器"""
        from scripts.security.network_control import get_network_control, NetworkControl

        control = get_network_control()

        assert isinstance(control, NetworkControl)


class TestAuditLoggerConvenience:
    """审计日志便捷函数测试"""

    def test_log_tool_execution_convenience(self):
        """测试工具执行便捷函数"""
        from scripts.security.audit_logger import log_tool_execution

        event_id = log_tool_execution(
            tool_name="Read",
            session_id="test-session",
            execution_time_ms=100,
        )

        assert event_id is not None

    def test_log_permission_decision_convenience(self):
        """测试权限决策便捷函数"""
        from scripts.security.audit_logger import log_permission_decision

        event_id = log_permission_decision(
            tool_name="Bash",
            session_id="test-session",
            granted=True,
        )

        assert event_id is not None
