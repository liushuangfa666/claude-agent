"""
LLM Pricing - Token 费用计算和进度条显示
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

# MiniMax-M2.7 pricing (per 1M tokens)
DEFAULT_PRICING = {
    "MiniMax-M2.7": {"input": 0.30, "output": 1.20, "currency": "USD"},
    "MiniMax-M2": {"input": 0.30, "output": 1.20, "currency": "USD"},
}

# Default model
DEFAULT_MODEL = "MiniMax-M2.7"


@dataclass
class TokenUsage:
    """Token 使用情况"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def cost(self, pricing: dict) -> float:
        """计算费用（美元）"""
        model = pricing.get("model", DEFAULT_MODEL)
        p = DEFAULT_PRICING.get(model, DEFAULT_PRICING[DEFAULT_MODEL])
        input_cost = (self.input_tokens / 1_000_000) * p["input"]
        output_cost = (self.output_tokens / 1_000_000) * p["output"]
        return input_cost + output_cost


@dataclass
class PricingConfig:
    """价格配置"""
    model: str = DEFAULT_MODEL
    custom_pricing: dict | None = None

    def get_pricing(self) -> dict:
        """获取定价"""
        if self.custom_pricing:
            return self.custom_pricing
        return DEFAULT_PRICING.get(self.model, DEFAULT_PRICING[DEFAULT_MODEL])


def format_cost(cost: float) -> str:
    """格式化费用显示"""
    if cost < 0.0001:
        return "$0.00"
    elif cost < 0.01:
        return f"${cost:.4f}"
    elif cost < 1:
        return f"${cost:.3f}"
    else:
        return f"${cost:.2f}"


def render_progress_bar(used: int, total: int, width: int = 30) -> str:
    """渲染进度条
    
    Args:
        used: 已使用的 token 数
        total: 总容量
        width: 进度条字符宽度
    
    Returns:
        格式化的进度条字符串
    """
    if total <= 0:
        total = 180000  # 默认 180k
    
    pct = min(used / total, 1.0)
    filled = int(width * pct)
    bar = "#" * filled + "." * (width - filled)
    return f"[tokens: {used:,} / {total:,} {bar} {pct*100:.1f}%]"


def render_token_info(
    usage: TokenUsage,
    cost: float,
    total_context: int = 180000,
    show_progress: bool = True
) -> str:
    """渲染完整的 token 信息
    
    Args:
        usage: Token 使用情况
        cost: 本次费用
        total_context: 总上下文容量
        show_progress: 是否显示进度条
    
    Returns:
        格式化的信息字符串
    """
    lines = []
    
    # 进度条
    if show_progress:
        progress = render_progress_bar(usage.total_tokens, total_context)
        lines.append(progress)
    
    # 详细信息
    lines.append(
        f"  Input: {usage.input_tokens:,} tokens | "
        f"Output: {usage.output_tokens:,} tokens | "
        f"Total: {usage.total_tokens:,} tokens"
    )
    
    # 费用
    lines.append(f"  Cost: {format_cost(cost)}")
    
    return "\n".join(lines)


def print_token_info(
    usage: TokenUsage,
    cost: float,
    total_context: int = 180000,
    file=sys.stdout
) -> None:
    """打印 token 信息到控制台
    
    Args:
        usage: Token 使用情况
        cost: 本次费用
        total_context: 总上下文容量
        file: 输出文件对象
    """
    info = render_token_info(usage, cost, total_context)
    print(info, file=file)


def extract_usage_from_response(response: dict) -> TokenUsage | None:
    """从 API 响应中提取 usage 信息
    
    Args:
        response: API 响应字典
    
    Returns:
        TokenUsage 对象，如果提取失败返回 None
    """
    if not response:
        return None
    
    # 尝试多个常见的 usage 字段位置
    usage = response.get("usage")
    if not usage and "model_usage" in response:
        usage = response.get("model_usage")
    
    if not usage:
        return None
    
    # 提取字段
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
    
    if input_tokens == 0 and output_tokens == 0:
        return None
    
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens
    )


# 全局配置实例
_pricing_config = PricingConfig()


def configure_pricing(model: str = None, custom_pricing: dict = None) -> None:
    """配置定价信息
    
    Args:
        model: 模型名称
        custom_pricing: 自定义定价 {"input": x.xx, "output": x.xx}
    """
    global _pricing_config
    if model:
        _pricing_config.model = model
    if custom_pricing:
        _pricing_config.custom_pricing = custom_pricing


def get_pricing_config() -> PricingConfig:
    """获取当前定价配置"""
    return _pricing_config
