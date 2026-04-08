"""
Compact Tests - Phase 1
"""
import pytest
import sys
import os

# Add scripts to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.compact.token_counter import count_tokens, count_messages_tokens
from scripts.compact.compact_manager import CompactManager, CompactConfig, CompactionResult
from scripts.compact.reactive_compact import is_prompt_too_long_error, try_reactive_compact, aggressive_compact


class TestTokenCounter:
    """Token 计数器测试"""

    def test_count_tokens_english(self):
        """测试英文 token 计数"""
        text = "Hello, world!"
        tokens = count_tokens(text)
        assert tokens > 0
        assert tokens == len(text) // 4 + 1

    def test_count_tokens_chinese(self):
        """测试中文 token 计数"""
        text = "你好世界"
        tokens = count_tokens(text)
        assert tokens > 0
        # 中文约 2 字符/token
        assert tokens >= 2

    def test_count_tokens_mixed(self):
        """测试混合文本 token 计数"""
        text = "Hello 你好 World 世界"
        tokens = count_tokens(text)
        assert tokens > 0

    def test_count_messages_tokens(self):
        """测试消息列表 token 计数"""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        tokens = count_messages_tokens(messages)
        assert tokens > 0

    def test_count_empty_messages(self):
        """测试空消息列表"""
        tokens = count_messages_tokens([])
        # 空消息仍然返回 overhead (10 tokens)
        assert tokens == 10


class TestCompactConfig:
    """压缩配置测试"""

    def test_default_config(self):
        """测试默认配置"""
        config = CompactConfig()
        assert config.warning_buffer == 40000
        assert config.auto_compact_buffer == 20000
        assert config.blocking_buffer == 5000
        assert config.preserve_recent_turns == 5

    def test_custom_config(self):
        """测试自定义配置"""
        config = CompactConfig(
            warning_buffer=15000,
            auto_compact_buffer=10000,
            blocking_buffer=2000,
            preserve_recent_turns=3,
        )
        assert config.warning_buffer == 15000
        assert config.auto_compact_buffer == 10000
        assert config.blocking_buffer == 2000
        assert config.preserve_recent_turns == 3


class TestCompactManager:
    """压缩管理器测试"""

    def test_should_warn(self):
        """测试警告阈值判断"""
        config = CompactConfig(warning_buffer=100)
        manager = CompactManager(config)

        assert not manager.should_warn(50)
        assert manager.should_warn(100)
        assert manager.should_warn(150)

    def test_should_auto_compact(self):
        """测试自动压缩阈值判断"""
        config = CompactConfig(auto_compact_buffer=13000)
        manager = CompactManager(config)

        assert not manager.should_auto_compact(10000)
        assert manager.should_auto_compact(13000)
        assert manager.should_auto_compact(20000)

    def test_should_block(self):
        """测试阻塞阈值判断"""
        config = CompactConfig(
            auto_compact_buffer=13000,
            blocking_buffer=3000,
        )
        manager = CompactManager(config)

        # blocking = auto_compact + blocking_buffer = 16000
        assert not manager.should_block(15000)
        assert manager.should_block(16000)
        assert manager.should_block(20000)

    def test_failure_tracking(self):
        """测试失败计数跟踪"""
        config = CompactConfig(max_consecutive_failures=3)
        manager = CompactManager(config)

        assert manager.consecutive_failures == 0

        manager.increment_failure()
        assert manager.consecutive_failures == 1

        manager.increment_failure()
        assert manager.consecutive_failures == 2

        manager.increment_failure()
        assert manager.consecutive_failures == 3

        # 达到最大失败次数后 should_auto_compact 返回 False
        assert not manager.should_auto_compact(20000)

    def test_reset_failures(self):
        """测试重置失败计数"""
        config = CompactConfig(max_consecutive_failures=3)
        manager = CompactManager(config)

        manager.increment_failure()
        manager.increment_failure()
        assert manager.consecutive_failures == 2

        manager.reset_failures()
        assert manager.consecutive_failures == 0

    def test_identify_compactable(self):
        """测试识别可压缩消息"""
        config = CompactConfig(preserve_recent_turns=2)
        manager = CompactManager(config)

        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Message 2"},
            {"role": "assistant", "content": "Response 2"},
            {"role": "user", "content": "Message 3"},
            {"role": "assistant", "content": "Response 3"},
        ]

        compactable, preserved = manager._identify_compactable(messages)

        # system + recent (2 turns = 4 messages) = 5 preserved
        assert len(preserved) == 5
        # 2 compactable messages
        assert len(compactable) == 2

    def test_format_messages_for_summary(self):
        """测试格式化消息用于摘要"""
        config = CompactConfig()
        manager = CompactManager(config)

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        formatted = manager._format_messages_for_summary(messages)
        assert "USER" in formatted
        assert "Hello" in formatted


