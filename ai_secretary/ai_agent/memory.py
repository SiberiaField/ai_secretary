from typing import List, Optional
from .messages import Message, Role


class ChatMemory:
    """Управляет кратковременной памятью (историей сообщений)."""
    
    def __init__(self, system_prompt: str, max_messages: Optional[int] = None):
        self.system_message = Message(Role.SYSTEM, system_prompt)
        self.messages: List[Message] = []
        self.max_messages = max_messages

    def add(self, message: Message):
        self.messages.append(message)
        self._trim_history()

    def get_context(self) -> List[Message]:
        """Возвращает готовый контекст для отправки в модель."""
        return [self.system_message] + self.messages

    def _trim_history(self):
        """Обрезает историю, если превышен лимит сообщений."""
        if self.max_messages and len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
            
    def clear(self):
        self.messages = []