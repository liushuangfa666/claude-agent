"""
WebBrowserTool - 使用多Agent系统的网页浏览器工具

使用 multi_agent 协调器架构：
- Coordinator: 规划浏览策略
- Worker: 执行具体浏览任务
- Team: 多Worker并行抓取

引用文档：docs/MULTI_AGENT_DESIGN.md
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

try:
    from scripts.tool import BaseTool, ToolResult
except ImportError:
    from tool import BaseTool, ToolResult

try:
    from scripts.web_tools import WebFetchTool, WebSearchTool
except ImportError:
    from web_tools import WebFetchTool, WebSearchTool


logger = logging.getLogger(__name__)


@dataclass
class BrowserAction:
    """浏览器操作"""
    action_type: str  # "navigate", "click", "input", "scroll", "screenshot"
    selector: str = ""
    value: str = ""
    description: str = ""


@dataclass
class PageState:
    """页面状态"""
    url: str
    title: str = ""
    content: str = ""
    links: list[dict] = field(default_factory=list)
    forms: list[dict] = field(default_factory=list)
    error: str = ""


class CoordinatorAgent:
    """
    协调Agent - 规划浏览策略

    职责：
    1. 分析用户目标
    2. 制定浏览计划
    3. 协调 Worker 执行
    4. 处理异常和重试
    """

    def __init__(self):
        self._web_fetch = WebFetchTool()
        self._web_search = WebSearchTool()

    async def plan(self, goal: str, start_url: str | None = None) -> dict[str, Any]:
        """
        规划浏览策略

        Args:
            goal: 用户目标
            start_url: 起始URL

        Returns:
            浏览计划
        """
        # 分析目标复杂度
        complexity = self._analyze_goal_complexity(goal, start_url)

        if complexity == "simple":
            # 简单目标：单次抓取
            return {
                "strategy": "single_fetch",
                "steps": [
                    {"type": "fetch", "url": start_url, "prompt": goal}
                ]
            }

        elif complexity == "search_then_fetch":
            # 搜索+抓取：先搜索再抓取
            search_query = self._extract_search_query(goal)
            return {
                "strategy": "search_then_fetch",
                "steps": [
                    {"type": "search", "query": search_query},
                    {"type": "fetch_results", "goal": goal}
                ]
            }

        else:
            # 复杂目标：多步导航
            return {
                "strategy": "multi_step",
                "steps": self._plan_multi_step(goal, start_url)
            }

    def _analyze_goal_complexity(self, goal: str, start_url: str | None) -> str:
        """分析目标复杂度"""
        complex_indicators = [
            "多个", "所有", "搜索", "查找", "比较",
            "登录", "填写", "提交", "下载", "注册"
        ]
        simple_indicators = [
            "获取", "查看", "阅读", "打开", "访问"
        ]

        has_complex = any(ind in goal for ind in complex_indicators)
        has_simple = any(ind in goal for ind in simple_indicators)

        if has_complex:
            return "multi_step"
        elif has_simple and not start_url:
            return "search_then_fetch"
        else:
            return "simple"

    def _extract_search_query(self, goal: str) -> str:
        """从目标中提取搜索查询"""
        # 简单实现：移除常见动词
        query = goal
        for prefix in ["获取", "查看", "查找", "搜索"]:
            query = query.replace(prefix, "")
        return query.strip()

    def _plan_multi_step(self, goal: str, start_url: str | None) -> list[dict]:
        """规划多步浏览"""
        steps = []

        if not start_url:
            # 需要先搜索
            search_query = self._extract_search_query(goal)
            steps.append({"type": "search", "query": search_query})

        steps.append({"type": "fetch", "url": start_url, "prompt": goal})

        return steps


class WorkerAgent:
    """
    Worker Agent - 执行具体浏览任务

    职责：
    1. 抓取网页内容
    2. 解析页面结构
    3. 提取目标信息
    """

    def __init__(self, worker_id: str = "worker_1"):
        self.worker_id = worker_id
        self._web_fetch = WebFetchTool()

    async def fetch_page(self, url: str, prompt: str = "") -> PageState:
        """抓取页面"""
        try:
            result = await self._web_fetch.fetch(url)

            if "error" in result:
                return PageState(url=url, error=result["error"])

            content = result.get("result", "")

            return PageState(
                url=url,
                title=self._extract_title(content),
                content=content,
                links=self._extract_links(content, url),
                forms=self._extract_forms(content)
            )

        except Exception as e:
            logger.error(f"[{self.worker_id}] Fetch failed: {e}")
            return PageState(url=url, error=str(e))

    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        """执行搜索"""
        try:
            result = await self._web_search.search(query, max_results=max_results)
            if "error" in result:
                return []
            return result.get("results", [])
        except Exception as e:
            logger.error(f"[{self.worker_id}] Search failed: {e}")
            return []

    def _extract_title(self, content: str) -> str:
        """提取页面标题"""
        lines = content.split("\n")
        if lines:
            return lines[0][:100]
        return ""

    def _extract_links(self, content: str, base_url: str) -> list[dict]:
        """提取链接"""
        import re
        links = []
        # 简单的链接提取
        url_pattern = r'https?://[^\s\)"\']+'
        urls = re.findall(url_pattern, content)
        for url in urls[:20]:  # 限制数量
            links.append({"url": url, "text": url[:50]})
        return links

    def _extract_forms(self, content: str) -> list[dict]:
        """提取表单（placeholder实现）"""
        return []


class TeamBrowser:
    """
    团队浏览器 - 多Worker并行工作

    使用 coordinator/team.py 的团队概念：
    - 一个 Coordinator 管理策略
    - 多个 Worker 并行执行
    """

    def __init__(self, team_size: int = 3):
        self.team_size = team_size
        self.coordinator = CoordinatorAgent()
        self.workers = [WorkerAgent(f"worker_{i}") for i in range(team_size)]

    async def browse(self, goal: str, start_url: str | None = None) -> dict[str, Any]:
        """
        执行浏览任务

        Args:
            goal: 浏览目标
            start_url: 起始URL

        Returns:
            浏览结果
        """
        # 1. Coordinator 规划
        plan = await self.coordinator.plan(goal, start_url)
        logger.info(f"TeamBrowser: 计划 strategy={plan['strategy']}")

        # 2. 根据策略执行
        if plan["strategy"] == "single_fetch":
            return await self._single_fetch(plan, goal, start_url)

        elif plan["strategy"] == "search_then_fetch":
            return await self._search_then_fetch(plan, goal)

        elif plan["strategy"] == "multi_step":
            return await self._multi_step(plan)

        return {"error": "Unknown strategy"}

    async def _single_fetch(
        self,
        plan: dict,
        goal: str,
        start_url: str | None
    ) -> dict[str, Any]:
        """单次抓取"""
        if not start_url:
            return {"error": "No start URL provided"}

        worker = self.workers[0]
        page = await worker.fetch_page(start_url, goal)

        return {
            "strategy": "single_fetch",
            "pages": [self._page_to_dict(page)],
            "goal": goal
        }

    async def _search_then_fetch(self, plan: dict, goal: str) -> dict[str, Any]:
        """搜索然后抓取"""
        search_query = plan["steps"][0]["query"]

        # 并行搜索和抓取（使用多个worker）
        search_task = self.workers[0].search(search_query)

        # 等待搜索结果
        search_results = await search_task

        if not search_results:
            return {
                "strategy": "search_then_fetch",
                "error": "No search results",
                "goal": goal
            }

        # 并行抓取前N个结果
        fetch_tasks = [
            self.workers[i % len(self.workers)].fetch_page(r["url"], goal)
            for i, r in enumerate(search_results[:self.team_size])
        ]

        pages = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        valid_pages = [
            self._page_to_dict(p) for p in pages
            if isinstance(p, PageState) and not p.error
        ]

        return {
            "strategy": "search_then_fetch",
            "search_query": search_query,
            "search_results": search_results[:self.team_size],
            "pages": valid_pages,
            "goal": goal
        }

    async def _multi_step(self, plan: dict) -> dict[str, Any]:
        """多步浏览"""
        all_pages = []
        current_goal = ""

        for step in plan["steps"]:
            if step["type"] == "search":
                results = await self.workers[0].search(step["query"])
                all_pages.append({
                    "type": "search_results",
                    "query": step["query"],
                    "results": results
                })

            elif step["type"] == "fetch":
                page = await self.workers[0].fetch_page(step["url"], step.get("prompt", ""))
                all_pages.append(self._page_to_dict(page))

        return {
            "strategy": "multi_step",
            "pages": all_pages,
            "steps_count": len(plan["steps"])
        }

    def _page_to_dict(self, page: PageState) -> dict[str, Any]:
        """转换PageState为字典"""
        return {
            "url": page.url,
            "title": page.title,
            "content": page.content[:2000] if page.content else "",  # 截断
            "links_count": len(page.links),
            "error": page.error
        }


class WebBrowserTool(BaseTool):
    """
    WebBrowserTool - 使用多Agent系统的网页浏览器工具

    功能：
    - 单页面抓取
    - 搜索+抓取组合
    - 多Worker并行抓取
    - 智能策略选择
    """

    name = "WebBrowser"
    description = """使用多Agent协调器系统的网页浏览器工具。

