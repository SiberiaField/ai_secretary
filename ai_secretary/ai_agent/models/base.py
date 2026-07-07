from __future__ import annotations

from abc import ABC, abstractmethod

from ..messages import Message, ModelResponse
from ..tools import ToolSet


class Model(ABC):
    """
    Base interface for all language models.

    Every model implementation should accept a conversation history and
    return a structured response.
    """

    @abstractmethod
    def __call__(
        self,
        messages: list[Message],
        tools: ToolSet,
        **kwargs,
    ) -> ModelResponse:
        """
        Generate the next assistant message.

        Parameters
        ----------
        messages
            Conversation history.
        tools
            Set of available tools.
        **kwargs
            Provider-specific generation parameters.

        Returns
        -------
        ModelResponse
        """
        raise NotImplementedError