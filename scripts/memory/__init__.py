"""
Memory 模块 - 记忆系统

提供跨会话的持久化记忆存储和检索功能。
"""
from .extract_memories import (
    ExtractionResult,
    MemoryExtractor,
    detect_explicit_save,
    extract_memories_from_messages,
    mark_explicit_save,
    reset_extraction_state,
    should_skip_extraction,
)
from .extract_prompts import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_PROMPT_TEMPLATE
from .freshness import FreshnessChecker
from .llm_selector import LLMSelector
from .memory_dream import MemoryDream
from .memory_retriever import MemoryRetriever
from .memory_store import MemoryStore
from .session_memory import SessionMemory
from .types import FreshnessStatus, FrontmatterMetadata, MemoryHeader, MemoryType, RelevantMemory

# 导入 tools 以注册到全局注册表
from . import tools

__all__ = [
    # Types
    "MemoryType",
    "MemoryHeader",
    "RelevantMemory",
    "FreshnessStatus",
    "FrontmatterMetadata",
    # Core
    "FreshnessChecker",
    "MemoryStore",
    "MemoryRetriever",
    "MemoryDream",
    "SessionMemory",
    "LLMSelector",
    # Extraction
    "MemoryExtractor",
    "ExtractionResult",
    "extract_memories_from_messages",
    "should_skip_extraction",
    "detect_explicit_save",
    "mark_explicit_save",
    "reset_extraction_state",
    "EXTRACTION_SYSTEM_PROMPT",
    "EXTRACTION_USER_PROMPT_TEMPLATE",
    # Tools
    "tools",
]
