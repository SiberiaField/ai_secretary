import asyncio
import logging
from pathlib import Path

from jinja2 import Environment, PackageLoader

from task_managers import FileTaskManager, TaskStatus
from agents.sending_agent.services import IncomingTasksService
from config import config

logger = logging.getLogger(__name__)


incoming_tasks_manager = FileTaskManager(config.sending_agent.tasks_root_dir)
sorting_agent_msgs_manager = FileTaskManager(config.sorting_agent.agents_msgs_dir)

jinja_env = Environment(
    loader=PackageLoader(
        "agents.sending_agent",
        "templates"
    )
)


async def main():
    output_dir = Path(config.sending_agent.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    while True:
        pending_tasks = await incoming_tasks_manager.get_tasks_by_status(TaskStatus.PENDING, 5)
        if pending_tasks:
            try:
                service = IncomingTasksService(
                    pending_tasks, 
                    jinja_env, 
                    incoming_tasks_manager, 
                    sorting_agent_msgs_manager, 
                    output_dir
                )
                await service.run()
            except Exception as e:
                logger.error(f"[Sorting Agent] Error while runnig service for incoming tasks: {e}")
                raise
        else:
            logger.info(f"[Sending Agent] Has nothing to process -> sleep")
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
