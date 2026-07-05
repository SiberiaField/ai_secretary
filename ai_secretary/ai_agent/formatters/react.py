from __future__ import annotations

from .base import Formatter
from ..messages import Message, Role


class ReActFormatter(Formatter):
    """
    Formats conversation history into a ReAct prompt.

    The formatter is intentionally model-agnostic and does not depend on
    any tokenizer or provider.
    """

    def __init__(
        self,
        system_prompt: str,
    ):
        self.system_prompt = system_prompt.strip()

    def __call__(
        self,
        messages: list[Message],
    ) -> str:

        parts: list[str] = [self.system_prompt, ""]

        for message in messages:

            match message.role:

                case Role.SYSTEM:
                    parts.append(f"System: {message.content}")

                case Role.USER:
                    parts.append(f"User: {message.content}")

                case Role.ASSISTANT:
                    parts.append(f"Assistant: {message.content}")

                case Role.TOOL:
                    parts.append(f"Observation: {message.content}")

        parts.append("")
        parts.append("Assistant:")

        return "\n".join(parts)