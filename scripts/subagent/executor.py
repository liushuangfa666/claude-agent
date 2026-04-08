"""
子代理执行器 - Subagent Executor
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from typing import Any

from .prompts import get_subagent_prompt_with_context
from .registry import SubagentInfo, SubagentRegistry, get_subagent_registry
from .tool_filter import filter_tools_by_type, get_allowed_tools
from .types import SubagentType


class SubagentExecutor:
    """子代理执行器"""

    def __init__(self, registry: SubagentRegistry | None = None):
        self.registry = registry or get_subagent_registry()

    async def execute(
        self,
        prompt: str,
        subagent_type: SubagentType,
        description: str = "",
        name: str = "",
        tools: list[dict] | None = None,
        context: dict[str, Any] | None = None,
        isolation: str = "none",
        worktree_branch: str = "",
    ) -> SubagentInfo:
        """执行子代理任务"""
        agent_info = self.registry.create(
            name=name or f"{subagent_type.value.lower()}_agent",
            subagent_type=subagent_type,
            description=description,
            prompt=prompt,
        )

        self.registry.update_status(agent_info.agent_id, "running")

        worktree_path = None
        original_cwd = None

        try:
            # 处理 worktree 隔离
            if isolation == "worktree":
                worktree_path = await self._create_worktree(agent_info.agent_id, worktree_branch)
                original_cwd = os.getcwd()
                os.chdir(worktree_path)

            system_prompt = get_subagent_prompt_with_context(
                subagent_type.value,
                task_context=context.get("task_context") if context else None,
            )

            if tools is not None:
                allowed_tools = filter_tools_by_type(tools, subagent_type.value)
            else:
                allowed_tool_names = get_allowed_tools(subagent_type.value)
                allowed_tools = None

            result = await self._run_agent(
                agent_info=agent_info,
                system_prompt=system_prompt,
                prompt=prompt,
                tools=allowed_tools,
            )

            self.registry.update_status(
                agent_info.agent_id,
                "completed",
                result=result,
            )

        except Exception as e:
            self.registry.update_status(
                agent_info.agent_id,
                "failed",
                error=str(e),
            )
            raise

        finally:
            # 恢复原始工作目录
            if original_cwd and worktree_path:
                try:
                    os.chdir(original_cwd)
                    await self._cleanup_worktree(worktree_path)
                except Exception:
                    pass  # 忽略清理错误

        return agent_info

    async def _run_agent(
        self,
        agent_info: SubagentInfo,
        system_prompt: str,
        prompt: str,
        tools: list[dict] | None,
    ) -> str:
        """运行实际代理的内部方法"""
        try:
            from scripts.agent import Agent, AgentConfig, Message
            from scripts.tool import get_registry
        except ImportError:
            try:
                from agent import Agent, AgentConfig, Message
                from tool import get_registry
            except ImportError:
                raise ImportError(
                    "Could not import Agent modules. Ensure the project root is in PYTHONPATH."
                )

        # 从 tools 列表提取允许的工具名
        allowed_tool_names = None
        if tools is not None:
            allowed_tool_names = [t.get("name") for t in tools if t.get("name")]

        config = AgentConfig(timeout=120, max_turns=20, allowed_tools=allowed_tool_names)
        agent = Agent(config)

        agent.messages.append(Message(role="system", content=system_prompt))
        agent.messages.append(Message(role="user", content=prompt))

        final_text = ""
        try:
            async for event in agent.run_stream(prompt):
                if event.type == "text":
                    final_text += event.content
                elif event.type == "done":
                    if event.content:
                        final_text = event.content
        except Exception as e:
            raise RuntimeError(f"Agent execution failed: {e}")

        return final_text

    async def execute_background(
        self,
        prompt: str,
        subagent_type: SubagentType,
        description: str = "",
        name: str = "",
    ) -> SubagentInfo:
        """后台执行子代理任务"""
        agent_info = self.registry.create(
            name=name or f"{subagent_type.value.lower()}_agent",
            subagent_type=subagent_type,
            description=description,
            prompt=prompt,
        )

        self.registry.update_status(agent_info.agent_id, "running")
        asyncio.create_task(self._background_task(agent_info.agent_id))

        return agent_info

    async def _background_task(self, agent_id: str) -> None:
        """后台执行任务"""
        try:
            agent_info = self.registry.get(agent_id)
            if agent_info is None:
                logger.error(f"Agent {agent_id} not found in registry")
                return

            await self.execute(
                prompt=agent_info.prompt,
                subagent_type=agent_info.subagent_type,
                description=agent_info.description,
                name=agent_info.name,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Background task failed: {e}")
            self.registry.update_status(agent_id, "failed", error=str(e))

    def get_status(self, agent_id: str) -> SubagentInfo | None:
        return self.registry.get(agent_id)

    def stop(self, agent_id: str) -> bool:
        return self.registry.update_status(agent_id, "stopped")

    async def _create_worktree(self, agent_id: str, branch: str = "") -> str:
        """
        创建 Git worktree 用于隔离执行

        Args:
            agent_id: 代理 ID
            branch: 分支名（可选）

        Returns:
            worktree 路径
        """
        if not branch:
            branch = f"subagent-{agent_id}"

        # 检查是否在 git 仓库中
        if not os.path.exists(".git") and not os.path.exists(os.path.join(".git")):
            # 非 git 仓库，使用临时目录
            worktree_path = tempfile.mkdtemp(prefix=f"agent-{agent_id}-")
            return worktree_path

        try:
            # 检查 git 是否可用
            import subprocess
            subprocess.run(["git", "rev-parse", "--git-dir"],
                         capture_output=True, check=True)

            # 创建 worktree
            worktree_path = os.path.join(".git", "worktrees", f"agent-{agent_id}")
            os.makedirs(worktree_path, exist_ok=True)

            # 创建分支（如果不存在）
            result = subprocess.run(
                ["git", "rev-parse", "--verify", branch],
                capture_output=True
            )
            if result.returncode != 0:
                subprocess.run(["git", "checkout", "-b", branch], check=True)

            # 创建 worktree
            worktree_dir = os.path.join(os.path.dirname(os.getcwd()), f".agent-worktree-{agent_id}")
            os.makedirs(worktree_dir, exist_ok=True)

            subprocess.run(
                ["git", "worktree", "add", worktree_dir, branch],
                capture_output=True,
                check=True
            )

            logger.info(f"Created worktree at {worktree_dir}")
            return worktree_dir

        except Exception as e:
            logger.warning(f"Failed to create worktree, using temp directory: {e}")
            worktree_path = tempfile.mkdtemp(prefix=f"agent-{agent_id}-")
            return worktree_path

    async def _cleanup_worktree(self, worktree_path: str) -> None:
        """
        清理 worktree

        Args:
            worktree_path: worktree 路径
        """
        if not worktree_path or ".agent-worktree-" not in worktree_path:
            return

        try:
            # 移除 worktree
            import subprocess
            result = subprocess.run(
                ["git", "worktree", "remove", worktree_path, "--force"],
                capture_output=True
            )
            if result.returncode == 0:
                logger.info(f"Removed worktree at {worktree_path}")
            else:
                # 直接删除目录
                shutil.rmtree(worktree_path, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Failed to cleanup worktree: {e}")
            shutil.rmtree(worktree_path, ignore_errors=True)


_executor: SubagentExecutor | None = None


def get_subagent_executor() -> SubagentExecutor:
    """获取全局子代理执行器"""
    global _executor
    if _executor is None:
        _executor = SubagentExecutor()
    return _executor


def create_subagent_executor(
    registry: SubagentRegistry | None = None,
) -> SubagentExecutor:
    """创建新的子代理执行器"""
    return SubagentExecutor(registry=registry)
