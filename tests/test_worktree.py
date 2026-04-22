"""Tests for worktree module - manager and isolation"""
import os
import platform
import subprocess
import pytest

from scripts.worktree import WorktreeManager, WorktreeInfo, WORKTREE_BASE


class TestWorktreeInfo:
    def test_create_info(self):
        info = WorktreeInfo(path="/tmp/test", branch="main", is_main=False)
        assert info.path == "/tmp/test"
        assert info.branch == "main"
        assert info.is_main is False

    def test_is_main(self):
        info = WorktreeInfo(path="/main/repo", branch="main", is_main=True)
        assert info.is_main is True


class TestWorktreeManager:
    def test_init_default_path(self):
        manager = WorktreeManager()
        assert manager.base_path == WORKTREE_BASE

    def test_init_custom_path(self, tmp_path):
        custom_path = tmp_path / "custom_worktrees"
        manager = WorktreeManager(base_path=custom_path)
        assert manager.base_path == custom_path
        assert custom_path.exists()

    def test_get_path(self, tmp_path):
        manager = WorktreeManager(base_path=tmp_path)
        path = manager.get_path("my-feature")
        assert path == tmp_path / "my-feature"

    def test_exists_false(self, tmp_path):
        manager = WorktreeManager(base_path=tmp_path)
        assert manager.exists("nonexistent") is False

    def test_exists_true(self, tmp_path):
        manager = WorktreeManager(base_path=tmp_path)
        (tmp_path / "existing").mkdir()
        assert manager.exists("existing") is True

    @pytest.mark.skipif(platform.system() == "Windows", reason="Git worktree behavior differs on Windows")
    def test_create_worktree(self, tmp_path):
        manager = WorktreeManager(base_path=tmp_path)
        if not os.path.exists(".git"):
            pytest.skip("Not a git repository")
        
        try:
            worktree_path = manager.create("test-worktree")
            assert worktree_path.exists()
            assert manager.exists("test-worktree") is True
        finally:
            try:
                manager.remove("test-worktree")
            except:
                pass

    @pytest.mark.skipif(platform.system() == "Windows", reason="Git worktree behavior differs on Windows")
    def test_list_worktrees(self):
        if not os.path.exists(".git"):
            pytest.skip("Not a git repository")
        
        manager = WorktreeManager()
        worktrees = manager.list()
        assert isinstance(worktrees, list)

    @pytest.mark.skipif(platform.system() == "Windows", reason="Git worktree behavior differs on Windows")
    def test_remove_nonexistent_raises(self, tmp_path):
        manager = WorktreeManager(base_path=tmp_path)
        with pytest.raises(ValueError, match="does not exist"):
            manager.remove("nonexistent-worktree")


class TestWorktreeBase:
    def test_worktree_base_is_path(self):
        assert isinstance(WORKTREE_BASE, os.PathLike)
