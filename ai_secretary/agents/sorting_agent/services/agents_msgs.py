import logging
from typing import List

from pydantic import BaseModel

from task_managers import Task, TaskStatus, FileTaskManager, register_data_model
from ai_agent.messages import Message, Role
from ai_agent.harness import Harness
from ai_agent.memory import ChatMemory

logger = logging.getLogger(__name__)


@register_data_model
class AgentMsg(BaseModel):
    agent_name: str
    content: str


class AgentsMsgsService():
    def __init__(
            self,
            agents_msgs: List[Task], 
            agents_msgs_manager: FileTaskManager,
            harness: Harness,
            memory: ChatMemory
        ):
        self.harness = harness
        self.memory = memory
        self.agents_msgs_manager = agents_msgs_manager
        self.agents_msgs = agents_msgs

    @staticmethod
    def _construct_prompt_from_agent_msg(agent_msg_data: AgentMsg) -> str:
        return f"[ СООБЩЕНИЕ ОТ ВНУТРЕННЕГО АГЕНТА ]\nИмя агента: {agent_msg_data.agent_name}\nСодержимое сообщения:\n```\n{agent_msg_data.content}\n```"

    async def run(self):
        logger.info(f"[Sorting Agent] Found msgs from agents -> process")
        for iter, agent_msg in enumerate(self.agents_msgs):
            await self.agents_msgs_manager.update_task(agent_msg.id, TaskStatus.IN_PROGRESS, None)
            logger.info(f"[Sorting Agent] Message {iter}/{len(self.agents_msgs)} started.")

            agent_msg_data: AgentMsg = agent_msg.get_typed_data()
            logger.info(f"[Sorting Agent] Processing message from {agent_msg_data.agent_name}")
            msg = Message(role=Role.USER, content=self._construct_prompt_from_agent_msg(agent_msg_data))

            try:
                # TODO: Отвечать секретарю по почте
                final_answer = await self.harness.run(msg)
            except Exception as e:
                await self.agents_msgs_manager.update_task(agent_msg.id, TaskStatus.FAILED, None)
                logger.error(f"[Sorting Agent] Error occured during ai-agent running. Message ID: {agent_msg.id}. Error: {e}", exc_info=True)
                self.memory.clear()
                continue
                    
            await self.agents_msgs_manager.update_task(agent_msg.id, TaskStatus.COMPLETED, None)
            self.memory.clear()
