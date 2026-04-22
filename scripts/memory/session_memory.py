"""
会话记忆管理

跟踪当前会话状态，支持会话压缩。
"""
import logging
from datetime import datetime
from typing import Optional

from .memory_store import MemoryStore

logger = logging.getLogger(__name__)


SESSION_TEMPLATE = """# Session Title

# Current State
_What is actively being worked on right now?_

# Task specification
_What did the user ask to build?_

# Files and Functions
_Important files and their purpose_

# Workflow
_Bash commands and their order_

# Errors & Corrections
_Errors encountered and how fixed_

# Learnings
_What worked well? What to avoid?_

# Key results
_The exact output requested_

# Worklog
_Step by step summary_
"""


class SessionMemory:
    """会话记忆管理"""

    def __init__(
        self,
        session_id: str | None = None,
        store: MemoryStore | None = None,
    ):
        self._session_id = session_id or self._generate_session_id()
        self._store = store or MemoryStore()
        self._current_state: str | None = None
        self._task_spec: str | None = None
        self._files: list[str] = []
        self._workflow: list[str] = []
        self._errors: list[tuple[str, str]] = []
        self._learnings: list[str] = []
        self._worklog: list[str] = []
        self._last_updated = datetime.now()

    @staticmethod
    def _generate_session_id() -> str:
        """生成会话 ID"""
        return datetime.now().strftime("%Y%m%d-%H%M%S")

    @property
    def session_id(self) -> str:
        """获取会话 ID"""
        return self._session_id

    def update_current_state(self, state: str) -> None:
        """更新当前状态"""
        self._current_state = state
        self._mark_updated()

    def update_task_spec(self, spec: str) -> None:
        """更新任务规格"""
        self._task_spec = spec
        self._mark_updated()

    def add_file(self, file_path: str, description: str = "") -> None:
        """添加文件信息"""
        entry = f"- {file_path}"
        if description:
            entry += f": {description}"
        if entry not in self._files:
            self._files.append(entry)
        self._mark_updated()

    def add_workflow_step(self, command: str) -> None:
        """添加工作流步骤"""
        self._workflow.append(f"- {command}")
        self._mark_updated()

    def add_error(self, error: str, solution: str) -> None:
        """添加错误记录"""
        self._errors.append((error, solution))
        self._mark_updated()

    def add_learning(self, learning: str) -> None:
        """添加学习记录"""
        if learning not in self._learnings:
            self._learnings.append(learning)
        self._mark_updated()

    def add_worklog_entry(self, entry: str) -> None:
        """添加工作日志条目"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._worklog.append(f"- [{timestamp}] {entry}")
        self._mark_updated()

    def _mark_updated(self) -> None:
        """标记更新时间"""
        self._last_updated = datetime.now()

    def to_template(self) -> str:
        """生成填充后的模板"""
        lines = [
            f"# Session {self._session_id}",
            "",
            "# Current State",
            self._current_state or "_No current state_",
            "",
            "# Task specification",
            self._task_spec or "_No task specified_",
            "",
            "# Files and Functions",
            '\n'.join(self._files) if self._files else "_No files recorded_",
            "",
            "# Workflow",
            '\n'.join(self._workflow) if self._workflow else "_No workflow recorded_",
            "",
            "# Errors & Corrections",
        ]

        if self._errors:
            for error, solution in self._errors:
                lines.append(f"- **Error**: {error}")
                lines.append(f"  - **Solution**: {solution}")
        else:
            lines.append("_No errors recorded_")

        lines.extend([
            "",
            "# Learnings",
            '\n'.join(f"- {l}" for l in self._learnings) if self._learnings else "_No learnings recorded_",
            "",
            "# Worklog",
            '\n'.join(self._worklog) if self._worklog else "_No worklog entries_",
        ])

        return '\n'.join(lines)

    def save(self) -> None:
        """保存会话记忆"""
        content = self.to_template()
        self._store.write_session_memory(self._session_id, content)
        logger.info(f"Saved session memory: {self._session_id}")

    @classmethod
    def load(cls, session_id: str, store: MemoryStore | None = None) -> Optional["SessionMemory"]:
        """加载会话记忆"""
        store = store or MemoryStore()
        content = store.read_session_memory(session_id)

        if not content:
            return None

        memory = cls(session_id=session_id, store=store)

        lines = content.split('\n')
        current_section = None
        section_content = []

        for line in lines:
            if line.startswith('# '):
                if current_section and section_content:
                    memory._parse_section(current_section, '\n'.join(section_content))

                current_section = line[2:].strip()
                section_content = []
            else:
                section_content.append(line)

        if current_section and section_content:
            memory._parse_section(current_section, '\n'.join(section_content))

        return memory

    def _parse_section(self, section_title: str, content: str) -> None:
        """解析并填充各个部分"""
        section_lower = section_title.lower()
        # content 已经是该 section 的全部内容，不再需要跳过标题行
        lines = [l for l in content.split('\n') if l.strip()]

        if 'current state' in section_lower:
            # 内容直接使用，不跳过第一行
            self._current_state = content.strip() if content.strip() else None
        elif 'task spec' in section_lower:
            self._task_spec = content.strip() if content.strip() else None
        elif 'files' in section_lower:
            self._files = lines
        elif 'workflow' in section_lower:
            self._workflow = lines
        elif 'learnings' in section_lower:
            self._learnings = [l.lstrip('- ') for l in lines]
        elif 'worklog' in section_lower:
            self._worklog = lines

    def get_summary(self) -> str:
        """获取会话摘要"""
        return f"""Session {self._session_id}
Last updated: {self._last_updated.isoformat()}
State: {self._current_state or 'N/A'}
Task: {self._task_spec or 'N/A'}
Files: {len(self._files)}
Steps: {len(self._workflow)}
Errors: {len(self._errors)}
Learnings: {len(self._learnings)}"""

    def to_dict(self) -> dict:
        """获取会话详细信息（用于 API 返回）"""
        return {
            "session_id": self._session_id,
            "last_updated": self._last_updated.isoformat(),
            "current_state": self._current_state or "",
            "task_spec": self._task_spec or "",
            "files": self._files,
            "workflow": self._workflow,
            "errors": [{"error": e, "solution": s} for e, s in self._errors],
            "learnings": self._learnings,
            "worklog": self._worklog,
        }

    @classmethod
    def load_from_store(cls, session_id: str, store: "MemoryStore | None" = None) -> Optional["SessionMemory"]:
        """从 MemoryStore 加载会话记忆"""
        if store is None:
            from .memory_store import MemoryStore
            store = MemoryStore()
        content = store.read_session_memory(session_id)
        if not content:
            return None

        memory = cls(session_id=session_id, store=store)

        lines = content.split('\n')
        current_section = None
        section_content = []

        for line in lines:
            if line.startswith('# '):
                if current_section and section_content:
                    memory._parse_section(current_section, '\n'.join(section_content))

                current_section = line[2:].strip()
                section_content = []
            else:
                section_content.append(line)

        if current_section and section_content:
            memory._parse_section(current_section, '\n'.join(section_content))

        return memory
