from __future__ import annotations

from abc import ABC, abstractmethod

from ..messages import Message, ModelResponse


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
        **kwargs,
    ) -> ModelResponse:
        """
        Generate the next assistant message.

        Parameters
        ----------
        messages
            Conversation history.
        **kwargs
            Provider-specific generation parameters.

        Returns
        -------
        ModelResponse
        """
        raise NotImplementedError