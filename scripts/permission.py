"""
权限规则引擎 - 参考 Claude Code 的权限系统设计
支持模式匹配： "Bash(git *)", "Edit(*.env)", "Bash(rm *)"
"""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field


@dataclass
class PermissionResult:
    """权限检查结果"""
    behavior: str           # "allow" | "deny" | "ask"
    updated_input: dict     # 可能的输入替换
    reason: str | None = None


@dataclass
class DenialTracking:
    """拒绝追踪状态（对应 Claude Code 的 DenialTrackingState）"""
    denials: dict[str, int] = field(default_factory=dict)  # tool_name -> count
    asks: dict[str, int] = field(default_factory=dict)  # tool_name -> count of consecutive asks

    def record_denial(self, tool_name: str):
        self.denials[tool_name] = self.denials.get(tool_name, 0) + 1

    def get_count(self, tool_name: str) -> int:
        return self.denials.get(tool_name, 0)

    def should_auto_deny(self, tool_name: str, threshold: int = 3) -> bool:
        """连续拒绝 N 次后自动拒绝"""
        return self.get_count(tool_name) >= threshold

    def record_ask(self, tool_name: str):
        """记录一次 ask"""
        self.asks[tool_name] = self.asks.get(tool_name, 0) + 1

    def should_auto_allow(self, tool_name: str, threshold: int = 2) -> bool:
        """连续 ask N 次后自动允许"""
        return self.asks.get(tool_name, 0) >= threshold

    def reset_ask(self, tool_name: str):
        """重置 ask 计数（当工具成功执行后）"""
        self.asks[tool_name] = 0


class PermissionRule:
    """单条权限规则"""

    def __init__(self, pattern: str, behavior: str, reason: str = ""):
        """
        pattern: "ToolName(args)" 如 "Bash(git *)", "Edit(*.env)"
        behavior: "allow" | "deny" | "ask"
        """
        self.pattern = pattern
        self.behavior = behavior
        self.reason = reason
        self.tool_name, self.arg_pattern = self._parse_pattern(pattern)

    def _parse_pattern(self, pattern: str) -> tuple[str, str]:
        """解析 'ToolName(args)' -> ('ToolName', 'args')"""
        match = re.match(r"^([A-Za-z0-9_]+)\((.*)\)$", pattern.strip())
        if match:
            return match.group(1), match.group(2)
        return pattern, "*"

    def matches(self, tool_name: str, raw_input: dict) -> bool:
        """检查输入是否匹配此规则"""
        if self.tool_name != tool_name:
            return False
        if self.arg_pattern == "*":
            return True
        # 从输入中提取关键字段用于匹配
        input_str = self._input_to_string(raw_input)
        return fnmatch.fnmatch(input_str, self.arg_pattern)

    def _input_to_string(self, raw_input: dict) -> str:
        """把输入字典转成可匹配的字符串"""
        parts = []
        for key in sorted(raw_input.keys()):
            value = raw_input[key]
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.append(" ".join(str(v) for v in value))
            else:
                parts.append(str(value))
        return " ".join(parts)


class PermissionEngine:
    """
    权限规则引擎
    参考 Claude Code 的权限系统，支持：
    - allow/deny/ask 三级
    - 规则模式匹配
    - 拒绝追踪（连续拒绝后降级）
    """

    def __init__(self):
        self.rules: list[PermissionRule] = []
        self.denial_tracking = DenialTracking()
        self._default_behavior = "ask"

    def add_rule(self, pattern: str, behavior: str, reason: str = ""):
        """添加一条规则"""
        self.rules.append(PermissionRule(pattern, behavior, reason))

    def set_default(self, behavior: str):
        self._default_behavior = behavior

    def check(self, tool_name: str, raw_input: dict) -> PermissionResult:
        """
        检查工具调用是否有权限
        """
        # 按优先级匹配规则
        for rule in self.rules:
            if rule.matches(tool_name, raw_input):
                if rule.behavior == "deny":
                    self.denial_tracking.record_denial(tool_name)
                    self.denial_tracking.reset_ask(tool_name)
                    return PermissionResult(
                        behavior="deny",
                        updated_input=raw_input,
                        reason=rule.reason or f"{tool_name} 被规则 {rule.pattern} 拒绝"
                    )
                # allow 或 ask 都重置 ask 计数
                self.denial_tracking.reset_ask(tool_name)
                return PermissionResult(
                    behavior=rule.behavior,
                    updated_input=raw_input,
                    reason=rule.reason
                )

        # 拒绝追踪检查
        if self.denial_tracking.should_auto_deny(tool_name):
            return PermissionResult(
                behavior="deny",
                updated_input=raw_input,
                reason=f"连续拒绝触发自动禁止: {tool_name}"
            )

        # ask 计数检查：连续 ask 后自动允许
        if self.denial_tracking.should_auto_allow(tool_name):
            self.denial_tracking.reset_ask(tool_name)
            return PermissionResult(
                behavior="allow",
                updated_input=raw_input,
                reason=f"连续确认请求后自动允许: {tool_name}"
            )

        # 默认行为处理
        default_result = PermissionResult(behavior=self._default_behavior, updated_input=raw_input)
        
        # 只有 ask 行为才计数
        if self._default_behavior == "ask":
            self.denial_tracking.record_ask(tool_name)
        
        return default_result

    def allow(self, pattern: str, reason: str = ""):
        """快捷方法：添加 allow 规则"""
        self.add_rule(pattern, "allow", reason)

    def deny(self, pattern: str, reason: str = ""):
        """快捷方法：添加 deny 规则"""
        self.add_rule(pattern, "deny", reason)

    def build_default_engine() -> PermissionEngine:
        """构建默认权限引擎（安全的默认值）"""
        engine = PermissionEngine()
        engine.set_default("allow")  # 默认允许（方便测试）

        # 危险操作需询问
        engine.add_rule("Bash(rm *)", "ask", "删除操作需要确认")
        engine.add_rule("Bash(mv *)", "ask", "移动/重命名操作需要确认")
        engine.add_rule("Edit(*.env)", "ask", "修改环境变量需要确认")
        engine.add_rule("Write(*.json)", "ask", "写入 JSON 文件需要确认")

        # 安全操作全部允许
        engine.allow("Bash(git *)", "git 读取操作安全")
        engine.allow("Bash(ls *)", "列出目录安全")
        engine.allow("Bash(ps *)", "查看进程安全")
        engine.allow("Bash(mkdir *)", "创建目录安全")
        engine.allow("Bash(mkdirp *)", "创建目录安全")
        engine.allow("Bash(touch *)", "创建文件安全")
        engine.allow("Bash(echo *)", "输出文本安全")
        engine.allow("Bash(cat *)", "查看文件安全")
        engine.allow("Bash(cd *)", "切换目录安全")
        engine.allow("Bash(pwd)", "获取当前目录安全")
        engine.allow("Bash(whoami)", "获取用户名安全")
        engine.allow("Read(*)", "读取文件安全")
        engine.allow("Glob(*)", "搜索文件安全")
        engine.allow("Grep(*)", "搜索内容安全")
        engine.allow("Write(*)", "写入文件默认允许")
        engine.allow("Edit(*)", "编辑文件默认允许")

        return engine
