import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

from agents.sorting_agent.main import main as sorting_agent_main
from agents.sending_agent.main import main as sending_agent_main
 

async def main():
    async with asyncio.TaskGroup() as tg:
        sorting_agent_run = tg.create_task(sorting_agent_main())
        sending_agent_run = tg.create_task(sending_agent_main())
    

if __name__ == "__main__":
    asyncio.run(main())