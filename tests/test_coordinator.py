"""
Coordinator 模块测试
"""
import pytest
import tempfile
import os
from datetime import datetime


class TestMessage:
    """Message 数据类测试"""

    def test_message_creation(self):
        """测试消息创建"""
        from scripts.coordinator.team import Message

        msg = Message(
            from_agent="worker1",
            to_agent="coord1",
            content="Task completed",
            summary="Task done",
            timestamp=datetime.now(),
            message_type="text"
        )

        assert msg.from_agent == "worker1"
        assert msg.to_agent == "coord1"
        assert msg.content == "Task completed"
        assert msg.summary == "Task done"
        assert msg.message_type == "text"

    def test_message_to_dict(self):
        """测试消息转字典"""
        from scripts.coordinator.team import Message

        timestamp = datetime.now()
        msg = Message(
            from_agent="worker1",
            to_agent="coord1",
            content="Task completed",
            summary="Task done",
            timestamp=timestamp,
            message_type="text"
        )

        data = msg.to_dict()

        assert data["from_agent"] == "worker1"
        assert data["to_agent"] == "coord1"
        assert data["content"] == "Task completed"
        assert data["timestamp"] == timestamp.isoformat()

    def test_message_from_dict(self):
        """测试从字典创建消息"""
        from scripts.coordinator.team import Message

        data = {
            "from_agent": "worker1",
            "to_agent": "coord1",
            "content": "Task completed",
            "summary": "Task done",
            "timestamp": datetime.now().isoformat(),
            "message_type": "text"
        }

        msg = Message.from_dict(data)

        assert msg.from_agent == "worker1"
        assert msg.to_agent == "coord1"
        assert msg.content == "Task completed"


class TestTeammate:
    """Teammate 数据类测试"""

    def test_teammate_creation(self):
        """测试队友创建"""
        from scripts.coordinator.team import Teammate

        teammate = Teammate(
            agent_id="worker_abc12345",
            name="worker1",
            agent_type="worker",
            model="MiniMax-M2",
            color="blue"
        )

        assert teammate.agent_id == "worker_abc12345"
        assert teammate.name == "worker1"
        assert teammate.agent_type == "worker"
        assert teammate.model == "MiniMax-M2"
        assert teammate.color == "blue"
        assert teammate.status == "running"
        assert teammate.mailbox == []

    def test_teammate_to_dict(self):
        """测试队友转字典"""
        from scripts.coordinator.team import Teammate

        teammate = Teammate(
            agent_id="worker_abc12345",
            name="worker1",
            agent_type="worker",
            model="MiniMax-M2",
            color="blue"
        )

        data = teammate.to_dict()

        assert data["agent_id"] == "worker_abc12345"
        assert data["name"] == "worker1"
        assert data["agent_type"] == "worker"
        assert data["mailbox"] == []

    def test_teammate_from_dict(self):
        """测试从字典创建队友"""
        from scripts.coordinator.team import Teammate

        data = {
            "agent_id": "worker_abc12345",
            "name": "worker1",
            "agent_type": "worker",
            "model": "MiniMax-M2",
            "color": "blue",
            "status": "running",
            "mailbox": []
        }

        teammate = Teammate.from_dict(data)

        assert teammate.agent_id == "worker_abc12345"
        assert teammate.name == "worker1"
        assert teammate.agent_type == "worker"

    def test_teammate_from_dict_with_mailbox(self):
        """测试从字典创建带邮箱的队友"""
        from scripts.coordinator.team import Teammate, Message

        data = {
            "agent_id": "worker_abc12345",
            "name": "worker1",
            "agent_type": "worker",
            "model": "MiniMax-M2",
            "color": "blue",
            "mailbox": [
                {
                    "from_agent": "coord1",
                    "to_agent": "worker1",
                    "content": "Hello",
                    "summary": "Hi",
                    "timestamp": datetime.now().isoformat(),
                    "message_type": "text"
                }
            ]
        }

        teammate = Teammate.from_dict(data)

        assert len(teammate.mailbox) == 1
        assert teammate.mailbox[0].from_agent == "coord1"


