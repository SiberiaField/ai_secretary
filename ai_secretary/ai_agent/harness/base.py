from abc import ABC, abstractmethod
from ai_agent.memory import ChatMemory
from ai_agent.messages import Message, ModelResponse


class Harness(ABC):
    def __init__(self, memory: ChatMemory):
        self.memory = memory

    @abstractmethod
    def run(self, user_message: Message) -> ModelResponse:
        """
        Запускает цикл агента. 
        Возвращает финальное сообщение для пользователя.
        """
        raise NotImplementedError