功能：
- 根据目标复杂度自动选择最佳策略
- 支持单页面抓取、多页面并行抓取
- 支持搜索+抓取组合
- 多Worker协作加速抓取

使用方式：
- 提供URL直接抓取
- 提供目标描述，自动决定是否需要搜索"""

    input_schema = {
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "浏览目标，如'获取Python最新文档'或'搜索React状态管理方案'"
            },
            "url": {
                "type": "string",
                "description": "起始URL（可选，不提供则自动搜索）"
            },
            "max_pages": {
                "type": "integer",
                "description": "最大抓取页面数，默认3",
                "default": 3
            }
        },
        "required": ["goal"]
    }

    def __init__(self, team_size: int = 3):
        super().__init__()
        self._team = TeamBrowser(team_size=team_size)

    async def call(self, args: dict, context: dict) -> ToolResult:
        """执行网页浏览"""
        goal = args.get("goal", "")
        url = args.get("url")
        max_pages = args.get("max_pages", 3)

        if not goal:
            return ToolResult(
                success=False,
                data=None,
                error="goal 参数不能为空"
            )

        try:
            result = await self._team.browse(goal, url)

            if "error" in result and not result.get("pages"):
                return ToolResult(success=False, data=result, error=result["error"])

            return ToolResult(success=True, data=result)

        except Exception as e:
            logger.error(f"WebBrowserTool 执行失败: {e}")
            return ToolResult(success=False, data=None, error=str(e))


# 注册工具
def register_browser_tools():
    """注册浏览器工具"""
    try:
        from scripts.tool import get_registry
    except ImportError:
        from tool import get_registry

    get_registry().register(WebBrowserTool())


# 延迟注册
import atexit
atexit.register(register_browser_tools)
