"""
记忆存储服务

负责记忆文件的读写和 MEMORY.md 索引维护。
"""
import re
from datetime import datetime
from pathlib import Path

from .types import FrontmatterMetadata, MemoryHeader, MemoryIndex, MemoryType


class MemoryStore:
    """记忆存储服务"""

    MEMORY_DIR = Path.home() / ".crush" / "memory"
    SESSION_MEMORY_DIR = Path.home() / ".crush" / "session-memory"
    MEMORY_INDEX_FILE = MEMORY_DIR / "MEMORY.md"

    def __init__(self):
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """确保必要的目录存在"""
        self.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self.SESSION_MEMORY_DIR.mkdir(parents=True, exist_ok=True)

        # 创建子目录
        for subdir in ["user", "feedback", "project", "reference", "logs"]:
            (self.MEMORY_DIR / subdir).mkdir(exist_ok=True)

    def _parse_frontmatter(self, content: str) -> tuple[FrontmatterMetadata | None, str]:
        """解析 frontmatter 和正文"""
        lines = content.split('\n')

        if not lines or lines[0].strip() != '---':
            return None, content

        end_idx = None
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == '---':
                end_idx = i
                break

        if end_idx is None:
            return None, content

        frontmatter_text = '\n'.join(lines[1:end_idx])
        body = '\n'.join(lines[end_idx + 1:])

        metadata = FrontmatterMetadata.parse(frontmatter_text)
        return metadata, body.strip()

    def _detect_memory_type(self, file_path: Path) -> MemoryType | None:
        """根据文件路径检测记忆类型"""
        rel_path = file_path.relative_to(self.MEMORY_DIR)
        parts = rel_path.parts

        if len(parts) >= 2 and parts[0] != "memory":
            try:
                return MemoryType(parts[0])
            except ValueError:
                pass

        return None

    def scan_memory_files(self) -> list[MemoryHeader]:
        """扫描所有记忆文件"""
        headers = []

        if not self.MEMORY_DIR.exists():
            return headers

        for md_file in self.MEMORY_DIR.rglob("*.md"):
            if md_file.name == "MEMORY.md":
                continue

            try:
                stat = md_file.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime)

                metadata, _ = self._read_file_content(md_file)

                header = MemoryHeader(
                    filename=md_file.name,
                    file_path=md_file,
                    mtime=mtime,
                    description=metadata.description if metadata else None,
                    memory_type=metadata.type if metadata else self._detect_memory_type(md_file),
                    name=metadata.name if metadata else None,
                    created=datetime.fromisoformat(metadata.created) if metadata and metadata.created else None,
                )
                headers.append(header)
            except Exception:
                continue

        headers.sort(key=lambda h: h.mtime, reverse=True)
        return headers

    def _read_file_content(self, file_path: Path) -> tuple[FrontmatterMetadata | None, str]:
        """读取文件内容并解析 frontmatter"""
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
            return self._parse_frontmatter(content)
        except Exception:
            return None, ""

    def read_memory(self, header: MemoryHeader) -> tuple[FrontmatterMetadata | None, str]:
        """读取记忆内容"""
        return self._read_file_content(header.file_path)

    def write_memory(
        self,
        content: str,
        memory_type: MemoryType | None = None,
        name: str | None = None,
        description: str | None = None,
        subdir: str | None = None,
    ) -> Path:
        """写入记忆文件"""
        return self._write_memory_file(
            content=content,
            memory_type=memory_type,
            name=name,
            description=description,
            subdir=subdir,
        )

    def _write_memory_file(
        self,
        content: str,
        memory_type: MemoryType | None = None,
        name: str | None = None,
        description: str | None = None,
        subdir: str | None = None,
    ) -> Path:
        metadata = FrontmatterMetadata(
            name=name,
            description=description,
            type=memory_type.value if memory_type else None,
            created=datetime.now().isoformat(),
            updated=datetime.now().isoformat(),
        )

        if subdir:
            dir_path = self.MEMORY_DIR / subdir
        elif memory_type:
            dir_path = self.MEMORY_DIR / memory_type.value
        else:
            dir_path = self.MEMORY_DIR / "user"

        dir_path.mkdir(parents=True, exist_ok=True)

        # 生成文件名
        if name:
            filename = re.sub(r'[^\w\s-]', '', name.lower())
            filename = re.sub(r'[\s]+', '-', filename)
        else:
            filename = datetime.now().strftime("%Y%m%d-%H%M%S")

        file_path = dir_path / f"{filename}.md"

        # 避免文件覆盖
        counter = 1
        while file_path.exists():
            file_path = dir_path / f"{filename}-{counter}.md"
            counter += 1

        # 写入文件
        full_content = f"{metadata.to_frontmatter()}\n\n{content}"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        self._update_index()

        return file_path

    def update_memory(self, header: MemoryHeader, content: str, **kwargs) -> None:
        """更新记忆文件"""
        old_metadata, _ = self._read_file_content(header.file_path)

        metadata = FrontmatterMetadata(
            name=kwargs.get("name", old_metadata.name if old_metadata else None),
            description=kwargs.get("description", old_metadata.description if old_metadata else None),
            type=kwargs.get("type", old_metadata.type if old_metadata else None),
            created=old_metadata.created if old_metadata else datetime.now().isoformat(),
            updated=datetime.now().isoformat(),
            tags=kwargs.get("tags", old_metadata.tags if old_metadata else []),
        )

        full_content = f"{metadata.to_frontmatter()}\n\n{content}"
        with open(header.file_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        self._update_index()

    def delete_memory(self, header: MemoryHeader) -> None:
        """删除记忆文件"""
        if header.file_path.exists():
            header.file_path.unlink()
        self._update_index()

    def get_memory(self, memory_id: str) -> tuple[FrontmatterMetadata | None, str]:
        """通过 memory_id 获取记忆内容（memory_id 实为文件名）"""
        if not self.MEMORY_DIR.exists():
            return None, ""

        for md_file in self.MEMORY_DIR.rglob("*.md"):
            if md_file.name == "MEMORY.md":
                continue
            if md_file.stem == memory_id or md_file.name == f"{memory_id}.md":
                return self._read_file_content(md_file)

        # 尝试完整路径
        path = Path(memory_id)
        if path.exists() and path.suffix == ".md":
            return self._read_file_content(path)

        return None, ""

    def list_memories(
        self,
        memory_type: MemoryType | None = None,
        limit: int = 100,
    ) -> list[MemoryHeader]:
        """列出记忆文件"""
        headers = self.scan_memory_files()

        if memory_type:
            type_val = memory_type.value if isinstance(memory_type, MemoryType) else memory_type
            headers = [h for h in headers if _get_memory_type_value(h.memory_type) == type_val]

        return headers[:limit]

    def delete_memory(self, header: MemoryHeader) -> None:
        """删除记忆文件（通过 header）"""
        if header.file_path.exists():
            header.file_path.unlink()
        self._update_index()

    def delete_memory_by_id(self, memory_id: str) -> bool:
        """删除记忆文件（通过 memory_id）"""
        for md_file in self.MEMORY_DIR.rglob("*.md"):
            if md_file.name == "MEMORY.md":
                continue
            if md_file.stem == memory_id or md_file.name == f"{memory_id}.md":
                md_file.unlink()
                self._update_index()
                return True
        return False

    def search_memories(self, query: str, limit: int = 10) -> list[MemoryHeader]:
        """简单关键词搜索记忆"""
        headers = self.scan_memory_files()
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []
        for header in headers:
            score = 0

            if header.name and query_lower in header.name.lower():
                score += 5
            if header.description and query_lower in header.description.lower():
                score += 3
            if header.name:
                words = set(header.name.lower().split())
                score += len(query_words & words)
            if header.description:
                words = set(header.description.lower().split())
                score += len(query_words & words)

            if score > 0:
                scored.append((score, header))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [h for _, h in scored[:limit]]

    def update_index(self) -> None:
        """更新 MEMORY.md 索引"""
        headers = self.scan_memory_files()
        index = MemoryIndex(memories=headers, last_updated=datetime.now())

        with open(self.MEMORY_INDEX_FILE, "w", encoding="utf-8") as f:
            f.write(index.to_markdown())

    def _update_index(self) -> None:
        """内部方法：更新 MEMORY.md 索引（兼容旧调用）"""
        self.update_index()

    def get_session_memory_path(self, session_id: str) -> Path:
        """获取会话记忆文件路径"""
        path = self.SESSION_MEMORY_DIR / f"{session_id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def read_session_memory(self, session_id: str) -> str | None:
        """读取会话记忆"""
        path = self.get_session_memory_path(session_id)
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return f.read()
        return None

    def write_session_memory(self, session_id: str, content: str) -> None:
        """写入会话记忆"""
        path = self.get_session_memory_path(session_id)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
