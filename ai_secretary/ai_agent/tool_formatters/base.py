from __future__ import annotations

from abc import ABC, abstractmethod

from ..tools import ToolSet


class ToolFormatter(ABC):
    """
    Base class for tools description formatters.

    A formatter converts a code description of tools into a plain text description.
    """

    @abstractmethod
    def __call__(
        self,
        tools: ToolSet,
    ) -> str:
        """
        Build a tools description from the tool set.

        Parameters
        ----------
        tools
            Set of tools.

        Returns
        -------
        str
            Description for a language model.
        """
        raise NotImplementedError