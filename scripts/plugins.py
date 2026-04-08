"""
Plugin 系统 - 参考 Claude Code 的 plugins 设计

支持：
- 插件安装/卸载
- 内置插件
- 插件命令/技能/代理
- 插件钩子
"""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PluginMetadata:
    """插件元数据"""
    name: str
    version: str
    description: str
    author: str = ""
    license: str = "MIT"
    homepage: str = ""
    installed_at: str | None = None
    enabled: bool = True


@dataclass
class Plugin:
    """插件"""
    metadata: PluginMetadata
    path: Path
    tools: list = field(default_factory=list)
    skills: list = field(default_factory=list)
    agents: list = field(default_factory=list)
    hooks: dict = field(default_factory=dict)  # hook_name -> callback
    is_builtin: bool = False

    def load(self) -> bool:
        """加载插件"""
        try:
            # 动态导入插件模块
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                self.metadata.name,
                self.path / "__init__.py"
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # 获取插件提供的工具、技能、代理
                if hasattr(module, "register_tools"):
                    self.tools = module.register_tools()
                if hasattr(module, "register_skills"):
                    self.skills = module.register_skills()
                if hasattr(module, "register_agents"):
                    self.agents = module.register_agents()
                if hasattr(module, "register_hooks"):
                    self.hooks = module.register_hooks()

                return True
            return False
        except Exception as e:
            logger.error(f"Failed to load plugin {self.metadata.name}: {e}")
            return False


class PluginRegistry:
    """插件注册表"""

    def __init__(self):
        self._plugins: dict[str, Plugin] = {}
        self._builtin_plugins: dict[str, Plugin] = {}
        self._plugin_dir = Path.home() / ".claude-agent" / "plugins"
        self._ensure_plugin_dir()

    def _ensure_plugin_dir(self) -> None:
        """确保插件目录存在"""
        self._plugin_dir.mkdir(parents=True, exist_ok=True)

    def register_builtin(self, plugin: Plugin) -> None:
        """注册内置插件"""
        plugin.is_builtin = True
        self._builtin_plugins[plugin.metadata.name] = plugin
        self._plugins[plugin.metadata.name] = plugin
        logger.info(f"Registered builtin plugin: {plugin.metadata.name}")

    def install(self, source: str | Path) -> Plugin | None:
        """
        安装插件
        
        Args:
            source: 插件来源，可以是本地路径或 npm 包名
            
        Returns:
            安装的插件，失败返回 None
        """
        source = Path(source) if isinstance(source, str) else source

        if not source.exists():
            logger.error(f"Plugin source not found: {source}")
            return None

        # 读取插件元数据
        metadata = self._load_metadata(source)
        if not metadata:
            logger.error("Invalid plugin: missing metadata")
            return None

        # 检查是否已安装
        if metadata.name in self._plugins:
            logger.warning(f"Plugin {metadata.name} already installed")
            return self._plugins[metadata.name]

        # 复制到插件目录
        target_dir = self._plugin_dir / metadata.name
        if target_dir.exists():
            shutil.rmtree(target_dir)

        try:
            shutil.copytree(source, target_dir)

            plugin = Plugin(
                metadata=metadata,
                path=target_dir,
            )

            if plugin.load():
                metadata.installed_at = datetime.now().isoformat()
                self._plugins[metadata.name] = plugin
                self._save_installed_plugins()
                logger.info(f"Installed plugin: {metadata.name}")
                return plugin
            else:
                shutil.rmtree(target_dir)
                return None

        except Exception as e:
            logger.error(f"Failed to install plugin: {e}")
            if target_dir.exists():
                shutil.rmtree(target_dir)
            return None

    def uninstall(self, name: str) -> bool:
        """卸载插件"""
        if name not in self._plugins:
            return False

        plugin = self._plugins[name]
        if plugin.is_builtin:
            logger.warning(f"Cannot uninstall builtin plugin: {name}")
            return False

        # 删除插件目录
        try:
            if plugin.path.exists():
                shutil.rmtree(plugin.path)
            del self._plugins[name]
            self._save_installed_plugins()
            logger.info(f"Uninstalled plugin: {name}")
            return True
        except Exception as e:
            logger.error(f"Failed to uninstall plugin {name}: {e}")
            return False

    def enable(self, name: str) -> bool:
        """启用插件"""
        if name not in self._plugins:
            return False
        self._plugins[name].metadata.enabled = True
        self._save_installed_plugins()
        return True

    def disable(self, name: str) -> bool:
        """禁用插件"""
        if name not in self._plugins:
            return False
        if self._plugins[name].is_builtin:
            logger.warning(f"Cannot disable builtin plugin: {name}")
            return False
        self._plugins[name].metadata.enabled = False
        self._save_installed_plugins()
        return True

    def get(self, name: str) -> Plugin | None:
        """获取插件"""
        return self._plugins.get(name)

    def list_all(self) -> list[Plugin]:
        """列出所有插件"""
        return list(self._plugins.values())

    def list_enabled(self) -> list[Plugin]:
        """列出已启用的插件"""
        return [p for p in self._plugins.values() if p.metadata.enabled]

    def _load_metadata(self, path: Path) -> PluginMetadata | None:
        """从路径加载插件元数据"""
        metadata_file = path / "plugin.json"

        if not metadata_file.exists():
            # 尝试从 setup.py 或 pyproject.toml
            return None

        try:
            with open(metadata_file, encoding="utf-8") as f:
                data = json.load(f)

            return PluginMetadata(
                name=data.get("name", ""),
                version=data.get("version", "1.0.0"),
                description=data.get("description", ""),
                author=data.get("author", ""),
                license=data.get("license", "MIT"),
                homepage=data.get("homepage", ""),
            )
        except Exception as e:
            logger.error(f"Failed to load plugin metadata: {e}")
            return None

    def _save_installed_plugins(self) -> None:
        """保存已安装插件列表"""
        installed_file = self._plugin_dir / "installed.json"

        installed = []
        for name, plugin in self._plugins.items():
            if not plugin.is_builtin:
                installed.append({
                    "name": name,
                    "version": plugin.metadata.version,
                    "path": str(plugin.path),
                    "enabled": plugin.metadata.enabled,
                    "installed_at": plugin.metadata.installed_at,
                })

        try:
            with open(installed_file, "w", encoding="utf-8") as f:
                json.dump(installed, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save installed plugins: {e}")

    def load_installed(self) -> None:
        """加载已安装的插件"""
        installed_file = self._plugin_dir / "installed.json"

        if not installed_file.exists():
            return

        try:
            with open(installed_file, encoding="utf-8") as f:
                installed = json.load(f)

            for item in installed:
                plugin_path = Path(item["path"])
                if not plugin_path.exists():
                    continue

                metadata = self._load_metadata(plugin_path)
                if not metadata:
                    continue

                metadata.installed_at = item.get("installed_at")
                metadata.enabled = item.get("enabled", True)

                plugin = Plugin(metadata=metadata, path=plugin_path)
                if plugin.load():
                    self._plugins[metadata.name] = plugin
                    logger.info(f"Loaded plugin: {metadata.name}")

        except Exception as e:
            logger.error(f"Failed to load installed plugins: {e}")


# 全局单例
_plugin_registry: PluginRegistry | None = None


def get_plugin_registry() -> PluginRegistry:
    """获取插件注册表单例"""
    global _plugin_registry
    if _plugin_registry is None:
        _plugin_registry = PluginRegistry()
    return _plugin_registry


def reset_plugin_registry() -> None:
    """重置插件注册表"""
    global _plugin_registry
    _plugin_registry = None
