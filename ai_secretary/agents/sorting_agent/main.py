import asyncio
import logging

from jinja2 import Environment, PackageLoader
from pydantic import BaseModel

from ai_agent.tool_parsers import GigaChatParser
from ai_agent.harness import ReActHarness
from ai_agent.models import GigaChatAPIModel
from ai_agent.tools import ToolSet
from ai_agent.memory import ChatMemory
from ai_agent.locale import AgentLocale
from ai_agent.messages import Message, Role
from task_managers import FileTaskManager, TaskStatus, register_data_model
from config import config

from agents.sorting_agent.tools import create_sending_task

logger = logging.getLogger(__name__)


incoming_tasks_client = FileTaskManager(config.sorting_agent.tasks_root_dir)

@register_data_model
class EmailReadTask(BaseModel):
    sender: str
    email: str
    content: str


jinja_env = Environment(
    loader=PackageLoader(
        "agents.sorting_agent",
        "templates"
    )
)


def construct_system_prompt() -> str:
    system_prompt_template = jinja_env.get_template("system_prompt.jinja2")
    return system_prompt_template.render(secretary_name=config.secretary.name)


def construct_prompt_from_email(task_data: EmailReadTask) -> str:
    return f"Письмо от: {task_data.sender}\nEmail отправителя: {task_data.email}\nСодержимое письма:\n```{task_data.content}\n```"


async def main():
    tool_set = ToolSet("sorting_agent_toolset", "toolset for sorting agent", [create_sending_task])
    memory = ChatMemory(system_prompt=construct_system_prompt())
    model = GigaChatAPIModel(
        credentials=config.sorting_agent.gigachat_auth_key, 
        tool_parser=GigaChatParser(),
    )
    harness = ReActHarness("ai_sorting_agent", model, tools=tool_set, memory=memory, locale=AgentLocale.ru())

    while True:
        pending_tasks = await incoming_tasks_client.get_tasks_by_status(TaskStatus.PENDING)
        if pending_tasks:
            logger.info(f"[Sorting Agent] Found tasks -> process")
            for iter, pending_task in enumerate(pending_tasks):
                await incoming_tasks_client.update_task(pending_task.id, TaskStatus.IN_PROGRESS, None)
                logger.info(f"[Sorting Agent] Task {iter}/{len(pending_tasks)} started.")

                task_data: EmailReadTask = pending_task.get_typed_data()
                msg = Message(role=Role.USER, content=construct_prompt_from_email(task_data))

                try:
                    final_answer = await harness.run(msg)
                except Exception as e:
                    await incoming_tasks_client.update_task(pending_task.id, TaskStatus.FAILED, None)
                    logger.error(f"[Sorting Agent] Error occured during ai-agent running. Task ID: {pending_task.id}. Error: {e}", exc_info=True)
                    memory.clear()
                    continue
                
                await incoming_tasks_client.update_task(pending_task.id, TaskStatus.COMPLETED, None)
                memory.clear()
        else:
            logger.info(f"[Sorting Agent] There are no tasks -> sleep")
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
