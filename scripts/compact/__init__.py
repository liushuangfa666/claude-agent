"""
Compact Module - 上下文压缩系统
"""
from .auto_compact import AUTOCOMPACT_BUFFER_TOKENS, try_auto_compact
from .compact_manager import CompactConfig, CompactionResult, CompactManager
from .context_collapse import ContextCollapser, CollapseStore, create_collapser
from .micro_compact import MicroCompactor, micro_compact
from .reactive_compact import is_prompt_too_long_error, try_reactive_compact
from .snip_compact import SnipCompactor, snip_compact
from .token_counter import count_messages_tokens, count_tokens

from .message_scorer import (
    score_message_importance,
    get_important_messages,
    get_compactable_messages,
    build_importance_index,
    find_key_decisions,
)
from .token_budget import (
    calculate_token_budget,
    calculate_budget_info,
    should_trigger_compaction,
    estimate_response_tokens,
)

__all__ = [
    "count_tokens",
    "count_messages_tokens",
    "CompactManager",
    "CompactConfig",
    "CompactionResult",
    "try_auto_compact",
    "AUTOCOMPACT_BUFFER_TOKENS",
    "try_reactive_compact",
    "is_prompt_too_long_error",
    "SnipCompactor",
    "snip_compact",
    "MicroCompactor",
    "micro_compact",
    "ContextCollapser",
    "CollapseStore",
    "create_collapser",
    "calculate_token_budget",
    "calculate_budget_info",
    "should_trigger_compaction",
    "estimate_response_tokens",
    "score_message_importance",
    "get_important_messages",
    "get_compactable_messages",
    "build_importance_index",
    "find_key_decisions",
]
