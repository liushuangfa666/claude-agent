"""
安全检查器 - Security Checker

检测危险操作并返回安全建议。
"""
import re
from dataclasses import dataclass
from enum import Enum


class RiskLevel(Enum):
    """风险级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


DANGEROUS_BASH_PATTERNS: list[tuple[str, RiskLevel, str]] = [
    (r"rm\s+-rf\s+/\s*$", RiskLevel.CRITICAL, "递归删除根目录"),
    (r"rm\s+-rf\s+/tmp", RiskLevel.HIGH, "删除 /tmp 目录"),
    (r"rm\s+-rf\s+/var", RiskLevel.HIGH, "删除系统目录"),
    (r"chmod\s+-R\s+777", RiskLevel.HIGH, "过度开放文件权限"),
    (r"chmod\s+000", RiskLevel.MEDIUM, "移除所有权限"),
    (r"sudo\s+.*", RiskLevel.MEDIUM, "提权命令"),
    (r"curl.*\|.*sh", RiskLevel.CRITICAL, "管道执行远程脚本"),
    (r"wget.*\|.*sh", RiskLevel.CRITICAL, "管道执行远程脚本"),
    (r":\(\)\s*:\s*:\s*;.*:.*:", RiskLevel.CRITICAL, "Fork 炸弹"),
    (r"fdisk", RiskLevel.CRITICAL, "磁盘分区工具"),
    (r"mkfs", RiskLevel.CRITICAL, "文件系统格式化"),
    (r"dd\s+.*of=/dev/", RiskLevel.CRITICAL, "直接写入设备"),
    (r"git\s+push\s+--force", RiskLevel.MEDIUM, "强制推送"),
    (r"git\s+push\s+--force-with-lease", RiskLevel.LOW, "强制推送"),
]

SENSITIVE_PATHS: list[str] = [
    ".git/",
    ".claude/",
    ".svn/",
    ".hg/",
    "node_modules/",
    "__pycache__/",
    "*.pyc",
    ".DS_Store",
    "Thumbs.db",
]

PROTECTED_PATHS: list[str] = [
    "/System/",
    "/Library/",
    "/Windows/System32/",
    "/Windows/SysWOW64/",
    "C:\\Windows\\",
    "C:\\Program Files\\",
    "C:\\Program Files (x86)\\",
]


@dataclass
class SecurityCheckResult:
    """安全检查结果"""
    is_safe: bool
    risk_level: RiskLevel
    message: str
    matched_pattern: str | None = None


class SecurityChecker:
    """安全检查器"""
    
    def __init__(self):
        self._bash_patterns: list[tuple[re.Pattern, RiskLevel, str]] = [
            (re.compile(pattern, re.IGNORECASE), level, msg)
            for pattern, level, msg in DANGEROUS_BASH_PATTERNS
        ]
    
    def check_bash_command(self, command: str) -> SecurityCheckResult:
        """
        检查 Bash 命令安全性。
        """
        for pattern, level, message in self._bash_patterns:
            if pattern.search(command):
                return SecurityCheckResult(
                    is_safe=False,
                    risk_level=level,
                    message=message,
                    matched_pattern=pattern.pattern
                )
        
        for path in SENSITIVE_PATHS:
            if path in command:
                return SecurityCheckResult(
                    is_safe=False,
                    risk_level=RiskLevel.MEDIUM,
                    message=f"涉及敏感路径: {path}",
                    matched_pattern=path
                )
        
        for path in PROTECTED_PATHS:
            if path in command:
                return SecurityCheckResult(
                    is_safe=False,
                    risk_level=RiskLevel.HIGH,
                    message=f"涉及系统保护路径: {path}",
                    matched_pattern=path
                )
        
        return SecurityCheckResult(
            is_safe=True,
            risk_level=RiskLevel.LOW,
            message="命令安全"
        )
    
    def check_file_path(self, file_path: str) -> SecurityCheckResult:
        """检查文件路径安全性"""
        for path in PROTECTED_PATHS:
            if path in file_path:
                return SecurityCheckResult(
                    is_safe=False,
                    risk_level=RiskLevel.HIGH,
                    message=f"涉及系统保护路径: {path}",
                    matched_pattern=path
                )
        
        for path in SENSITIVE_PATHS:
            if path in file_path:
                return SecurityCheckResult(
                    is_safe=False,
                    risk_level=RiskLevel.LOW,
                    message=f"涉及敏感路径: {path}",
                    matched_pattern=path
                )
        
        return SecurityCheckResult(
            is_safe=True,
            risk_level=RiskLevel.LOW,
            message="路径安全"
        )
    
    def check_url(self, url: str) -> SecurityCheckResult:
        """检查 URL 安全性"""
        blocked_extensions = [".exe", ".dmg", ".pkg", ".msi", ".deb", ".rpm"]
        for ext in blocked_extensions:
            if url.lower().endswith(ext):
                return SecurityCheckResult(
                    is_safe=False,
                    risk_level=RiskLevel.HIGH,
                    message=f"阻止下载可执行文件: {ext}",
                    matched_pattern=ext
                )
        
        if url.startswith("file://"):
            return SecurityCheckResult(
                is_safe=False,
                risk_level=RiskLevel.HIGH,
                message="本地文件访问被阻止",
                matched_pattern="file://"
            )
        
        return SecurityCheckResult(
            is_safe=True,
            risk_level=RiskLevel.LOW,
            message="URL 安全"
        )
