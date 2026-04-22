"""
系统整合模块

将所有模块整合到 Agent 系统中。
"""
import logging

from .tool import get_registry

logger = logging.getLogger(__name__)


def register_all_tools() -> list[str]:
    """
    注册所有内置工具到工具注册表
    
    Returns:
        注册的工具名称列表
    """
    registered = []

    # 注册基础工具 (Read, Bash, Write, Grep, Glob)
    try:
        from . import tools
        from .tool import get_registry

        # 调用 tools 模块的 register_base_tools 来注册基础工具
        tools.register_base_tools()

        # 获取已注册的基础工具
        basic_tools = ['Read', 'Bash', 'Write', 'Grep', 'Glob']
        for name in basic_tools:
            tool = get_registry().get(name)
            if tool:
                registered.append(tool.name)

        logger.info(f"Registered {len([t for t in registered if t in basic_tools])} basic tools")
    except ImportError as e:
        logger.warning(f"Could not import tools: {e}")

    # 注册 Task 工具
    try:
        from .task import (
            TaskCreateTool,
            TaskGetTool,
            TaskListTool,
            TaskOutputTool,
            TaskStopTool,
            TaskUpdateTool,
        )

        task_tools = [
            TaskCreateTool(),
            TaskGetTool(),
            TaskListTool(),
            TaskUpdateTool(),
            TaskStopTool(),
            TaskOutputTool(),
        ]

        for tool in task_tools:
            get_registry().register(tool)
            registered.append(tool.name)

        logger.info(f"Registered {len(task_tools)} task tools")
    except ImportError as e:
        logger.warning(f"Could not import task tools: {e}")

    # 注册 Skill 工具
    try:
        from .skill import (
            SkillInfoTool,
            SkillListTool,
            SkillLoader,
            SkillTool,
            register_bundled_skills,
        )

        loader = SkillLoader()
        register_bundled_skills(loader)
        loader.discover_skills()

        skill_tools = [
            SkillTool(loader),
            SkillListTool(loader),
            SkillInfoTool(loader),
        ]

        for tool in skill_tools:
            get_registry().register(tool)
            registered.append(tool.name)

        logger.info(f"Registered {len(skill_tools)} skill tools")
    except ImportError as e:
        logger.warning(f"Could not import skill tools: {e}")

    # 注册 Web 工具
    try:
        from .web_tools import WebFetchTool, WebSearchTool

        web_fetch = WebFetchTool()
        web_search = WebSearchTool()

        get_registry().register(web_fetch)
        get_registry().register(web_search)

        registered.extend([web_fetch.name, web_search.name])
        logger.info("Registered WebFetch and WebSearch tools")
    except ImportError as e:
        logger.warning(f"Could not import web tools: {e}")

    return registered


def setup_memory_system(session_id: str | None = None):
    """
    设置记忆系统
    
    Args:
        session_id: 会话 ID
    """
    try:
        from .memory import MemoryRetriever, SessionMemory

        session = SessionMemory(session_id=session_id)
        retriever = MemoryRetriever()

        logger.info("Memory system initialized")

        return session, retriever
    except ImportError as e:
        logger.warning(f"Could not initialize memory system: {e}")
        return None, None


async def register_mcp_tools(manager: "MCPServerManager | None" = None) -> list[str]:
    """
    注册 MCP 服务器提供的工具到工具注册表
    
    Args:
        manager: MCP 服务器管理器，如果为 None 则使用全局管理器
    
    Returns:
        注册的工具名称列表
    """
    registered = []
    
    try:
        from .mcp import MCPToolExecutor, get_server_manager
        
        if manager is None:
            manager = get_server_manager()
        
        executor = MCPToolExecutor(manager)
        tools = executor.register_all_tools()
        
        for tool in tools:
            registered.append(tool.name)
        
        logger.info(f"Registered {len(tools)} MCP tools")
        
        return registered
    except ImportError as e:
        logger.warning(f"Could not register MCP tools: {e}")
        return []


async def initialize_mcp_servers(config_path: str | None = None):
    """
    初始化 MCP 服务器并注册其工具
    
    Args:
        config_path: MCP 配置文件路径
    
    Returns:
        (manager, registered_tool_names) 元组
    """
    manager = await _initialize_mcp_manager(config_path)
    if manager is None:
        return None, []
    
    registered = await register_mcp_tools(manager)
    return manager, registered


async def _initialize_mcp_manager(config_path: str | None = None):
    """
    初始化 MCP 服务器管理器（内部函数）
    
    Args:
        config_path: MCP 配置文件路径
    """
    try:
        from .mcp import MCPServerManager, initialize_mcp

        manager = await initialize_mcp(config_path)

        logger.info(f"MCP servers initialized: {len(manager.get_all_servers())} servers")

        return manager
    except ImportError as e:
        logger.warning(f"Could not initialize MCP servers: {e}")
        return None


async def shutdown_mcp_servers():
    """关闭 MCP 服务器"""
    try:
        from .mcp import shutdown_mcp

        await shutdown_mcp()
        logger.info("MCP servers shut down")
    except ImportError as e:
        logger.warning(f"Could not shutdown MCP servers: {e}")


def get_all_registered_tools() -> list[dict]:
    """
    获取所有已注册工具的详细信息
    
    Returns:
        工具定义列表
    """
    registry = get_registry()
    tools = []

    for tool_def in registry.all():
        tools.append({
            "name": tool_def.name,
            "description": tool_def.description,
            "input_schema": tool_def.input_schema,
        })

    return tools
