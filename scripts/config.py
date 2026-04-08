"""
配置管理模块 - 支持从 crush.json 和环境变量读取配置
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable


# 默认配置
DEFAULT_CONFIG = {
    "api_key": "",
    "api_url": "https://api.minimaxi.com/anthropic/v1/messages",
    "model": "MiniMax-M2.7",
    "temperature": 0.1,
    "max_turns": 20,
    "timeout": 180,
    "parallel_tool_calls": True,
    "multi_agent_enabled": True,
    "lsp": {},
    "permission": {
        "default": "ask",
        "rules": []
    }
}


@dataclass
class AgentConfig:
    """Agent 配置"""
    api_key: str = ""
    api_url: str = "https://api.minimaxi.com/anthropic/v1/messages"
    model: str = "MiniMax-M2.7"
    temperature: float = 0.1
    max_turns: int = 20
    timeout: int = 180
    parallel_tool_calls: bool = True
    multi_agent_enabled: bool = True


@dataclass
class Config:
    """全局配置"""
    api_key: str = ""
    api_url: str = "https://api.minimaxi.com/anthropic/v1/messages"
    model: str = "MiniMax-M2.7"
    temperature: float = 0.1
    max_turns: int = 20
    timeout: int = 180
    parallel_tool_calls: bool = True
    multi_agent_enabled: bool = True
    lsp: dict = field(default_factory=dict)
    permission: dict = field(default_factory=dict)
    _changed_callbacks: list[Callable] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        """从字典创建配置"""
        return cls(
            api_key=data.get("api_key", ""),
            api_url=data.get("api_url", DEFAULT_CONFIG["api_url"]),
            model=data.get("model", DEFAULT_CONFIG["model"]),
            temperature=data.get("temperature", DEFAULT_CONFIG["temperature"]),
            max_turns=data.get("max_turns", DEFAULT_CONFIG["max_turns"]),
            timeout=data.get("timeout", DEFAULT_CONFIG["timeout"]),
            parallel_tool_calls=data.get("parallel_tool_calls", DEFAULT_CONFIG["parallel_tool_calls"]),
            multi_agent_enabled=data.get("multi_agent_enabled", DEFAULT_CONFIG["multi_agent_enabled"]),
            lsp=data.get("lsp", {}),
            permission=data.get("permission", DEFAULT_CONFIG["permission"]),
        )

    def to_dict(self) -> dict:
        """转字典（不包含敏感信息的完整配置）"""
        return {
            "api_key": self.api_key,
            "api_url": self.api_url,
            "model": self.model,
            "temperature": self.temperature,
            "max_turns": self.max_turns,
            "timeout": self.timeout,
            "parallel_tool_calls": self.parallel_tool_calls,
            "multi_agent_enabled": self.multi_agent_enabled,
            "lsp": self.lsp,
            "permission": self.permission,
        }

    def to_public_dict(self) -> dict:
        """转字典（隐藏 api_key）"""
        d = self.to_dict()
        if d["api_key"]:
            d["api_key"] = mask_api_key(d["api_key"])
        return d

    def to_agent_config(self) -> AgentConfig:
        """转为 AgentConfig"""
        return AgentConfig(
            api_key=self.api_key,
            api_url=self.api_url,
            model=self.model,
            temperature=self.temperature,
            max_turns=self.max_turns,
            timeout=self.timeout,
            parallel_tool_calls=self.parallel_tool_calls,
            multi_agent_enabled=self.multi_agent_enabled,
        )


def mask_api_key(key: str) -> str:
    """隐藏 API key 中间部分"""
    if len(key) <= 8:
        return "***"
    return key[:4] + "***" + key[-4:]


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_file: str = "claude.json"):
        self.config_file = config_file
        self._config: Config = Config()
        self._changed_callbacks: list[Callable[[Config], None]] = []

    def load(self) -> Config:
        """加载配置（从文件 + 环境变量）"""
        # 先加载文件配置
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._config = Config.from_dict(data)
            except Exception as e:
                print(f"[Config] Failed to load {self.config_file}: {e}")
                self._config = Config()
        else:
            self._config = Config()

        # 环境变量覆盖（优先级更高）
        if os.environ.get("MINIMAX_API_KEY"):
            self._config.api_key = os.environ["MINIMAX_API_KEY"]
        if os.environ.get("MINIMAX_API_URL"):
            self._config.api_url = os.environ["MINIMAX_API_URL"]
        if os.environ.get("LLM_MODEL"):
            self._config.model = os.environ["LLM_MODEL"]

        return self._config

    def save(self, config: Config = None) -> bool:
        """保存配置到文件"""
        if config is None:
            config = self._config

        try:
            # 读取现有文件（保留其他字段）
            data = {}
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

            # 更新配置
            data.update(config.to_dict())

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            self._config = config
            return True
        except Exception as e:
            print(f"[Config] Failed to save {self.config_file}: {e}")
            return False

    def get(self) -> Config:
        """获取当前配置"""
        return self._config

    def update(self, data: dict) -> Config:
        """更新配置"""
        # 合并更新
        current = self._config.to_dict()
        current.update(data)
        self._config = Config.from_dict(current)
        
        # 触发变更回调
        self._notify_changed()
        
        return self._config

    def on_changed(self, callback: Callable[[Config], None]):
        """注册配置变更回调"""
        self._changed_callbacks.append(callback)

    def _notify_changed(self):
        """通知配置变更"""
        for cb in self._changed_callbacks:
            try:
                cb(self._config)
            except Exception as e:
                print(f"[Config] Callback error: {e}")


# 全局配置管理器
_config_manager: ConfigManager | None = None


def get_config_manager() -> ConfigManager:
    """获取全局配置管理器"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load()
    return _config_manager


def get_config() -> Config:
    """获取当前配置"""
    return get_config_manager().get()


def update_config(data: dict) -> Config:
    """更新配置"""
    return get_config_manager().update(data)
