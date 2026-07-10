import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

from mail_connection_manager import build_mail_connection
from agents.sorting_agent.main import main as sorting_agent_main
from agents.sending_agent.main import main as sending_agent_main
from mail_poller import poll_mail
from task_managers import FileTaskManager
from config import config


async def main():
    mail_conn = await build_mail_connection(config)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(poll_mail(mail_conn, FileTaskManager(config.sorting_agent.tasks_root_dir)))
        tg.create_task(sorting_agent_main(mail_conn, FileTaskManager(config.sorting_agent.tasks_root_dir), FileTaskManager(config.sorting_agent.agents_msgs_dir)))
        tg.create_task(sending_agent_main(mail_conn, FileTaskManager(config.sending_agent.tasks_root_dir), FileTaskManager(config.sorting_agent.agents_msgs_dir)))


if __name__ == "__main__":
    asyncio.run(main())