import logging
from typing import List, Optional
from datetime import datetime

from pydantic import BaseModel

from task_managers import Task, TaskStatus, FileTaskManager, register_data_model
from ai_agent.messages import Message, Role
from ai_agent.harness import Harness
from mail_agent import EmailMessage, EmailAddress
from mail_connection_manager import MailConnectionManager
import asyncio
mail_lock = asyncio.Lock()

logger = logging.getLogger(__name__)


class EmailAddressData(BaseModel):
    name: Optional[str]
    address: str


@register_data_model
class EmailReadTask(BaseModel):
    # для промпта агенту
    sender: str
    email: str
    content: str

    # снимок полей EmailMessage, нужных для save_draft
    uid: int
    uid_validity: int
    folder: str
    message_id: str
    in_reply_to: Optional[str]
    references: List[str]
    from_addr: EmailAddressData
    subject: str


def _task_to_email_message(task_data: EmailReadTask) -> EmailMessage:
    """Восстанавливает EmailMessage из сохранённого снимка задачи —
    только полей, которые реально использует build_reply_mime()
    (subject/from_addr/message_id/references/in_reply_to). Остальные
    поля не участвовали в исходном письме на момент сохранения задачи
    и заполняются безопасными пустыми значениями, т.к. save_draft их
    не читает."""
    return EmailMessage(
        message_id=task_data.message_id,
        uid=task_data.uid,
        uid_validity=task_data.uid_validity,
        folder=task_data.folder,
        in_reply_to=task_data.in_reply_to,
        references=task_data.references,
        from_addr=EmailAddress(name=task_data.from_addr.name, address=task_data.from_addr.address),
        to=[],
        cc=[],
        subject=task_data.subject,
        date=None,
        body_text=None,
        body_html=None,
        attachments=[],
        flags=frozenset(),
    )

class IncomingTasksService():
    def __init__(
            self,
            tasks: List[Task],
            incoming_tasks_manager: FileTaskManager,
            harness: Harness,
            mail_conn: MailConnectionManager,
        ):
        self.harness = harness
        self.incoming_tasks_manager = incoming_tasks_manager
        self.tasks = tasks
        self.mail_conn = mail_conn

    @staticmethod
    def _construct_prompt_from_email(task_data: EmailReadTask) -> str:
        return f"Письмо от: {task_data.sender}\nEmail отправителя: {task_data.email}\nСодержимое письма:\n```{task_data.content}\n```"

    async def _save_reply_draft(self, task_data: EmailReadTask, reply_text: str) -> None:
        original_message = _task_to_email_message(task_data)
        body_html = f"<p>{reply_text}</p>"
        await self.mail_conn.call(self.mail_conn.mail_agent.save_draft, original_message, body_html=body_html)


    async def run(self):
        logger.info(f"[Sorting Agent] Found tasks -> process")
        for iter, task in enumerate(self.tasks):
            await self.incoming_tasks_manager.update_task(task.id, TaskStatus.IN_PROGRESS, None)
            logger.info(f"[Sorting Agent] Task {iter}/{len(self.tasks)} started.")

            task_data: EmailReadTask = task.get_typed_data()
            msg = Message(role=Role.USER, content=self._construct_prompt_from_email(task_data))

            try:
                final_answer = await self.harness.run(msg)
            except Exception as e:
                await self.incoming_tasks_manager.update_task(task.id, TaskStatus.FAILED, None)
                logger.error(f"[Sorting Agent] Error occured during ai-agent running. Task ID: {task.id}. Error: {e}", exc_info=True)
                continue

            try:
                await self._save_reply_draft(task_data, final_answer.message.content)
            except Exception as e:
                await self.incoming_tasks_manager.update_task(task.id, TaskStatus.FAILED, None)
                logger.error(f"[Sorting Agent] Error occured while saving draft. Task ID: {task.id}. Error: {e}", exc_info=True)
                continue

            await self.incoming_tasks_manager.update_task(task.id, TaskStatus.COMPLETED, None)