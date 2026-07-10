import asyncio
import logging

from jinja2 import Environment, PackageLoader

from ai_agent.tool_parsers import GigaChatParser
from ai_agent.harness import ReActHarness
from ai_agent.models import GigaChatAPIModel
from ai_agent.tools import ToolSet
from ai_agent.memory import ChatMemory
from ai_agent.locale import AgentLocale
from mail_connection_manager import MailConnectionManager
from agents.sorting_agent.services import IncomingTasksService, AgentsMsgsService
from task_managers import FileTaskManager, TaskStatus
from config import config

from agents.sorting_agent.tools import create_sending_task

logger = logging.getLogger(__name__)

jinja_env = Environment(loader=PackageLoader("agents.sorting_agent", "templates"))


def construct_system_prompt() -> str:
    system_prompt_template = jinja_env.get_template("system_prompt.jinja2")
    return system_prompt_template.render(secretary_name=config.secretary.name)


async def main(
    mail_conn: MailConnectionManager,
    incoming_tasks_manager: FileTaskManager,
    agents_msgs_manager: FileTaskManager,
):
    tool_set = ToolSet("sorting_agent_toolset", "toolset for sorting agent", [create_sending_task])
    memory = ChatMemory(system_prompt=construct_system_prompt())
    model = GigaChatAPIModel(
        credentials=config.sorting_agent.gigachat_auth_key,
        tool_parser=GigaChatParser(),
    )
    harness = ReActHarness("ai_sorting_agent", model, tools=tool_set, memory=memory, locale=AgentLocale.ru())

    while True:
        agent_msgs = await agents_msgs_manager.get_tasks_by_status(TaskStatus.PENDING, 5)
        if agent_msgs:
            try:
                service = AgentsMsgsService(agent_msgs, agents_msgs_manager, harness, memory)
                await service.run()
            except Exception as e:
                logger.error(f"[Sorting Agent] Error while running service for agents messages: {e}")
                raise

        pending_tasks = await incoming_tasks_manager.get_tasks_by_status(TaskStatus.PENDING, 5)
        if pending_tasks:
            try:
                service = IncomingTasksService(pending_tasks, incoming_tasks_manager, harness, memory, mail_conn)
                await service.run()
            except Exception as e:
                logger.error(f"[Sorting Agent] Error while running service for incoming tasks: {e}")
                raise
        else:
            logger.info(f"[Sorting Agent] Has nothing to process -> sleep")
            await asyncio.sleep(10)