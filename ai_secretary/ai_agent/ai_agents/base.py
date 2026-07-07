from abc import ABC, abstractmethod
from ..memory import ChatMemory
from ..messages import Message, ModelResponse


class AIAgent(ABC):
    def __init__(self, memory: ChatMemory):
        self.memory = memory

    @abstractmethod
    def run(self, user_message: Message) -> ModelResponse:
        """
        Запускает цикл агента. 
        Возвращает финальное сообщение для пользователя.
        """
        raise NotImplementedError