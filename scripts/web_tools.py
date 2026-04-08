"""
Web 工具

提供 WebFetchTool 和 WebSearchTool。
"""
import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from .preapproved import is_preapproved_host
from .web_cache import LRUCache

logger = logging.getLogger(__name__)


try:
    from .tool import BaseTool, ToolResult
except ImportError:
    from scripts.tool import BaseTool, ToolResult


class WebFetchTool(BaseTool):
    """Web 页面抓取工具"""

    name = "WebFetch"
    description = "抓取网页内容并转换为 Markdown"

    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "要抓取的 URL"},
            "prompt": {"type": "string", "description": "对页面内容的问题"},
        },
        "required": ["url", "prompt"],
    }

    def __init__(self, cache: LRUCache | None = None):
        super().__init__()
        self._cache = cache or LRUCache(max_size_bytes=50 * 1024 * 1024, ttl_seconds=900)

    async def call(self, args: dict, context: dict) -> ToolResult:
        """Execute web fetch"""
        url = args.get("url", "")
        prompt = args.get("prompt", "")

        result = await self.fetch(url)

        if "error" in result:
            return ToolResult(success=False, data=None, error=result["error"])

        return ToolResult(success=True, data=result)

    async def fetch(self, url: str, timeout: int = 30) -> dict[str, Any]:
        """
        抓取网页内容
        
        Returns:
            {
                "bytes": int,
                "code": int,
                "codeText": str,
                "result": str (markdown),
                "durationMs": int,
                "url": str
            }
        """
        start_time = time.time()

        url = url.strip()

        if len(url) > 2000:
            return {"error": "URL too long (max 2000 characters)"}

        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return {"error": "Only http/https protocols allowed"}

        if not is_preapproved_host(parsed.netloc):
            return {"error": f"Domain {parsed.netloc} not in whitelist"}

        cached = self._cache.get(url)
        if cached:
            logger.info(f"WebFetch: Cache hit for {url}")
            return cached

        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    allow_redirects=True,
                ) as response:
                    content = await response.read()
                    content_type = response.headers.get("Content-Type", "")

                    redirect_count = 0
                    final_url = str(response.url)

                    while str(response.url) != url and redirect_count < 10:
                        url = str(response.url)
                        redirect_count += 1

                    if redirect_count >= 10:
                        return {"error": "Too many redirects"}

                    if "text/html" in content_type:
                        result = self._html_to_markdown(content.decode("utf-8", errors="replace"))
                    elif "text/plain" in content_type:
                        result = content.decode("utf-8", errors="replace")
                    else:
                        result = f"[Binary content: {content_type}]"

                    result_dict = {
                        "bytes": len(content),
                        "code": response.status,
                        "codeText": response.reason,
                        "result": result,
                        "durationMs": int((time.time() - start_time) * 1000),
                        "url": final_url,
                    }

                    if len(content) < 10 * 1024 * 1024:
                        self._cache.set(url, result_dict)

                    return result_dict

        except asyncio.TimeoutError:
            return {"error": f"Request timed out after {timeout}s"}
        except Exception as e:
            logger.error(f"WebFetch error: {e}")
            return {"error": str(e)}

    def _html_to_markdown(self, html: str) -> str:
        """将 HTML 转换为 Markdown"""
        try:
            from markdownify import markdownify
            return markdownify(html)
        except ImportError:
            import re
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<[^>]+>', '', html)
            html = re.sub(r'\n\s*\n', '\n\n', html)
            return html.strip()


class WebSearchTool(BaseTool):
    """Web 搜索工具"""

    name = "WebSearch"
    description = "使用 DuckDuckGo 搜索网页"

    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "allowed_domains": {"type": "array", "items": {"type": "string"}, "description": "允许的域名"},
            "blocked_domains": {"type": "array", "items": {"type": "string"}, "description": "禁止的域名"},
        },
        "required": ["query"],
    }

    def __init__(self):
        super().__init__()

    async def call(self, args: dict, context: dict) -> ToolResult:
        """Execute web search"""
        query = args.get("query", "")
        allowed = args.get("allowed_domains")
        blocked = args.get("blocked_domains")

        result = await self.search(query, allowed_domains=allowed, blocked_domains=blocked)

        if "error" in result:
            return ToolResult(success=False, data=None, error=result["error"])

        return ToolResult(success=True, data=result)

    async def search(
        self,
        query: str,
        max_results: int = 10,
        allowed_domains: list[str] | None = None,
        blocked_domains: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        执行 Web 搜索，使用 Tavily API
        
        Returns:
            {
                "query": str,
                "results": [{"title": str, "url": str}],
                "durationSeconds": float
            }
        """
        start_time = time.time()

        tavily_key = os.environ.get("TAVILY_API_KEY")
        if not tavily_key:
            return {"error": "TAVILY_API_KEY environment variable not set"}

        url = "https://api.tavily.com/search"
        data = {
            "api_key": tavily_key,
            "query": query,
            "max_results": max_results,
            "include_answer": True,
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            results = []
            for r in result.get("results", [])[:max_results]:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                })

            answer = result.get("answer", "")
            duration = time.time() - start_time

            return {
                "query": query,
                "results": results,
                "answer": answer,
                "durationSeconds": round(duration, 2),
            }

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            return {"error": f"HTTP {e.code}: {body[:200]}"}
        except Exception as e:
            logger.error(f"WebSearch error: {e}")
            return {"error": str(e)}
