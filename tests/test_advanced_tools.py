"""Tests for advanced tools - Task tools, Web tools, Plan tools, Worktree tools"""
import os
import tempfile

import pytest

from scripts.tools_advanced import (
    TaskCreateTool,
    TaskGetTool,
    TaskListTool,
    TaskUpdateTool,
    TaskOutputTool,
    TaskStopTool,
    TodoWriteTool,
    WebFetchTool,
    WorktreeCreateTool,
    WorktreeRemoveTool,
    WorktreeListTool,
)


class TestTaskTools:
    @pytest.mark.asyncio
    async def test_task_create(self):
        tool = TaskCreateTool()
        result = await tool.call({
            "subject": "Test task",
            "description": "A test task"
        }, {})
        assert result.success is True
        assert "task" in result.data
        assert result.data["task"]["id"] is not None

    @pytest.mark.asyncio
    async def test_task_list(self):
        tool = TaskListTool()
        result = await tool.call({}, {})
        assert result.success is True
        assert "tasks" in result.data
        assert isinstance(result.data["tasks"], list)

    @pytest.mark.asyncio
    async def test_task_get_not_found(self):
        tool = TaskGetTool()
        result = await tool.call({"taskId": "99999"}, {})
        assert result.success is True
        assert result.data["task"] is None

    @pytest.mark.asyncio
    async def test_task_update_not_found(self):
        tool = TaskUpdateTool()
        result = await tool.call({"taskId": "99999", "status": "completed"}, {})
        assert result.success is False
        assert "不存在" in result.error


class TestTodoWriteTool:
    @pytest.mark.asyncio
    async def test_todo_write(self):
        tool = TodoWriteTool()
        todos = [
            {"status": "in_progress", "content": "Task 1", "activeForm": "Working on task 1"},
            {"status": "pending", "content": "Task 2", "activeForm": ""}
        ]
        result = await tool.call({"todos": todos}, {})
        assert result.success is True
        assert result.data["todos"] == todos


class TestTaskOutputTool:
    @pytest.mark.asyncio
    async def test_task_output_not_found(self):
        tool = TaskOutputTool()
        result = await tool.call({"task_id": "nonexistent"}, {})
        assert result.success is False
        assert "不存在" in result.error


class TestTaskStopTool:
    @pytest.mark.asyncio
    async def test_task_stop_not_found(self):
        tool = TaskStopTool()
        result = await tool.call({"task_id": "nonexistent"}, {})
        assert result.success is False
        assert "不存在" in result.error


class TestWebFetchTool:
    @pytest.mark.asyncio
    async def test_web_fetch_invalid_url(self):
        tool = WebFetchTool()
        result = await tool.call({
            "url": "http://localhost:99999/nonexistent",
            "prompt": "test"
        }, {})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_web_fetch_missing_params(self):
        tool = WebFetchTool()
        result = await tool.call({"url": ""}, {})
        assert result.success is False


class TestWorktreeTools:
    @pytest.mark.asyncio
    async def test_worktree_create_invalid_repo(self):
        tool = WorktreeCreateTool()
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = await tool.call({"name": "test-worktree"}, {})
                assert result.success is False
                assert "git" in result.error.lower() or "Failed" in result.error
            finally:
                os.chdir(original_dir)

    @pytest.mark.asyncio
    async def test_worktree_remove_not_exists(self):
        tool = WorktreeRemoveTool()
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = await tool.call({"name": "nonexistent-worktree"}, {})
                assert result.success is False
            finally:
                os.chdir(original_dir)

    @pytest.mark.asyncio
    async def test_worktree_list(self):
        if not os.path.exists(".git"):
            pytest.skip("Not a git repository")
        tool = WorktreeListTool()
        result = await tool.call({}, {})
        assert result.success is True
        assert "worktrees" in result.data
        assert isinstance(result.data["worktrees"], list)