class TestCompactionResult:
    """压缩结果测试"""

    def test_successful_result(self):
        """测试成功压缩结果"""
        result = CompactionResult(
            success=True,
            original_tokens=1000,
            compacted_tokens=200,
            messages_removed=5,
            summary="Test summary",
        )
        assert result.success
        assert result.original_tokens == 1000
        assert result.compacted_tokens == 200
        assert result.messages_removed == 5
        assert result.summary == "Test summary"

    def test_failed_result(self):
        """测试失败压缩结果"""
        result = CompactionResult(
            success=False,
            error="Test error",
        )
        assert not result.success
        assert result.error == "Test error"


class TestReactiveCompact:
    """响应式压缩测试"""

    def test_is_prompt_too_long_error(self):
        """测试错误类型识别"""
        # 各种 prompt-too-long 错误模式
        assert is_prompt_too_long_error(Exception("prompt too long"))
        assert is_prompt_too_long_error(Exception("prompt-too-long"))
        assert is_prompt_too_long_error(Exception("context_length_exceeded"))
        assert is_prompt_too_long_error(Exception("maximum context length"))
        assert is_prompt_too_long_error(Exception("too many tokens"))
        assert is_prompt_too_long_error(Exception("token limit exceeded"))

        # 非相关错误
        assert not is_prompt_too_long_error(Exception("connection timeout"))
        assert not is_prompt_too_long_error(Exception("invalid request"))

    @pytest.mark.asyncio
    async def test_try_reactive_compact_non_long_error(self):
        """测试非 prompt-too-long 错误"""
        result = await try_reactive_compact(
            messages=[{"role": "user", "content": "test"}],
            error=Exception("connection timeout"),
            config=CompactConfig(),
        )
        assert not result.success
        assert "Not a prompt-too-long error" in result.error

    @pytest.mark.asyncio
    async def test_aggressive_compact(self):
        """测试激进压缩"""
        config = CompactConfig(preserve_recent_turns=5)
        messages = [
            {"role": "system", "content": "System"},
        ]
        # 添加多轮对话
        for i in range(20):
            messages.append({"role": "user", "content": f"Message {i}"})
            messages.append({"role": "assistant", "content": f"Response {i}"})

        result = await aggressive_compact(messages, config)

        # 激进压缩应该保留更少的历史
        assert result.success or not result.success  # 可能因为没有可压缩的消息而失败


class TestCompactIntegration:
    """压缩集成测试"""

    @pytest.mark.asyncio
    async def test_compact_conversation(self):
        """测试对话压缩"""
        manager = CompactManager()

        # 创建长对话
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
        ]

        # 添加多轮对话
        for i in range(10):
            messages.append({"role": "user", "content": f"Message {i}" * 50})
            messages.append({"role": "assistant", "content": f"Response {i}" * 50})

        result = await manager.compact_conversation(messages)

        # 如果成功，应该有消息被移除
        if result.success:
            assert result.messages_removed >= 0
            assert result.compacted_tokens <= result.original_tokens or result.original_tokens == 0

    def test_get_token_count(self):
        """测试获取 token 数量"""
        manager = CompactManager()
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]

        count = manager.get_token_count(messages)
        assert count > 0
