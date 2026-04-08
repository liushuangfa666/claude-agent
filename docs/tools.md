# 内置工具参考

## Read（读取文件）

**用途**: 读取文件内容，支持大文件截断

**输入**:
```json
{
  "file_path": "src/main.py",
  "max_lines": 100,
  "offset": 0
}
```

**注意**:
- `max_lines` 默认为 100，超出自动截断
- `offset` 支持从指定行开始读取
- 二进制文件不支持

---

## Bash（执行命令）

**用途**: 执行 shell 命令

**输入**:
```json
{
  "command": "ls -la",
  "timeout": 30,
  "cwd": "/path/to/dir"
}
```

**危险操作标记**:
- `rm *` → 危险（删除）
- `mv *` → 需确认（移动）
- `git push` → 需确认（推送）
- `curl/wget` → 安全（网络请求）

**示例**:
- `{"command": "git status"}` - 查看 git 状态
- `{"command": "find . -name '*.py' -type f"}` - 搜索 Python 文件
- `{"command": "ps aux | grep python"}` - 查看进程

---

## Write（写入文件）

**用途**: 创建或覆盖文件

**输入**:
```json
{
  "file_path": "output.txt",
  "content": "Hello World",
  "append": false
}
```

**注意**:
- `append=true` 时追加写入
- 父目录不存在时自动创建
- **危险**: 会覆盖已有文件

---

## Edit（编辑文件）

**用途**: 对文件进行精确编辑（sed 风格）

**输入**:
```json
{
  "file_path": "config.py",
  "old_text": "DEBUG = True",
  "new_text": "DEBUG = False"
}
```

**注意**:
- `old_text` 必须精确匹配
- 支持多行编辑
- **危险**: 不可撤销

---

## Glob（文件搜索）

**用途**: 按模式搜索文件

**输入**:
```json
{
  "pattern": "**/*.py",
  "cwd": "src",
  "max_results": 50
}
```

**示例**:
- `{"pattern": "**/*.md"}` - 所有 Markdown 文件
- `{"pattern": "src/**/*.ts"}` - src 下所有 TypeScript 文件

---

## Grep（内容搜索）

**用途**: 在文件中搜索文本

**输入**:
```json
{
  "pattern": "TODO",
  "path": "src",
  "recursive": true,
  "ignore_case": false
}
```

---

## TodoWrite（待办事项）

**用途**: 记录任务清单

**输入**:
```json
{
  "action": "add",
  "content": "完成用户认证功能",
  "priority": "high"
}
```

**action 选项**: `add` | `done` | `list` | `clear`