class TestTeam:
    """Team 数据类测试"""

    def test_team_creation(self):
        """测试团队创建"""
        from scripts.coordinator.team import Team

        team = Team(
            name="my-team",
            lead_agent_id="coord_abc12345"
        )

        assert team.name == "my-team"
        assert team.lead_agent_id == "coord_abc12345"
        assert team.members == []
        assert team.created_at is not None

    def test_team_add_member(self):
        """测试添加成员"""
        from scripts.coordinator.team import Team, Teammate

        team = Team(name="my-team", lead_agent_id="coord_1")
        member = Teammate(
            agent_id="worker_1",
            name="worker1",
            agent_type="worker",
            model="MiniMax-M2",
            color="blue"
        )

        team.add_member(member)

        assert len(team.members) == 1
        assert team.members[0].name == "worker1"

    def test_team_remove_member(self):
        """测试移除成员"""
        from scripts.coordinator.team import Team, Teammate

        team = Team(name="my-team", lead_agent_id="coord_1")
        member = Teammate(
            agent_id="worker_1",
            name="worker1",
            agent_type="worker",
            model="MiniMax-M2",
            color="blue"
        )
        team.add_member(member)

        result = team.remove_member("worker_1")

        assert result is True
        assert len(team.members) == 0

    def test_team_remove_member_not_found(self):
        """测试移除不存在的成员"""
        from scripts.coordinator.team import Team

        team = Team(name="my-team", lead_agent_id="coord_1")

        result = team.remove_member("nonexistent")

        assert result is False

    def test_team_get_member(self):
        """测试获取成员"""
        from scripts.coordinator.team import Team, Teammate

        team = Team(name="my-team", lead_agent_id="coord_1")
        member = Teammate(
            agent_id="worker_1",
            name="worker1",
            agent_type="worker",
            model="MiniMax-M2",
            color="blue"
        )
        team.add_member(member)

        found = team.get_member("worker_1")

        assert found is not None
        assert found.name == "worker1"

    def test_team_get_member_not_found(self):
        """测试获取不存在的成员"""
        from scripts.coordinator.team import Team

        team = Team(name="my-team", lead_agent_id="coord_1")

        found = team.get_member("nonexistent")

        assert found is None

    def test_team_get_member_by_name(self):
        """测试按名称获取成员"""
        from scripts.coordinator.team import Team, Teammate

        team = Team(name="my-team", lead_agent_id="coord_1")
        member = Teammate(
            agent_id="worker_1",
            name="worker1",
            agent_type="worker",
            model="MiniMax-M2",
            color="blue"
        )
        team.add_member(member)

        found = team.get_member_by_name("worker1")

        assert found is not None
        assert found.agent_id == "worker_1"

    def test_team_to_dict(self):
        """测试团队转字典"""
        from scripts.coordinator.team import Team

        team = Team(name="my-team", lead_agent_id="coord_1")
        data = team.to_dict()

        assert data["name"] == "my-team"
        assert data["lead_agent_id"] == "coord_1"
        assert data["members"] == []

    def test_team_from_dict(self):
        """测试从字典创建团队"""
        from scripts.coordinator.team import Team

        data = {
            "name": "my-team",
            "lead_agent_id": "coord_1",
            "members": [],
            "created_at": datetime.now().isoformat()
        }

        team = Team.from_dict(data)

        assert team.name == "my-team"
        assert team.lead_agent_id == "coord_1"


class TestTeamStorage:
    """TeamStorage 测试"""

    def test_storage_init(self):
        """测试存储初始化"""
        from scripts.coordinator.team import TeamStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TeamStorage(base_dir=tmpdir)

            assert storage.base_dir.exists()

    def test_save_and_load_team(self):
        """测试保存和加载团队"""
        from scripts.coordinator.team import Team, Teammate, TeamStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TeamStorage(base_dir=tmpdir)

            team = Team(name="my-team", lead_agent_id="coord_1")
            team.add_member(Teammate(
                agent_id="worker_1",
                name="worker1",
                agent_type="worker",
                model="MiniMax-M2",
                color="blue"
            ))

            storage.save_team(team)

            loaded = storage.load_team("my-team")

            assert loaded is not None
            assert loaded.name == "my-team"
            assert len(loaded.members) == 1

    def test_load_nonexistent_team(self):
        """测试加载不存在的团队"""
        from scripts.coordinator.team import TeamStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TeamStorage(base_dir=tmpdir)

            loaded = storage.load_team("nonexistent")

            assert loaded is None

    def test_delete_team(self):
        """测试删除团队"""
        from scripts.coordinator.team import Team, TeamStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TeamStorage(base_dir=tmpdir)

            team = Team(name="my-team", lead_agent_id="coord_1")
            storage.save_team(team)

            result = storage.delete_team("my-team")

            assert result is True
            assert storage.load_team("my-team") is None

    def test_delete_nonexistent_team(self):
        """测试删除不存在的团队"""
        from scripts.coordinator.team import TeamStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TeamStorage(base_dir=tmpdir)

            result = storage.delete_team("nonexistent")

            assert result is False

    def test_list_teams(self):
        """测试列出团队"""
        from scripts.coordinator.team import Team, TeamStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TeamStorage(base_dir=tmpdir)

            team1 = Team(name="team1", lead_agent_id="coord_1")
            team2 = Team(name="team2", lead_agent_id="coord_2")
            storage.save_team(team1)
            storage.save_team(team2)

            teams = storage.list_teams()

            assert len(teams) == 2
            assert "team1" in teams
            assert "team2" in teams

    def test_team_exists(self):
        """测试团队是否存在"""
        from scripts.coordinator.team import Team, TeamStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = TeamStorage(base_dir=tmpdir)

            team = Team(name="my-team", lead_agent_id="coord_1")
            storage.save_team(team)

            assert storage.team_exists("my-team") is True
            assert storage.team_exists("nonexistent") is False


class TestCreateAgentId:
    """create_agent_id 测试"""

    def test_create_worker_id(self):
        """测试创建 worker ID"""
        from scripts.coordinator.team import create_agent_id

        agent_id = create_agent_id("worker")

        assert agent_id.startswith("worker_")
        assert len(agent_id) == 15  # worker_ + 8 hex chars

    def test_create_coordinator_id(self):
        """测试创建 coordinator ID"""
        from scripts.coordinator.team import create_agent_id

        agent_id = create_agent_id("coordinator")

        assert agent_id.startswith("coord_")
        assert len(agent_id) == 14

    def test_create_id_default_worker(self):
        """测试默认创建 worker ID"""
        from scripts.coordinator.team import create_agent_id

        agent_id = create_agent_id()

        assert agent_id.startswith("worker_")


class TestCreateTeamId:
    """create_team_id 测试"""

    def test_create_team_id(self):
        """测试创建团队 ID"""
        from scripts.coordinator.team import create_team_id

        team_id = create_team_id()

        assert team_id.startswith("team_")
        assert len(team_id) == 13  # team_ + 8 hex chars
