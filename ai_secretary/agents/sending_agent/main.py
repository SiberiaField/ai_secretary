import asyncio
import logging
from pathlib import Path

from jinja2 import Environment, PackageLoader

from mail_connection_manager import MailConnectionManager
from task_managers import FileTaskManager, TaskStatus
from agents.sending_agent.services import IncomingTasksService
from config import config

logger = logging.getLogger(__name__)

jinja_env = Environment(loader=PackageLoader("agents.sending_agent", "templates"))


async def main(mail_conn: MailConnectionManager, incoming_tasks_manager: FileTaskManager, sorting_agent_msgs_manager: FileTaskManager):
    output_dir = Path(config.sending_agent.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    while True:
        pending_tasks = await incoming_tasks_manager.get_tasks_by_status(TaskStatus.PENDING, 5)
        if pending_tasks:
            try:
                service = IncomingTasksService(pending_tasks, jinja_env, incoming_tasks_manager, sorting_agent_msgs_manager, mail_conn, output_dir)
                await service.run()
            except Exception as e:
                logger.error(f"[Sending Agent] Error while running service for incoming tasks: {e}")
                raise
        else:
            logger.info(f"[Sending Agent] Has nothing to process -> sleep")
            await asyncio.sleep(10)
