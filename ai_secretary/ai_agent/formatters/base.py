from __future__ import annotations

from abc import ABC, abstractmethod

from ..messages import Message


class Formatter(ABC):
    """
    Base class for prompt formatters.

    A formatter converts a conversation history into a plain text prompt.
    The resulting prompt can then be tokenized by any tokenizer.
    """

    @abstractmethod
    def __call__(
        self,
        messages: list[Message],
    ) -> str:
        """
        Build a prompt from the conversation history.

        Parameters
        ----------
        messages
            Conversation history.

        Returns
        -------
        str
            Prompt for a language model.
        """
        raise NotImplementedError