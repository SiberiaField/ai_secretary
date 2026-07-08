from __future__ import annotations

import json
from typing import Optional, Any

from gigachat import GigaChat
from gigachat.models import MessagesRole, Chat

from ai_agent.models.base import Model
from ai_agent.tool_parsers import ToolParser, ToolParsingError
from ai_agent.messages import (
    Message, 
    AssistantMessage, 
    ModelResponse, 
    Role, 
    TokenUsage,
    ToolCall
)
from ai_agent.tools import ToolSet


class GigaChatAPIModel(Model):
    """
    Модель для работы с GigaChat API через библиотеку gigachat.
    
    Использует нативную поддержку function calling в GigaChat API.
    """
    
    def __init__(
        self,
        credentials: str,
        tool_parser: ToolParser,
        model: str = "GigaChat",
        scope: str = "GIGACHAT_API_PERS",
        verify_ssl_certs: bool = False,
        default_generation_kwargs: Optional[dict] = None,
    ):
        """
        Parameters
        ----------
        credentials
            Авторизационные данные для GigaChat API (токен или путь к файлу).
        tool_parser
            Парсер для извлечения tool calls из текстового ответа.
            Используется как fallback, если API не вернул tool_calls напрямую.
        model
            Название модели GigaChat (GigaChat, GigaChat-Pro, GigaChat-Max).
        scope
            Область действия токена (GIGACHAT_API_PERS, GIGACHAT_API_CORP, GIGACHAT_API_FINT).
        verify_ssl_certs
            Проверять SSL сертификаты (обычно False для корпоративной среды).
        default_generation_kwargs
            Параметры генерации по умолчанию (temperature, max_tokens и т.д.).
        """
        self.credentials=credentials
        self.scope=scope
        self.verify_ssl_certs=verify_ssl_certs
        self.model=model
        self.model_name = model
        self.tool_parser = tool_parser
        self.default_generation_kwargs = default_generation_kwargs or {}
    
    def _to_gigachat_messages(
        self, 
        messages: list[Message]
    ) -> list[dict[str, Any]]:
        """
        Конвертирует список Message в формат, ожидаемый GigaChat API.
        """
        gigachat_messages = []
        
        for msg in messages:
            role_map = {
                Role.SYSTEM: MessagesRole.SYSTEM,
                Role.USER: MessagesRole.USER,
                Role.ASSISTANT: MessagesRole.ASSISTANT,
                Role.TOOL: MessagesRole.FUNCTION
            }
            
            gigachat_msg = {
                "role": role_map[msg.role],
                "content": msg.content,
            }
            
            if msg.role == Role.ASSISTANT and hasattr(msg, 'tool_calls') and msg.tool_calls:
                gigachat_msg["function_call"] = {
                    "name": msg.tool_calls[0].name,
                    "arguments": msg.tool_calls[0].arguments,
                }
            elif msg.role == Role.TOOL:
                gigachat_msg["name"] = msg.tool_name
            
            gigachat_messages.append(gigachat_msg)
        
        return gigachat_messages
    
    def _to_gigachat_functions(
        self, 
        tools: ToolSet
    ) -> list[dict[str, Any]]:
        """
        Конвертирует ToolSet в формат functions для GigaChat API.
        """
        functions = []
        
        for tool_def in tools.to_llm_definition():
            func = {
                "name": tool_def["function"]["name"],
                "description": tool_def["function"].get("description", ""),
                "parameters": tool_def["function"].get("parameters", {}),
            }
            functions.append(func)
        
        return functions
    
    def _parse_tool_calls_from_response(
        self, 
        response: Any
    ) -> tuple[list[ToolCall], Optional[str]]:
        """
        Извлекает tool calls из ответа GigaChat API.
        
        Если API вернул function_call напрямую — использует его.
        Иначе пытается распарсить из текста через tool_parser.
        
        Returns
        -------
        tuple[list[ToolCall], Optional[str]]
            Список tool calls и ошибка парсинга (если была).
        """
        message = response.choices[0].message
        
        if response.choices[0].finish_reason == "function_call":
            try:
                tool_call = ToolCall(
                    id=None,
                    name=message.function_call.name,
                    arguments=message.function_call.arguments,
                )
                return [tool_call], None
            except (json.JSONDecodeError, AttributeError) as e:
                pass
        
        text = message.content or ""
        try:
            tool_calls = self.tool_parser(text)
            return tool_calls, None
        except ToolParsingError as e:
            return [], e.message
    
    async def __call__(
        self,
        messages: list[Message],
        tools: Optional[ToolSet] = None,
        **generation_kwargs,
    ) -> ModelResponse:
        """
        Генерирует ответ модели через GigaChat API.
        
        Parameters
        ----------
        messages
            История диалога.
        tools
            Набор доступных инструментов.
        **generation_kwargs
            Параметры генерации (переопределяют default_generation_kwargs).
        
        Returns
        -------
        ModelResponse
            Структурированный ответ модели.
        """
        # Конвертируем сообщения
        gigachat_messages = self._to_gigachat_messages(messages)
        
        # Формируем параметры запроса
        request_params = {
            "messages": gigachat_messages,
            **self.default_generation_kwargs,
            **generation_kwargs,
        }
        
        # Добавляем функции, если переданы
        if tools is not None and len(tools) > 0:
            request_params["functions"] = self._to_gigachat_functions(tools)
        
        # Отправляем запрос к API
        async with GigaChat(credentials=self.credentials, scope=self.scope, verify_ssl_certs=self.verify_ssl_certs, model=self.model) as client:
            response = await client.achat(Chat(**request_params))
        
        # Извлекаем текст ответа
        message = response.choices[0].message
        text = message.content or ""
        
        # Парсим tool calls
        tool_calls, tool_call_error = self._parse_tool_calls_from_response(response)
        
        # Извлекаем usage
        usage = TokenUsage(
            input=response.usage.prompt_tokens,
            output=response.usage.completion_tokens,
            total=response.usage.total_tokens
        )
        
        # Определяем finish_reason
        finish_reason = response.choices[0].finish_reason or "stop"
        
        return ModelResponse(
            message=AssistantMessage(
                role=Role.ASSISTANT,
                content=text,
                tool_calls=tool_calls,
                tool_call_error=tool_call_error,
            ),
            model=self.model_name,
            usage=usage,
            finish_reason=finish_reason,
            raw_response=response,
        )