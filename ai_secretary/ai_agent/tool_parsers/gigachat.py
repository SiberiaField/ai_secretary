from __future__ import annotations

import json
from typing import List

from .base import ToolParser, ToolParsingError
from ..messages import ToolCall


class GigaChatParser(ToolParser):
    FUNCTION_CALL_TOKEN = "<|function_call|>"

    def __call__(
        self,
        content: str,
    ) -> List[ToolCall] | str:
        content = content.strip()

        if self.FUNCTION_CALL_TOKEN not in content:
            return []

        _, function_part = content.split(self.FUNCTION_CALL_TOKEN, 1)

        function_part = function_part.strip()

        for suffix in ("</s>", "<s>"):
            if function_part.endswith(suffix):
                function_part = function_part[: -len(suffix)].strip()

        try:
            raw_tool_call = json.loads(function_part)
        except json.JSONDecodeError as e:
            raise ToolParsingError(
                "Ошибка при парсинге JSON для function_call",
                original_error=e
            ) from e

        if not (
            isinstance(raw_tool_call, dict)
            and "name" in raw_tool_call
            and "arguments" in raw_tool_call
            and isinstance(raw_tool_call["arguments"], dict)
        ):
            raise ToolParsingError(
                "function_call имеет неправильную структуру: потеряно поле 'name' или 'arguments', "
                "или 'arguments' не является словарём."
            )

        return [ToolCall(None, raw_tool_call["name"], raw_tool_call["arguments"])]