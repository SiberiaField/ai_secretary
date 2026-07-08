import logging
from typing import Optional
import asyncio
import inspect

logger = logging.getLogger(__name__)

from ai_agent.harness.base import Harness
from ai_agent.models import Model
from ai_agent.messages import Message, ModelResponse, ToolMessage, ToolCall, Role
from ai_agent.tools import ToolSet
from ai_agent.memory import ChatMemory
from ai_agent.locale import AgentLocale


class ReActHarness(Harness):
    def __init__(
        self,
        name: str,
        model: Model, 
        tools: ToolSet,
        memory: ChatMemory,
        max_iterations: int = 10,
        locale: Optional[AgentLocale] = None,
        **generate_kwargs
    ):
        super().__init__(memory)
        self.name = name
        self.model = model
        self.tools = tools
        self.max_iterations = max_iterations
        self.generate_kwargs = generate_kwargs
        
        self.locale = locale or AgentLocale.en()
        
        logger.info(f"[{self.name}] Agent initialized with {len(self.tools)} tools.")

    async def run(self, message: Message) -> ModelResponse:
        self.memory.add(message)
        
        iterations = 0
        while iterations < self.max_iterations:
            iterations += 1
            logger.debug(f"[{self.name}] Starting iteration {iterations}/{self.max_iterations}")
            
            context = self.memory.get_context()
            
            if inspect.iscoroutinefunction(self.model.__call__):
                model_response = await self.model.__call__(context, self.tools, **self.generate_kwargs)
            else:
                model_response = await asyncio.to_thread(self.model.__call__, context, self.tools, **self.generate_kwargs)
            
            self.memory.add(model_response.message)
            logger.debug(f"[{self.name}] Model answered: ### {model_response.message.content} ###")
            
            if model_response.message.tool_calls:
                logger.info(f"[{self.name}] Model requested {len(model_response.message.tool_calls)} tool calls.")
                
                for tool_call in model_response.message.tool_calls:
                    logger.debug(f"[{self.name}] Executing tool: {tool_call.name} with args: {tool_call.arguments}")
                    
                    tool_result = await self._execute_tool(tool_call)
                    
                    observation_message = ToolMessage(
                        role=Role.TOOL, 
                        content=tool_result,
                        tool_name=tool_call.name,
                        tool_call_id=tool_call.id
                    )
                    self.memory.add(observation_message)
            elif model_response.message.tool_call_error:
                logger.warning(f"[{self.name}] Tool parsing error detected: {model_response.message.tool_call_error}")
                
                raw_output = model_response.message.content or ""
                
                if len(raw_output) > 1000:
                    raw_output = raw_output[:500] + "\n...\n" + raw_output[-500:]
                
                error_message = self.locale.tool_calling_error.format(
                    error=str(model_response.message.tool_call_error),
                    raw_output=raw_output
                )
                
                error_observation = ToolMessage(
                    role=Role.TOOL,
                    content=error_message,
                    tool_call_id=None
                )
                self.memory.add(error_observation)
                
                logger.info(f"[{self.name}] Error message added to memory, retrying...")
            else:
                logger.info(f"[{self.name}] Final answer generated.")
                return model_response
                
        error_msg = f"[{self.name}] Agent reached max iterations ({self.max_iterations}) without a final answer."
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    async def _execute_tool(self, tool_call: ToolCall) -> str:
        """
        Выполняет инструмент. 
        """
        tool_name = tool_call.name
        
        if tool_name not in self.tools.tools:
            error_text = self.locale.tool_not_found.format(
                tool_name=tool_name, 
                available_tools=", ".join(self.tools.tools.keys())
            )
            logger.warning(f"[{self.name}] {error_text}")
            return error_text

        tool = self.tools.tools[tool_name]
        
        try:
            if tool.is_async:
                result = await tool.func(**tool_call.arguments)
            else:
                result = await asyncio.to_thread(tool.func, **tool_call.arguments)
                
            logger.debug(f"[{self.name}] Tool '{tool_name}' executed successfully.")
            return result
        except Exception as e:
            logger.error(
                f"[{self.name}] Failed while executing tool '{tool_name}': {e}", 
                exc_info=True
            )
            
            return self.locale.tool_execution_error.format(
                tool_name=tool_name, 
                error=str(e)
            )