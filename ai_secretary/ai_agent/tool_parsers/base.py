from __future__ import annotations

from typing import List, Optional
from abc import ABC, abstractmethod

from ..messages import ToolCall


class ToolParsingError(Exception):
    """
    Исключение, возникающее при ошибках парсинга вызовов инструментов.
    
    Может содержать либо текстовое сообщение об ошибке, либо оригинальное
    исключение, которое привело к ошибке парсинга.
    """
    
    def __init__(
        self, 
        message: str, 
        original_error: Optional[Exception] = None
    ):
        """
        Parameters
        ----------
        message : str
            Текстовое описание ошибки.
        original_error : Exception, optional
            Оригинальное исключение, если ошибка возникла из-за него.
        """
        self.message = message
        self.original_error = original_error
        
        if original_error is not None:
            full_message = f"{message}: {original_error}"
        else:
            full_message = message
            
        super().__init__(full_message)


class ToolParser(ABC):
    """
    Base class for tools parsers.

    A parsers converts a text output of model into a list of tool calls.
    """

    @abstractmethod
    def __call__(
        self,
        content: str,
    ) -> List[ToolCall] | str:
        """
        Extract tool calls from a raw assistant output.

        Parameters
        ----------
        content
            Raw assistant output.

        Returns
        -------
        List[ToolCall]
            List of tool calls.
        """
        raise NotImplementedError