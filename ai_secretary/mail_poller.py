import asyncio
import logging

from mail_agent import EmailMessage, ProcessingStatus
from task_managers import FileTaskManager, TaskStatus
from mail_connection_manager import MailConnectionManager

logger = logging.getLogger(__name__)


def _email_message_to_task_data(msg: EmailMessage) -> dict:
    return {
        "sender": msg.from_addr.name or msg.from_addr.address,
        "email": msg.from_addr.address,
        "content": msg.body_text or msg.body_html or "",
        "uid": msg.uid,
        "uid_validity": msg.uid_validity,
        "folder": msg.folder,
        "message_id": msg.message_id,
        "in_reply_to": msg.in_reply_to,
        "references": msg.references,
        "from_addr": {"name": msg.from_addr.name, "address": msg.from_addr.address},
        "subject": msg.subject,
    }


async def poll_mail(
    mail_conn: MailConnectionManager,
    incoming_tasks_manager: FileTaskManager,
    poll_interval: int = 30,
) -> None:
    while True:
        try:
            messages = await mail_conn.call(mail_conn.mail_agent.fetch_new_messages)

            for msg in messages:
                task_data = _email_message_to_task_data(msg)
                await incoming_tasks_manager.create_task(
                    task_data=task_data,
                    data_type="EmailReadTask",
                    initial_status=TaskStatus.PENDING,
                )
                logger.info(f"[Mail Poller] Task created for {msg.message_id!r} from {msg.from_addr.address}")

                await mail_conn.call(mail_conn.mail_agent.mark_processed, msg, ProcessingStatus.PROCESSED)

        except Exception as e:
            logger.error(f"[Mail Poller] Error while polling mail: {e}", exc_info=True)

        await asyncio.sleep(poll_interval)