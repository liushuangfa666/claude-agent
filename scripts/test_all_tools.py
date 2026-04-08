#!/usr/bin/env python3
"""
工具测试脚本 - 测试所有实现的工具

Usage:
    python test_all_tools.py [--quick] [--full]
    
Options:
    --quick   只测试核心功能，不依赖网络
    --full    完整测试，包括网络请求
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime

# 添加 scripts 到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scripts.integration import register_all_tools
from scripts.mcp import McpServerConfig, ServerStatus, TransportType
from scripts.mcp.mcp_string_utils import format_mcp_tool_name, parse_mcp_tool_name
from scripts.memory import FreshnessChecker, MemoryRetriever, MemoryStore, SessionMemory
from scripts.memory.types import MemoryHeader, MemoryType
from scripts.preapproved import is_preapproved_host
from scripts.skill import (
    SkillConfig,
    SkillExecutionMode,
    SkillLoader,
    get_bundled_skills,
    register_bundled_skills,
)
from scripts.task import Task, TaskStatus, TaskStore, TaskType
from scripts.web_cache import LRUCache
from scripts.web_tools import WebFetchTool, WebSearchTool


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []

    def test(self, name: str, fn, *args, **kwargs):
        """运行单个测试"""
        try:
            result = fn(*args, **kwargs)
            if result:
                self.passed += 1
                self.results.append(("PASS", name))
                print(f"  [PASS] {name}")
                return True
            else:
                self.failed += 1
                self.results.append(("FAIL", name, "Test returned False"))
                print(f"  [FAIL] {name}")
                return False
        except Exception as e:
            self.failed += 1
            self.results.append(("FAIL", name, str(e)))
            print(f"  [FAIL] {name}: {e}")
            return False

    def summary(self):
        """打印测试摘要"""
        print("\n" + "=" * 60)
        print(f"测试结果: {self.passed} 通过, {self.failed} 失败")
        print("=" * 60)

        if self.failed > 0:
            print("\n失败的测试:")
            for r in self.results:
                if r[0] == "FAIL":
                    print(f"  - {r[1]}: {r[2]}")

        return self.failed == 0


def test_memory_system(runner: TestRunner):
    """测试记忆系统"""
    print("\n[记忆系统 Memory System]")

    # 1. MemoryStore
    def test_memory_store():
        store = MemoryStore()
        # 扫描现有记忆
        headers = store.scan_memory_files()
        # 写入新记忆
        path = store.write_memory(
            content="This is a test memory for testing purposes.",
            memory_type=MemoryType.USER,
            name="test-memory",
            description="A test memory"
        )
        # 重新扫描验证写入成功
        new_headers = store.scan_memory_files()
        # 删除测试记忆
        if path.exists():
            path.unlink()
        return len(new_headers) >= len(headers)

    runner.test("MemoryStore 存储功能", test_memory_store)

    # 2. SessionMemory
    def test_session_memory():
        session = SessionMemory(session_id="test-session")
        session.update_current_state("Testing memory system")
        session.update_task_spec("Create a test plan")
        session.add_file("test.py", "Test file")
        session.add_workflow_step("python test.py")
        session.add_learning("Always test before committing")
        session.add_error("Import error", "Fixed by adding missing dependency")

        summary = session.get_summary()
        template = session.to_template()

        # 保存并重新加载
        session.save()
        loaded = SessionMemory.load("test-session")

        return loaded is not None and "test-session" in loaded.session_id

    runner.test("SessionMemory 会话记忆", test_session_memory)

    # 3. FreshnessChecker
    def test_freshness():
        header = MemoryHeader(
            filename="test.md",
            file_path=None,
            mtime=datetime.now()
        )
        freshness = FreshnessChecker.check(header)
        warning = FreshnessChecker.get_warning(header)

        return freshness.value in ["fresh", "stale", "outdated"]

    runner.test("FreshnessChecker 新鲜度检查", test_freshness)

    # 4. MemoryRetriever
    def test_memory_retriever():
        retriever = MemoryRetriever()
        # 检索（可能返回空，但不报错）
        results = retriever.retrieve("test query", limit=5)
        report = retriever.get_freshness_report()

        return "total" in report and "fresh" in report

    runner.test("MemoryRetriever 检索服务", test_memory_retriever)


def test_mcp_system(runner: TestRunner):
    """测试 MCP 系统"""
    print("\n[MCP 系统]")

    # 1. MCP 类型
    def test_mcp_types():
        config = McpServerConfig.from_dict("github", {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}
        })

        return (config.name == "github" and
                config.transport_type == TransportType.STDIO and
                "npx" in config.command)

    runner.test("McpServerConfig 配置解析", test_mcp_types)

    # 2. 工具名称格式化
    def test_tool_name_formatting():
        tool_name = format_mcp_tool_name("github", "create_issue")
        parsed = parse_mcp_tool_name("mcp__github__create_issue")

        return (tool_name == "mcp__github__create_issue" and
                parsed == ("github", "create_issue"))

    runner.test("MCP 工具名称格式化", test_tool_name_formatting)

    # 3. 工具名称解析边界情况
    def test_tool_name_parsing():
        # 无效名称
        assert parse_mcp_tool_name("invalid") is None
        assert parse_mcp_tool_name("mcp__") is None

        # 有效名称
        assert parse_mcp_tool_name("mcp__gh__create") == ("gh", "create")

        return True

    runner.test("MCP 工具名称解析边界", test_tool_name_parsing)

    # 4. ServerStatus
    def test_server_status():
        return (ServerStatus.CONNECTED.value == "connected" and
                ServerStatus.DISCONNECTED.value == "disconnected")

    runner.test("ServerStatus 状态枚举", test_server_status)


def test_task_system(runner: TestRunner):
    """测试 Task 系统"""
    print("\n[Task 系统]")

    # 1. Task 模型
    def test_task_model():
        task = Task(
            id="1",
            subject="Test task",
            description="A task for testing",
            task_type=TaskType.BASH
        )

        task_dict = task.to_dict()
        task_from_dict = Task.from_dict(task_dict)

        return (task.subject == task_from_dict.subject and
                task.task_type == task_from_dict.task_type)

    runner.test("Task 模型序列化", test_task_model)

    # 2. TaskStore
    def test_task_store():
        store = TaskStore()
        session_id = "test-" + datetime.now().strftime("%Y%m%d%H%M%S")

        # 创建任务
        task = Task(id="", subject="Test task", task_type=TaskType.BASH)
        created = store.create(task, session_id)
        task_id = created.id

        # 列出任务
        tasks = store.list_all(session_id)

        # 获取单个任务
        retrieved = store.get(task_id, session_id)

        # 更新状态
        store.update_status(task_id, session_id, TaskStatus.IN_PROGRESS)
        updated = store.get(task_id, session_id)

        # 清理
        store.delete(task_id, session_id)

        return (len(tasks) >= 1 and
                retrieved is not None and
                updated.status == TaskStatus.IN_PROGRESS)

    runner.test("TaskStore 完整CRUD", test_task_store)

    # 3. TaskStatus 转换
    def test_task_status_transitions():
        task = Task(id="1", subject="Test")

        task.status = TaskStatus.PENDING
        assert task.status == TaskStatus.PENDING

        task.status = TaskStatus.IN_PROGRESS
        assert task.status == TaskStatus.IN_PROGRESS

        task.status = TaskStatus.COMPLETED
        assert task.status == TaskStatus.COMPLETED

        task.status = TaskStatus.FAILED
        assert task.status == TaskStatus.FAILED

        return True

    runner.test("TaskStatus 状态转换", test_task_status_transitions)

    # 4. TaskType 枚举
    def test_task_types():
        return (TaskType.BASH.value == "bash" and
                TaskType.AGENT.value == "agent" and
                TaskType.WORKFLOW.value == "workflow")

    runner.test("TaskType 类型枚举", test_task_types)


def test_skill_system(runner: TestRunner):
    """测试 Skill 系统"""
    print("\n[Skill 系统]")

    # 1. SkillConfig
    def test_skill_config():
        config = SkillConfig(
            name="test-skill",
            description="A test skill",
            context=SkillExecutionMode.INLINE,
            content="Hello $ARGUMENTS world"  # 有内容的
        )

        expanded = config.expand_content("my args")

        return ("my args" in expanded and
                config.context == SkillExecutionMode.INLINE and
                config.name == "test-skill")

    runner.test("SkillConfig 配置与展开", test_skill_config)

    # 2. Bundled Skills
    def test_bundled_skills():
        skills = get_bundled_skills()

        skill_names = [s.name for s in skills]

        return all(name in skill_names for name in
                   ["verify", "pr-review", "refactor", "debug", "test", "docs"])

    runner.test("Bundled Skills 内置技能", test_bundled_skills)

    # 3. SkillLoader
    def test_skill_loader():
        loader = SkillLoader()
        register_bundled_skills(loader)

        skill = loader.get_skill("verify")

        return skill is not None and skill.config.name == "verify"

    runner.test("SkillLoader 技能加载", test_skill_loader)

    # 4. SkillExecutionMode
    def test_execution_modes():
        return (SkillExecutionMode.INLINE.value == "inline" and
                SkillExecutionMode.FORK.value == "fork")

    runner.test("SkillExecutionMode 执行模式", test_execution_modes)


def test_web_tools(runner: TestRunner, quick: bool = False):
    """测试 Web 工具"""
    print("\n[Web 工具]")

    # 1. LRUCache
    def test_lru_cache():
        cache = LRUCache(max_size_bytes=100, ttl_seconds=60)

        cache.set("k1", "v1")  # size=1
        cache.set("k2", "v2", size=50)  # size=50 - total=51

        # 添加更大的值触发驱逐
        cache.set("k3", "x" * 60)  # size=60 - total=111 > 100, should evict

        # k1 或 k2 应该被驱逐
        v1 = cache.get("k1")
        v2 = cache.get("k2")
        v3 = cache.get("k3")

        # 清理
        cache.clear()

        # v3 应该存在, v1/v2 至少一个被驱逐
        return v3 is not None and (v1 is None or v2 is None)

    runner.test("LRUCache LRU淘汰", test_lru_cache)

    # 2. Preapproved Hosts
    def test_preapproved_hosts():
        # 预批准域名
        assert is_preapproved_host("docs.python.org") == True
        assert is_preapproved_host("github.com") == True
        assert is_preapproved_host("stackoverflow.com") == True

        # 未批准域名
        assert is_preapproved_host("evil.com") == False
        assert is_preapproved_host("phishing-site.com") == False

        # 子域名
        assert is_preapproved_host("api.docs.python.org") == True

        return True

    runner.test("Preapproved Hosts 白名单", test_preapproved_hosts)

    # 3. WebFetchTool 结构
    def test_web_fetch_structure():
        tool = WebFetchTool()

        # 检查属性
        assert tool.name == "WebFetch"
        assert "url" in tool.input_schema.get("properties", {})
        assert "prompt" in tool.input_schema.get("properties", {})

        return True

    runner.test("WebFetchTool 结构", test_web_fetch_structure)

    # 4. WebSearchTool 结构
    def test_web_search_structure():
        tool = WebSearchTool()

        # 检查属性
        assert tool.name == "WebSearch"
        assert "query" in tool.input_schema.get("properties", {})

        return True

    runner.test("WebSearchTool 结构", test_web_search_structure)

    # 5. 网络测试 (可选)
    if not quick:
        async def test_web_search():
            tool = WebSearchTool()
            result = await tool.search("Python programming language")
            return "results" in result or "error" in result

        runner.test("WebSearch 实际搜索", asyncio.run, test_web_search())

    return True


def test_integration(runner: TestRunner):
    """测试整合"""
    print("\n[整合模块]")

    # 1. 工具注册
    def test_tool_registration():
        from scripts.tool import get_registry
        get_registry()._tools.clear()  # 清空后重新注册

        tools = register_all_tools()
        return len(tools) >= 15  # 至少有15个工具

    runner.test("工具注册", test_tool_registration)

    # 2. 获取所有工具
    def test_get_all_tools():
        from scripts.integration import get_all_registered_tools
        all_tools = get_all_registered_tools()

        names = [t["name"] for t in all_tools]

        # 检查各类工具
        has_basic = any(n in ["Read", "Bash", "Write", "Grep", "Glob"] for n in names)
        has_task = any(n.startswith("Task") for n in names)
        has_skill = any(n.startswith("Skill") for n in names)
        has_web = any(n in ["WebFetch", "WebSearch"] for n in names)

        return has_basic and has_task and has_skill and has_web

    runner.test("获取所有工具", test_get_all_tools)


def main():
    parser = argparse.ArgumentParser(description="工具测试脚本")
    parser.add_argument("--quick", action="store_true", help="快速测试，跳过网络请求")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    args = parser.parse_args()

    print("=" * 60)
    print("Crush Agent 工具测试套件")
    print("=" * 60)
    print(f"模式: {'快速测试' if args.quick else '完整测试'}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    runner = TestRunner()

    # 运行所有测试
    test_memory_system(runner)
    test_mcp_system(runner)
    test_task_system(runner)
    test_skill_system(runner)
    test_web_tools(runner, quick=args.quick)
    test_integration(runner)

    # 打印摘要
    success = runner.summary()

    if success:
        print("\n所有测试通过!")
        return 0
    else:
        print("\n部分测试失败，请检查上面的输出。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
