"""
SubagentType 枚举 - 子代理类型定义
"""
from __future__ import annotations

from enum import Enum


class SubagentType(Enum):
    """
    子代理类型枚举
    
    参考 Claude Code 的 AgentTool 设计:
    - Explore: 只读代码探索
    - Plan: 复杂任务规划
    - Verification: 测试验证
    - GeneralPurpose: 通用类型，默认选项
    """
    EXPLORE = "Explore"
    PLAN = "Plan"
    VERIFICATION = "Verification"
    GENERAL_PURPOSE = "GeneralPurpose"

    @classmethod
    def from_string(cls, value: str) -> SubagentType:
        """从字符串创建 SubagentType"""
        for member in cls:
            if member.value == value or member.name == value:
                return member
        raise ValueError(f"Invalid SubagentType: {value}")

    @property
    def description(self) -> str:
        """返回该类型的描述"""
        desc_map = {
            "Explore": "只读代码探索代理，用于理解代码结构",
            "Plan": "复杂任务规划代理，用于分解和规划任务",
            "Verification": "测试验证代理，用于验证代码正确性",
            "GeneralPurpose": "通用目的代理，用于处理任意任务",
        }
        return desc_map.get(self.value, "")


SUBAGENT_TYPE_NAMES = [t.value for t in SubagentType]
