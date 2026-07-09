import logging
from typing import List

from pydantic import BaseModel

from task_managers import Task, TaskStatus, FileTaskManager, register_data_model
from ai_agent.messages import Message, Role
from ai_agent.harness import Harness

logger = logging.getLogger(__name__)


@register_data_model
class EmailReadTask(BaseModel):
    sender: str
    email: str
    content: str


class IncomingTasksService():
    def __init__(
            self,
            tasks: List[Task], 
            incoming_tasks_manager: FileTaskManager,
            harness: Harness
        ):
        self.harness = harness
        self.incoming_tasks_manager = incoming_tasks_manager
        self.tasks = tasks

    @staticmethod
    def _construct_prompt_from_email(task_data: EmailReadTask) -> str:
        return f"Письмо от: {task_data.sender}\nEmail отправителя: {task_data.email}\nСодержимое письма:\n```{task_data.content}\n```"

    async def run(self):
        logger.info(f"[Sorting Agent] Found tasks -> process")
        for iter, task in enumerate(self.tasks):
            await self.incoming_tasks_manager.update_task(task.id, TaskStatus.IN_PROGRESS, None)
            logger.info(f"[Sorting Agent] Task {iter}/{len(self.tasks)} started.")

            task_data: EmailReadTask = task.get_typed_data()
            msg = Message(role=Role.USER, content=self._construct_prompt_from_email(task_data))

            try:
                # TODO: Отвечать секретарю по почте
                final_answer = await self.harness.run(msg)
            except Exception as e:
                await self.incoming_tasks_manager.update_task(task.id, TaskStatus.FAILED, None)
                logger.error(f"[Sorting Agent] Error occured during ai-agent running. Task ID: {task.id}. Error: {e}", exc_info=True)
                continue
                    
            await self.incoming_tasks_manager.update_task(task.id, TaskStatus.COMPLETED, None)
