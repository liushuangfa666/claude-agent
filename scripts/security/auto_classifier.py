"""
自动分类器 - Auto Classifier
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ClassificationLevel(Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"
    BLOCKED = "blocked"


class AutoAction(Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


BLOCK_PATTERNS: list[str] = [
    "*production*",
    "*/prod/*",
    "*/production/*",
    "*--prod*",
    "*--production*",
    "*--environment=production*",
    "*--env=prod*",
    "*--stage=production*",
    "*STAGING*",
    "*PRODUCTION*",
]

DANGEROUS_PATTERNS: list[dict[str, Any]] = [
    {"pattern": "Bash(rm *)", "description": "删除操作", "severity": "high"},
    {"pattern": "Bash(mv *)", "description": "移动/重命名操作", "severity": "medium"},
    {"pattern": "Bash(dd *)", "description": "直接磁盘操作", "severity": "critical"},
    {"pattern": "Bash(mkfs *)", "description": "格式化操作", "severity": "critical"},
    {"pattern": "Bash(> *)", "description": "覆盖文件操作", "severity": "medium"},
    {"pattern": "Edit(*.pem)", "description": "修改证书文件", "severity": "high"},
    {"pattern": "Edit(*.key)", "description": "修改密钥文件", "severity": "high"},
    {"pattern": "Edit(*.env)", "description": "修改环境变量", "severity": "medium"},
]

INJECTION_PATTERNS: list[dict[str, Any]] = [
    {"pattern": r"(?i)(sql\s+injection|sqli|'OR\s+'1'\s*=\s*'1|--|\bUNION\b.*\bSELECT\b)", "description": "SQL注入特征", "severity": "critical"},
    {"pattern": r"(?i)(<script|javascript:|on\w+\s*=|<iframe|<object|<embed)", "description": "XSS注入特征", "severity": "high"},
    {"pattern": r"(?i)(https?://[^\s]*\.php[^\s]*\?.*=)", "description": "可疑URL参数", "severity": "medium"},
    {"pattern": r"(\.\./|\.\.\\|%2e%2e)", "description": "路径遍历特征", "severity": "high"},
    {"pattern": r"(\||;)\s*(curl|wget|nc|bash|sh)\b", "description": "命令注入特征", "severity": "critical"},
    {"pattern": r"\$\([^\)]+\)|`[^`]+`", "description": "命令替换特征", "severity": "high"},
    {"pattern": r"(?i)(eval|exec|system|passthru|shell_exec|popen)\s*\(", "description": "危险函数调用", "severity": "critical"},
    {"pattern": r"(?i)(base64_decode|assert|preg_replace.*\/e)", "description": "代码执行特征", "severity": "critical"},
    {"pattern": r"(?i)(concat|char\s*\().*select.*from", "description": "SQL注入混淆特征", "severity": "high"},
    {"pattern": r"<[^\>]*\bon(error|click|load|focus|blur)\s*=", "description": "DOM事件注入", "severity": "high"},
]

SAFE_PATTERNS: list[str] = [
    "Read(*)", "Glob(*)", "Grep(*)",
    "Bash(git status*)", "Bash(git diff*)", "Bash(git log*)",
    "Bash(git show*)", "Bash(git branch*)", "Bash(git tag*)",
    "Bash(git remote*)", "Bash(ls *)", "Bash(pwd)",
    "Bash(ps *)", "Bash(which *)", "Bash(cat *)",
]


@dataclass
class Classification:
    level: ClassificationLevel
    auto_action: AutoAction
    reason: str
    matched_pattern: str | None = None
    confidence: float = 1.0
    suggestions: list[str] = field(default_factory=list)

    @property
    def should_allow(self) -> bool:
        return self.auto_action == AutoAction.ALLOW

    @property
    def should_ask(self) -> bool:
        return self.auto_action == AutoAction.ASK

    @property
    def should_deny(self) -> bool:
        return self.auto_action == AutoAction.DENY


class AutoClassifier:
    def __init__(
        self,
        block_patterns: list[str] | None = None,
        dangerous_patterns: list[dict[str, Any]] | None = None,
        safe_patterns: list[str] | None = None,
        strict_mode: bool = True,
        enable_injection_detection: bool = True,
    ):
        self.block_patterns = block_patterns or BLOCK_PATTERNS.copy()
        self.dangerous_patterns = dangerous_patterns or DANGEROUS_PATTERNS.copy()
        self.safe_patterns = safe_patterns or SAFE_PATTERNS.copy()
        self.strict_mode = strict_mode
        self.enable_injection_detection = enable_injection_detection
        self._injection_regexes = self._compile_injection_regexes()

    def classify(self, operation: dict[str, Any]) -> Classification:
        tool_name = operation.get("tool_name", "")
        raw_input = operation.get("input", {})

        match_str = self._build_match_string(tool_name, raw_input)

        injection_result = self._check_injection(tool_name, match_str)
        if injection_result:
            return injection_result

        for pattern in self.block_patterns:
            if self._matches_pattern(match_str, pattern):
                return Classification(
                    level=ClassificationLevel.BLOCKED,
                    auto_action=AutoAction.DENY,
                    reason=f"Operation matches blocked pattern: {pattern}",
                    matched_pattern=pattern,
                )

        for pattern in self.safe_patterns:
            if self._matches_pattern(match_str, pattern):
                return Classification(
                    level=ClassificationLevel.SAFE,
                    auto_action=AutoAction.ALLOW,
                    reason=f"Operation matches safe pattern: {pattern}",
                    matched_pattern=pattern,
                )

        for pattern_info in self.dangerous_patterns:
            pattern = pattern_info["pattern"]
            if self._matches_pattern(match_str, pattern):
                severity = pattern_info.get("severity", "medium")
                level = self._severity_to_level(severity)
                return Classification(
                    level=level,
                    auto_action=AutoAction.ASK,
                    reason=f"Operation matches dangerous pattern: {pattern_info['description']}",
                    matched_pattern=pattern,
                )

        if self.strict_mode:
            return Classification(
                level=ClassificationLevel.CAUTION,
                auto_action=AutoAction.ASK,
                reason="Unknown operation - requires user confirmation",
                confidence=0.5,
            )

        return Classification(
            level=ClassificationLevel.SAFE,
            auto_action=AutoAction.ALLOW,
            reason="Unknown operation - allowed in non-strict mode",
            confidence=0.5,
        )

    def _build_match_string(self, tool_name: str, raw_input: dict[str, Any]) -> str:
        parts = [tool_name]
        for key in sorted(raw_input.keys()):
            value = raw_input[key]
            if isinstance(value, str):
                parts.append(f"{key}={value}")
            elif isinstance(value, list):
                parts.append(f"{key}={','.join(str(v) for v in value)}")
            else:
                parts.append(f"{key}={value}")
        return f"{' '.join(parts)}"

    def _matches_pattern(self, match_str: str, pattern: str) -> bool:
        if fnmatch.fnmatch(match_str, pattern):
            return True
        regex_pattern = fnmatch.translate(pattern)
        if re.match(regex_pattern, match_str):
            return True
        return False

    def _severity_to_level(self, severity: str) -> ClassificationLevel:
        severity_map = {
            "critical": ClassificationLevel.DANGEROUS,
            "high": ClassificationLevel.DANGEROUS,
            "medium": ClassificationLevel.CAUTION,
            "low": ClassificationLevel.CAUTION,
        }
        return severity_map.get(severity, ClassificationLevel.CAUTION)

    def _compile_injection_regexes(self) -> list[tuple[re.Pattern, dict[str, Any]]]:
        regexes = []
        for pattern_info in INJECTION_PATTERNS:
            try:
                compiled = re.compile(pattern_info["pattern"])
                regexes.append((compiled, pattern_info))
            except re.error:
                pass
        return regexes

    def _check_injection(self, tool_name: str, text: str) -> Classification | None:
        if not self.enable_injection_detection:
            return None
        
        # 只对命令行工具执行注入检测，文件内容不需要检测
        # Write/Edit 写入的文件内容可能是合法的代码（如 HTML、JS 等）
        command_tools = {"Bash", "Agent", "Grep", "WebFetch", "WebSearch"}
        if tool_name not in command_tools:
            return None
            
        for regex, pattern_info in self._injection_regexes:
            if regex.search(text):
                severity = pattern_info.get("severity", "high")
                level = self._severity_to_level(severity)
                return Classification(
                    level=level,
                    auto_action=AutoAction.DENY if severity == "critical" else AutoAction.ASK,
                    reason=f"Potential security threat detected: {pattern_info['description']}",
                    matched_pattern=pattern_info["pattern"],
                    confidence=0.9,
                )
        return None
