"""
内置工具实现 - ReadTool, BashTool, WriteTool, GrepTool, GlobTool
跨平台支持：Linux 和 Windows
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
from pathlib import Path

try:
    from tool import BaseTool, ToolResult
except ImportError:
    from scripts.tool import BaseTool, ToolResult


IS_WINDOWS = platform.system() == "Windows"
IS_WSL = False

# 检测是否运行在 WSL 中
try:
    with open("/proc/version") as f:
        IS_WSL = "microsoft" in f.read().lower() or "wsl" in f.read().lower()
except (FileNotFoundError, PermissionError):
    pass


def wsl_path_to_linux(windows_path: str) -> str:
    """
    将 Windows 路径转换为 WSL/Linux 路径。

    D:\\wspace\\code\\file.py  ->  /mnt/d/wspace/code/file.py
    C:\\Users\\name\\file.txt  ->  /mnt/c/Users/name/file.txt

    支持的格式：
    - D:\\path\\to\\file
    - D:/path/to/file
    - D:\\\\path\\\\to\\\\file (JavaScript JSON 序列化后的双反斜杠)
    - \\172.25.82.118\\share (UNC 路径，转换为 /mnt/unc/)
    """
    if not IS_WSL:
        return windows_path

    path = windows_path.strip()

    # 归一化反斜杠和双反斜杠
    path = path.replace("\\\\", "/").replace("\\", "/")

    # 处理 UNC 路径 \\server\share -> /mnt/unc/server/share
    if path.startswith("//") or path.startswith("\\\\"):
        unc_match = re.match(r"^(//+|\\\\+)([^/]+)(/.*)?$", path)
        if unc_match:
            server = unc_match.group(2)
            rest = unc_match.group(3) or ""
            return f"/mnt/unc/{server}{rest}"

    # 处理带盘符的路径 D:/path 或 D:\path
    match = re.match(r"^([A-Za-z]):(/.*)?$", path)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2) or ""
        return f"/mnt/{drive}{rest}"

    return windows_path


def normalize_command_paths(command: str) -> str:
    """
    自动识别并转换命令中的 Windows 路径为 WSL 路径。
    处理 git clone、docker run -v、npm install 等常见带路径的命令。
    """
    if not IS_WSL:
        return command

    # 跳过已经是 Linux 路径的命令
    if command.startswith("/") and not re.match(r"^[A-Za-z]:", command):
        return command

    # git clone https://... 或 git clone D:\\... (Windows 本地仓库)
    # docker run -v D:\\path:/container/path
    # npm install --prefix D:\\node_modules
    # python D:\\script.py

    result = command

    # 匹配带盘符的路径作为独立参数（前面有空格、=、:等分隔）
    # D:\path 或 D:/path
    result = re.sub(
        r'(?<=[ =\t\n])((?:[A-Za-z]:)[\\][^ \t\n]+|[A-Za-z]:[/][^ \t\n]+)',
        lambda m: wsl_path_to_linux(m.group(1)),
        result
    )

    # 处理 Docker/Compose 文件挂载：-v host-path:container-path
    # 支持 -v "D:\path:/var/data" 或 -v D:/path:/var/data
    docker_vol_pattern = r'-v\s+((?:[A-Za-z]:[/\\][^: \t\n]+)|(?:"[^"]+")):'
    result = re.sub(
        docker_vol_pattern,
        lambda m: '-v ' + wsl_path_to_linux(m.group(1)) + ':',
        result
    )

    return result


def translate_command(cmd: str) -> str:
    """
    将 Linux 命令翻译为 Windows 等价命令
    """
    if not IS_WINDOWS:
        return cmd
    # ls 系列
    if re.match(r'^ls(\s+.*)?$', cmd):
        if '-l' in cmd and '-a' in cmd:
            cmd = re.sub(r'^ls(\s+-la)?(\s+.*)?$', r'dir /a\2', cmd)
        elif '-l' in cmd:
            cmd = re.sub(r'^ls(\s+-l)?(\s+.*)?$', r'dir\2', cmd)
        elif '-a' in cmd:
            cmd = re.sub(r'^ls(\s+-a)?(\s+.*)?$', r'dir /a\2', cmd)
        else:
            cmd = re.sub(r'^ls(\s+.*)?$', r'dir\1', cmd)
        return cmd

    # grep -> findstr
    if cmd.startswith('grep '):
        cmd = cmd.replace('grep ', 'findstr ')
        # findstr 用 /C:"pattern" 而不是 -e "pattern"
        cmd = re.sub(r'findstr -e\s+"([^"]+)"', r'findstr /C:"\1"', cmd)
        cmd = re.sub(r'findstr -i\s+"([^"]+)"', r'findstr /I "\1"', cmd)
        return cmd

    # cat -> type
    if re.match(r'^cat\s+', cmd):
        return re.sub(r'^cat\s+', 'type ', cmd)

    # pwd -> cd (无输出，用 echo %cd%)
    if cmd.strip() == 'pwd':
        return 'echo %cd%'

    # find -> dir /s /b
    if cmd.startswith('find '):
        # find . -name "*.py" -> dir /s /b *.py
        match = re.search(r'find\s+(\S+)\s+-name\s+"([^"]+)"', cmd)
        if match:
            path, pattern = match.group(1), match.group(2)
            if path == '.':
                return f'dir /s /b {pattern}'
            return f'dir /s /b {pattern}'
        return cmd

    # head -> more (不完美但能用)
    if re.search(r'\bhead\s+-n\s+\d+', cmd):
        cmd = re.sub(r'(\S+)\s*\|\s*head\s+-n\s+(\d+)', r'\1 | more +1', cmd)
        cmd = re.sub(r'head\s+-n\s+(\d+)\s+(\S+)', r'more /P \2 > NUL 2>&1 & type \2 | more +1', cmd)
        return cmd

    # tail -> PowerShell
    if re.search(r'\btail\s+-n', cmd):
        match = re.search(r'tail\s+-n\s+(\d+)\s+(.+)', cmd)
        if match:
            n, file = match.group(1), match.group(2)
            return f'powershell -Command "Get-Content {file} | Select-Object -Last {n}"'

    # rm -rf -> rmdir /s /q
    if 'rm -rf' in cmd:
        cmd = cmd.replace('rm -rf', 'rmdir /s /q')
    elif re.match(r'^rm\s+', cmd):
        cmd = re.sub(r'^rm\s+', 'del /q ', cmd)

    # cp -> copy
    cmd = re.sub(r'^cp\s+', 'copy ', cmd)

    # mv -> move
    cmd = re.sub(r'^mv\s+', 'move ', cmd)

    # mkdir -p -> mkdir (Windows mkdir 已支持多级)
    cmd = re.sub(r'mkdir\s+-p\s+', 'mkdir ', cmd)

    # Windows 路径格式转换: F:/path -> F:\path (在引号内)
    def convert_path(m):
        drive = m.group(1)
        rest = m.group(2).replace("/", "\\")
        return f'"{drive}:\\{rest}"'
    cmd = re.sub(r'"([A-Za-z]):/([^"]+)"', convert_path, cmd)

    def convert_path_unquoted(m):
        drive = m.group(1)
        rest = m.group(2).replace("/", "\\")
        return f'{drive}:\\{rest}'
    cmd = re.sub(r"'([A-Za-z]):/([^']+)'", convert_path_unquoted, cmd)

    # which -> where
    if cmd.startswith('which '):
        cmd = cmd.replace('which ', 'where ')
        return cmd

    # ps aux -> tasklist
    if cmd.strip() == 'ps aux' or cmd.startswith('ps '):
        if '-ef' in cmd:
            return 'tasklist /v'
        return 'tasklist'

    # kill -> taskkill
    if cmd.startswith('kill '):
        match = re.search(r'kill\s+(\d+)', cmd)
        if match:
            return f'taskkill /PID {match.group(1)} /F'
        return cmd

    # chmod -> icacls (Windows)
    if cmd.startswith('chmod '):
        return 'echo chmod not supported on Windows'

    return cmd


# 敏感路径模式 - 用于防止路径穿越攻击
SENSITIVE_PATH_PATTERNS = [
    r"\.\./",           # 路径穿越 ..
    r"\.\.\\",          # Windows 路径穿越
    r"%2e%2e%2f",       # URL 编码 ../
    r"%2e%2e%5c",       # URL 编码 ..\
    r"\.\.%2f",         # 混合编码
    r"\.\.%5c",         # 混合编码
]

# 系统保护路径
PROTECTED_PATHS = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "C:\\Windows\\",
    "C:\\Program Files\\",
    "C:\\Program Files (x86)\\",
    "C:\\System32\\",
]


def validate_path_security(file_path: str) -> tuple[bool, str]:
    """
    验证文件路径安全性，防止路径穿越攻击。
    
    Args:
        file_path: 要验证的文件路径
        
    Returns:
        (is_safe, error_message)
        - is_safe=True, error_message="" 表示路径安全
        - is_safe=False, error_message="..." 表示路径不安全
    """
    # 检查敏感路径模式
    for pattern in SENSITIVE_PATH_PATTERNS:
        if re.search(pattern, file_path, re.IGNORECASE):
            return False, f"路径包含敏感模式: {pattern}"
    
    # 检查系统保护路径
    normalized_path = file_path.replace("\\", "/").lower()
    for protected in PROTECTED_PATHS:
        protected_normalized = protected.replace("\\", "/").lower()
        if protected_normalized in normalized_path:
            return False, f"路径涉及系统保护路径: {protected}"
    
    return True, ""


class ReadTool(BaseTool):
    """读取文件内容"""

    name = "Read"
    description = "读取文件内容，支持大文件截断和指定行范围"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要读取的文件路径"
            },
            "max_lines": {
                "type": "integer",
                "description": "最大行数，默认100",
                "default": 100
            },
            "offset": {
                "type": "integer",
                "description": "从第几行开始，默认0",
                "default": 0
            }
        },
        "required": ["file_path"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        file_path = args["file_path"]
        max_lines = args.get("max_lines", 100)
        offset = args.get("offset", 0)

        # WSL 下转换 Windows 路径
        if IS_WSL:
            file_path = wsl_path_to_linux(file_path)

        # 路径安全检查
        is_safe, error_msg = validate_path_security(file_path)
        if not is_safe:
            return ToolResult(success=False, data=None, error=f"路径安全检查失败: {error_msg}")

        if not os.path.exists(file_path):
            return ToolResult(success=False, data=None, error=f"文件不存在: {file_path}")

        try:
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()

            total_lines = len(lines)
            start = offset
            end = min(offset + max_lines, total_lines)
            content = "".join(lines[start:end])

            truncated = end < total_lines
            result = {
                "content": content,
                "total_lines": total_lines,
                "returned_lines": end - start,
                "truncated": truncated,
                "file_path": file_path
            }

            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class BashTool(BaseTool):
    """执行 shell 命令"""

    name = "Bash"
    description = "执行 shell 命令，用于文件操作、进程管理、git 等"
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 shell 命令"
            },
            "timeout": {
                "type": "integer",
                "description": "超时秒数，默认30",
                "default": 30
            },
            "cwd": {
                "type": "string",
                "description": "执行目录，默认当前目录"
            }
        },
        "required": ["command"]
    }

    def is_destructive(self, args: dict) -> bool:
        cmd = args.get("command", "")
        dangerous = ["rm -rf", "rm ", "dd if=", "mkfs"]
        return any(d in cmd for d in dangerous)

    async def call(self, args: dict, context: dict) -> ToolResult:
        command = args["command"]
        timeout = args.get("timeout", 30)
        cwd = args.get("cwd")

        # WSL 下自动转换 Windows 路径
        if IS_WSL:
            command = normalize_command_paths(command)
            if cwd:
                cwd = wsl_path_to_linux(cwd)

        # Windows 命令翻译
        if IS_WINDOWS:
            command = translate_command(command)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                timeout=timeout,
                cwd=cwd
            )

            output = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
            stderr_decoded = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
            if stderr_decoded:
                output += "\n[stderr]:\n" + stderr_decoded

            # 检查是否是无害的错误
            if result.returncode != 0:
                # mkdir 目录已存在不是真正的问题
                if command.strip().startswith("mkdir") or "mkdir" in command:
                    if "already exists" in stderr_decoded.lower() or "已存在" in stderr_decoded:
                        return ToolResult(
                            success=True,
                            data={
                                "stdout": output or "目录已存在",
                                "stderr": stderr_decoded,
                                "returncode": 0,
                                "command": command
                            }
                        )
                
                error_msg = f"exit code: {result.returncode}"
                if stderr_decoded:
                    error_msg += f": {stderr_decoded.strip()}"
                elif output:
                    error_msg += f": {output.strip()}"
            else:
                error_msg = None

            return ToolResult(
                success=result.returncode == 0,
                data={
                    "stdout": output,
                    "stderr": stderr_decoded,
                    "returncode": result.returncode,
                    "command": command
                },
                error=error_msg
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, data=None, error=f"命令超时: {command}")
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class WriteTool(BaseTool):
    """写入文件"""

    name = "Write"
    description = "创建或覆盖文件内容"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件路径"
            },
            "content": {
                "type": "string",
                "description": "文件内容"
            },
            "append": {
                "type": "boolean",
                "description": "追加模式，默认False（覆盖）",
                "default": False
            }
        },
        "required": ["file_path", "content"]
    }

    def is_destructive(self, args: dict) -> bool:
        # 如果文件存在且是覆盖模式，认为是危险操作
        if args.get("append", False):
            return False
        fp = args["file_path"]
        if IS_WSL:
            fp = wsl_path_to_linux(fp)
        return os.path.exists(fp)

    async def call(self, args: dict, context: dict) -> ToolResult:
        file_path = args["file_path"]
        content = args["content"]
        append = args.get("append", False)

        # WSL 下转换 Windows 路径
        if IS_WSL:
            file_path = wsl_path_to_linux(file_path)

        # 路径安全检查
        is_safe, error_msg = validate_path_security(file_path)
        if not is_safe:
            return ToolResult(success=False, data=None, error=f"路径安全检查失败: {error_msg}")

        try:
            # 确保父目录存在
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)

            mode = "a" if append else "w"
            with open(file_path, mode, encoding="utf-8") as f:
                f.write(content)

            return ToolResult(
                success=True,
                data={
                    "file_path": file_path,
                    "bytes_written": len(content.encode("utf-8")),
                    "append": append
                }
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class GrepTool(BaseTool):
    """在文件中搜索文本"""

    name = "Grep"
    description = "在文件或目录中搜索包含指定文本的行"
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "搜索模式（支持正则）"
            },
            "path": {
                "type": "string",
                "description": "搜索路径，默认当前目录",
                "default": "."
            },
            "recursive": {
                "type": "boolean",
                "description": "递归搜索",
                "default": True
            },
            "ignore_case": {
                "type": "boolean",
                "description": "忽略大小写",
                "default": False
            },
            "file_pattern": {
                "type": "string",
                "description": "文件过滤，如 *.py",
                "default": "*"
            }
        },
        "required": ["pattern"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        pattern = args["pattern"]
        path = args.get("path", ".")
        recursive = args.get("recursive", True)
        ignore_case = args.get("ignore_case", False)
        file_pattern = args.get("file_pattern", "*")

        # WSL 下转换 Windows 路径
        if IS_WSL:
            path = wsl_path_to_linux(path)

        if IS_WINDOWS:
            # Windows: findstr
            case_flag = "/I" if ignore_case else ""
            if recursive:
                cmd = f'findstr /S /N {case_flag} "{pattern}" "{path}\\{file_pattern}"'
            else:
                cmd = f'findstr /N {case_flag} "{pattern}" "{path}"'
        else:
            cmd = "grep -n"
            if ignore_case:
                cmd += " -i"
            if recursive:
                cmd += " -r"
            cmd += f" --include='{file_pattern}' {pattern!r} {path}"

        try:
            result = subprocess.run(cmd, shell=True, capture_output=True)
            stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
            lines = stdout.strip().split("\n") if stdout.strip() else []
            # findstr 找不到匹配时 returncode=1，但这不是真正的错误
            if result.returncode == 1 and not stdout.strip():
                return ToolResult(
                    success=True,
                    data={
                        "matches": [],
                        "count": 0,
                        "pattern": pattern,
                        "path": path
                    }
                )
            return ToolResult(
                success=result.returncode == 0 or (result.returncode == 1 and stdout.strip()),
                data={
                    "matches": lines,
                    "count": len(lines),
                    "pattern": pattern,
                    "path": path,
                    "returncode": result.returncode
                },
                error=None if result.returncode == 0 or (result.returncode == 1 and stdout.strip()) else f"exit code: {result.returncode}"
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class GlobTool(BaseTool):
    """按模式搜索文件"""

    name = "Glob"
    description = "按 glob 模式搜索文件路径"
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "glob 模式，如 **/*.py"
            },
            "cwd": {
                "type": "string",
                "description": "搜索根目录",
                "default": "."
            },
            "max_results": {
                "type": "integer",
                "description": "最大结果数",
                "default": 50
            }
        },
        "required": ["pattern"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        import glob as glob_module

        pattern = args["pattern"]
        cwd = args.get("cwd", ".")
        max_results = args.get("max_results", 50)

        # WSL 下转换 Windows 路径
        if IS_WSL:
            cwd = wsl_path_to_linux(cwd)

        try:
            search_pattern = os.path.join(cwd, pattern)
            matches = glob_module.glob(search_pattern, recursive=True)[:max_results]
            return ToolResult(
                success=True,
                data={
                    "files": matches,
                    "count": len(matches),
                    "pattern": pattern,
                    "truncated": len(matches) >= max_results
                }
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))


class EditTool(BaseTool):
    """
    编辑文件内容 - 精准文本替换

    特性：
    - 支持 oldText 多位置匹配（默认首个匹配会被使用）
    - 错误恢复：oldText 匹配失败时自动尝试：
      1. 去除首尾空白后再匹配
      2. 归一化空白字符（space↔tab）后再匹配
      3. 逐行 fuzzy 匹配找到最相似位置
    - 恢复成功时返回警告（warning 字段），包含修复前后对比
    - 恢复失败时返回详细错误和候选位置列表
    """

    name = "Edit"
    description = "编辑文件内容，精准替换指定文本段"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "文件路径"
            },
            "oldText": {
                "type": "string",
                "description": "要被替换的原文本（必须完整匹配）"
            },
            "newText": {
                "type": "string",
                "description": "替换后的新文本"
            }
        },
        "required": ["file_path", "oldText", "newText"]
    }

    async def call(self, args: dict, context: dict) -> ToolResult:
        file_path = args["file_path"]
        old_text = args["oldText"]
        new_text = args["newText"]

        # WSL 下转换 Windows 路径
        if IS_WSL:
            file_path = wsl_path_to_linux(file_path)

        # 路径安全检查
        is_safe, error_msg = validate_path_security(file_path)
        if not is_safe:
            return ToolResult(success=False, data=None, error=f"路径安全检查失败: {error_msg}")

        if not os.path.exists(file_path):
            return ToolResult(success=False, data=None, error=f"文件不存在: {file_path}")

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"读取文件失败: {e}")

        # 恢复状态
        recovery_warning = None

        # 第一次尝试：精确匹配
        if old_text in content:
            new_content = content.replace(old_text, new_text, 1)
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                return ToolResult(
                    success=True,
                    data={
                        "file_path": file_path,
                        "bytes_before": len(content),
                        "bytes_after": len(new_content),
                    }
                )
            except Exception as e:
                return ToolResult(success=False, data=None, error=f"写入文件失败: {e}")

        # ---- 错误恢复阶段 ----
        recovery_result = await self._try_error_recovery(content, old_text, new_text)

        if recovery_result is None:
            # 恢复失败，返回详细错误
            candidates = self._find_similar_lines(content, old_text)
            error_msg = "oldText 在文件中未找到匹配"
            if candidates:
                error_msg += "\n\n最相似的行（可能你想要的是其中之一）：\n"
                for i, (line_no, similarity, line_text) in enumerate(candidates[:5], 1):
                    error_msg += f"  {i}. 第{line_no}行 (相似度 {similarity:.0%}): {line_text[:60]!r}"

            return ToolResult(
                success=False,
                data=None,
                error=error_msg,
            )

        # 恢复成功，应用修改
        new_content, warning = recovery_result
        recovery_warning = warning

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            return ToolResult(success=False, data=None, error=f"写入文件失败: {e}")

        result_data = {
            "file_path": file_path,
            "bytes_before": len(content),
            "bytes_after": len(new_content),
            "recovered": True,
            "warning": recovery_warning,
        }
        return ToolResult(success=True, data=result_data)

    async def _try_error_recovery(self, content: str, old_text: str, new_text: str):
        """
        尝试错误恢复策略：
        1. 去除首尾空白匹配
        2. 归一化空白（space/tab 互换）
        3. 逐行 fuzzy 匹配找最相似位置
        """
        # 策略1：去除首尾空白
        stripped_old = old_text.strip()
        if stripped_old != old_text and stripped_old in content:
            # 找到后，用原始 oldText 两端的空白情况进行处理
            # 找出 content 中所有匹配位置
            pos = content.find(stripped_old)
            if pos >= 0:
                # 重建：保留原始 oldText 的前后空白
                prefix_len = len(old_text) - len(old_text.lstrip())
                suffix_len = len(old_text) - len(old_text.rstrip())
                prefix = old_text[:prefix_len]
                suffix = old_text[-suffix_len:] if suffix_len else ""
                adjusted_new = prefix + new_text + suffix
                new_content = content.replace(stripped_old, adjusted_new, 1)
                warning = (
                    f"oldText 匹配时自动去除了首尾空白。\n"
                    f"原始: {old_text!r}\n"
                    f"实际匹配: {stripped_old!r}"
                )
                return new_content, warning

        # 策略2：归一化空白（把 oldText 中的 tab 换成 spaces 或反之）
        normalized_old = self._normalize_whitespace(old_text)
        normalized_content = self._normalize_whitespace(content)
        if normalized_old != old_text and normalized_old in normalized_content:
            # 找到归一化后的位置，用原始内容替换
            idx = normalized_content.find(normalized_old)
            original_segment = content[idx:idx + len(old_text)]
            adjusted_new = original_segment[:len(original_segment) - len(original_segment.lstrip())] + \
                          new_text + \
                          original_segment[len(original_segment) - len(original_segment.rstrip()):]
            new_content = content[:idx] + adjusted_new + content[idx + len(old_text):]
            warning = (
                f"oldText 匹配时自动归一化了空白字符（tab/space 互换）。\n"
                f"原始: {old_text!r}\n"
                f"归一化后匹配成功"
            )
            return new_content, warning

        # 策略3：fuzzy 行匹配（找最相似的行序列）
        fuzzy_match = await self._fuzzy_match_and_replace(content, old_text, new_text)
        return fuzzy_match

    def _normalize_whitespace(self, text: str) -> str:
        """将 tab 替换为 4 个空格，或反之（归一化）"""
        # 简单策略：把连续空白归一化为单 space
        import re
        return re.sub(r'[ \t]+', ' ', text)

    async def _fuzzy_match_and_replace(self, content: str, old_text: str, new_text: str):
        """
        逐行 fuzzy 匹配找到 old_text 所在位置，
        返回 (new_content, warning) 或 None
        """
        old_lines = old_text.split('\n')
        content_lines = content.split('\n')

        if len(old_lines) < 2:
            # 单行情况，用字符级相似度
            best_pos = -1
            best_sim = 0
            for i, line in enumerate(content_lines):
                sim = self._line_similarity(old_text.strip(), line.strip())
                if sim > best_sim and sim > 0.6:
                    best_pos = i
                    best_sim = sim
            if best_pos >= 0:
                new_lines = content_lines.copy()
                new_lines[best_pos] = new_text
                warning = (
                    f"oldText 未精确匹配，通过 fuzzy 匹配找到第 {best_pos + 1} 行。\n"
                    f"原始行: {content_lines[best_pos][:50]!r}\n"
                    f"相似度: {best_sim:.0%}\n"
                    f"已替换为: {new_text[:50]!r}"
                )
                return '\n'.join(new_lines), warning
            return None

        # 多行情况：滑动窗口匹配行序列
        best_start = -1
        best_score = 0.0
        window_size = len(old_lines)

        for i in range(len(content_lines) - window_size + 1):
            score = 0.0
            matched_lines = 0
            for j in range(window_size):
                sim = self._line_similarity(old_lines[j].strip(), content_lines[i + j].strip())
                if sim > 0.5:
                    score += sim
                    matched_lines += 1
            if matched_lines >= window_size * 0.6 and score > best_score:
                best_score = score
                best_start = i

        if best_start >= 0:
            new_lines = content_lines.copy()
            # 替换整个 old_text 覆盖的行范围
            new_lines[best_start:best_start + window_size] = [new_text]
            warning = (
                f"oldText 未精确匹配，通过 fuzzy 行匹配找到第 {best_start + 1}-{best_start + window_size} 行。\n"
                f"原始行数: {window_size}，匹配质量: {best_score:.0%}\n"
                f"已替换为新内容"
            )
            return '\n'.join(new_lines), warning

        return None

    def _line_similarity(self, s1: str, s2: str) -> float:
        """计算两行文本的相似度（简单编辑距离）"""
        if not s1 and not s2:
            return 1.0
        if not s1 or not s2:
            return 0.0
        # 公共前缀长度
        prefix_len = 0
        for c1, c2 in zip(s1, s2):
            if c1 == c2:
                prefix_len += 1
            else:
                break
        # 公共后缀长度
        suffix_len = 0
        for c1, c2 in zip(reversed(s1), reversed(s2)):
            if c1 == c2:
                suffix_len += 1
            else:
                break
        # 编辑距离
        max_len = max(len(s1), len(s2))
        if max_len == 0:
            return 1.0
        edit_dist = self._levenshtein_distance(s1, s2)
        return 1.0 - (edit_dist / max_len)

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """计算编辑距离（DP）"""
        m, n = len(s1), len(s2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i - 1] == s2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
        return dp[m][n]

    def _find_similar_lines(self, content: str, old_text: str) -> list:
        """找到与 old_text 最相似的行，返回 [(行号, 相似度, 行内容)]"""
        content_lines = content.split('\n')
        old_lines = old_text.split('\n')
        candidates = []

        for i, line in enumerate(content_lines):
            if len(old_lines) == 1:
                sim = self._line_similarity(old_text.strip(), line.strip())
            else:
                # 多行情况：计算第一行和最后一行的综合相似度
                sim = (self._line_similarity(old_lines[0].strip(), line.strip()) +
                       self._line_similarity(old_lines[-1].strip(), line.strip())) / 2
            if sim > 0.3:
                candidates.append((i + 1, sim, line.strip()))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates


# 注册基础工具
def register_base_tools():
    """注册所有基础工具到全局注册表"""
    try:
        from tool import get_registry
    except ImportError:
        from scripts.tool import get_registry

    tools = [
        ReadTool(),
        BashTool(),
        WriteTool(),
        GrepTool(),
        GlobTool(),
        EditTool(),
    ]

    for tool in tools:
        get_registry().register(tool)


register_base_tools()
