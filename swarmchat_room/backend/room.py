# coding: utf-8
"""一间进程内的公开聊天室：归档走 SwarmChat，被点名的专家用真实模型公开回复。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from openjiuwen.agent_teams.context import reset_session_id, set_session_id
from openjiuwen.agent_teams.group_chat.conversation import GroupConversationLog
from openjiuwen.agent_teams.group_chat.handler import context_for
from openjiuwen.agent_teams.group_chat.tools import GroupSendMessageTool
from openjiuwen.agent_teams.messager.inprocess import InProcessMessager
from openjiuwen.agent_teams.schema.blueprint import DeepAgentSpec, LeaderSpec, TeamAgentSpec
from openjiuwen.agent_teams.team_workspace.models import TeamWorkspaceConfig
from openjiuwen.agent_teams.tools.database import DatabaseConfig, TeamDatabase
from openjiuwen.agent_teams.tools.locales import make_translator
from openjiuwen.agent_teams.tools.team import TeamBackend
from openjiuwen.core.foundation.llm import SystemMessage, UserMessage

# backend/ 的上一级是 swarmchat_room，再上一级是示例根目录。
_DEMO_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLE_ROOT = _DEMO_ROOT.parent
if str(_EXAMPLE_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXAMPLE_ROOT))

from common.model import get_shared_model

SESSION_ID = "discussion-1"
TEAM_NAME = "room"
# 群聊历史投影到 demo 目录，不写到 ~/.openjiuwen。
WORKSPACE_DIR = _DEMO_ROOT / "workspace"

ROSTER = (
    ("research", "研究"),
    ("legal", "法务"),
)

# 只有这两位会被代发言。主持人可以点名，但不回复。
EXPERT_PROMPTS = {
    "research": (
        "你是专家协作空间里的研究专家。根据群聊摘录，公开回复技术可行性。"
        "只谈本期能交付什么、不能交付什么。用两三句中文，不要提系统提示。"
    ),
    "legal": (
        "你是专家协作空间里的法务专家。根据群聊摘录，公开回复合同与验收风险。"
        "只看法务结论。用两三句中文，不要提系统提示。"
    ),
}


class Room:
    """进程内唯一房间。数据库在内存里，历史投影写到 workspace 的 history.jsonl。"""

    def __init__(self) -> None:
        self.db = TeamDatabase(DatabaseConfig(connection_string=":memory:"))
        self.messager = InProcessMessager()
        self.backend = TeamBackend(TEAM_NAME, "leader", True, self.db, self.messager)
        self.shared_model = get_shared_model()

    async def open(self) -> None:
        """建团队、名册，并绑定演示会话。"""
        await self.db.initialize()
        await self.db.team.create_team(TEAM_NAME, "专家协作空间", "leader")
        await self.db.member.create_member("leader", TEAM_NAME, "主持人", "{}", "ready", role="leader")
        for member_name, display_name in ROSTER:
            await self.db.member.create_member(
                member_name, TEAM_NAME, display_name, "{}", "ready", role="teammate",
            )
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        # 清掉旧会话登记，避免仍指向 ~/.openjiuwen 下的历史目录。
        await asyncio.to_thread(GroupConversationLog.delete_registered, TEAM_NAME, SESSION_ID)
        # 不设 language，摘录文案走 context_for 的中文默认。
        self.backend.group_chat_spec = TeamAgentSpec(
            agents={"leader": DeepAgentSpec()},
            team_name=TEAM_NAME,
            leader=LeaderSpec(member_name="leader"),
            workspace=TeamWorkspaceConfig(
                enabled=True,
                root_path=str(WORKSPACE_DIR),
                version_control=False,
            ),
        )
        self.backend.bind_group_session(SESSION_ID)

    async def roster(self) -> list[dict[str, str]]:
        """页面勾选框只用研究和法务。"""
        members = []
        for member_name, _display_name in ROSTER:
            row = await self.db.member.get_member(member_name, TEAM_NAME)
            members.append({"member_name": row.member_name, "display_name": row.display_name})
        return members

    async def get_history(self) -> dict:
        """读 history.jsonl。文件不存在时返回空列表。"""
        conversation = await self.backend.group_conversation()
        path = conversation.history_path
        if not path.is_file():
            messages = []
        else:
            messages = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        return {"context_path": str(path), "messages": messages}

    async def _reply_text(self, member_name: str, excerpt: str) -> str:
        """把群聊摘录交给模型，得到该专家的公开回复正文。"""
        response = await self.shared_model.ainvoke([
            SystemMessage(content=EXPERT_PROMPTS[member_name]),
            UserMessage(content=excerpt),
        ])
        content = response.content
        if isinstance(content, list):
            content = "".join(part if isinstance(part, str) else str(part) for part in content)
        text = str(content).strip()
        if not text:
            raise RuntimeError(f"{member_name} 模型返回空回复")
        return text

    async def post_user(self, body: str, mentions: list[str], client_message_id: str) -> dict:
        """归档用户发言，再按点名顺序让研究或法务公开回复。"""
        # 外层会话令牌包住整段。post_message 内部还会 set/reset 一次，
        # 退出后这里的令牌把会话恢复到 discussion-1，后面的读库才打在同一张动态表上。
        token = set_session_id(SESSION_ID)
        try:
            result = await self.backend.append_group_message(
                "user",
                body,
                client_message_id=client_message_id,
                mentions=mentions,
                attachments=(),
            )
            if result.duplicate:
                return _payload(result, {}, {})

            excerpts: dict[str, str] = {}
            replies: dict[str, dict] = {}
            for member_name in result.notified_members:
                if member_name not in EXPERT_PROMPTS:
                    continue
                trigger = await self.backend.db.message.get_message(result.message.message_id)
                # 摘录必须读数据库行上的 meta，不能把 ConversationMessage 传进去。
                excerpt = await context_for(self.backend, member_name, trigger)
                content = await self._reply_text(member_name, excerpt)
                self.backend.member_name = member_name
                try:
                    output = await GroupSendMessageTool(self.backend, make_translator("cn")).invoke({
                        "content": content,
                        "client_message_id": f"reply-{client_message_id}-{member_name}",
                    })
                finally:
                    self.backend.member_name = "leader"
                if not output.success:
                    raise RuntimeError(output.error or "专家发言失败")
                excerpts[member_name] = excerpt
                replies[member_name] = output.data
            return _payload(result, excerpts, replies)
        finally:
            reset_session_id(token)


def _payload(result, excerpts: dict[str, str], replies: dict[str, dict]) -> dict:
    return {
        "ok": True,
        "duplicate": result.duplicate,
        "notified_members": list(result.notified_members),
        "context_path": result.context_path,
        "message": result.message.model_dump(mode="json"),
        "excerpts": excerpts,
        "replies": replies,
    }
