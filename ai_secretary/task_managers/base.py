from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Type
from enum import Enum

from pydantic import BaseModel, Field


TASK_DATA_REGISTRY: Dict[str, Type[BaseModel]] = {}


def register_data_model(model_cls: Type[BaseModel]) -> Type[BaseModel]:
    """Декоратор для регистрации моделей данных задач в реестре."""
    TASK_DATA_REGISTRY[model_cls.__name__] = model_cls
    return model_cls


class TaskStatus(str, Enum):
    """Базовые статусы задачи."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(BaseModel):
    id: str
    status: TaskStatus
    data_type: str  # Имя класса модели (нужно для десериализации)
    data: Dict[str, Any] = Field(default_factory=dict) 

    def get_typed_data(self) -> BaseModel:
        """
        Возвращает данные задачи в виде строго типизированной Pydantic-модели.
        Использует реестр для поиска нужного класса.
        """
        model_cls = TASK_DATA_REGISTRY.get(self.data_type)
        if not model_cls:
            raise ValueError(f"Модель данных '{self.data_type}' не найдена в реестре. "
                             f"Убедитесь, что она зарегистрирована декоратором @register_data_model.")
        return model_cls.model_validate(self.data)


class TaskManagerError(Exception):
    """Базовое исключение для ошибок менеджера задач."""
    pass


class TaskNotFoundError(TaskManagerError):
    """Вызывается, если задача с указанным ключом не найдена."""
    pass


class TaskManager(ABC):
    """
    Абстрактный менеджер задач.
    """

    @abstractmethod
    def create_task(self, task_data: Dict[str, Any], data_type: str, initial_status: TaskStatus = TaskStatus.PENDING) -> str:
        """
        Создает новую задачу.
        :return: Уникальный ключ (ID) созданной задачи.
        """
        pass

    @abstractmethod
    def get_task(self, task_key: str) -> Task:
        """
        Получает задачу по её уникальному ключу.
        :raises TaskNotFoundError: Если задача не найдена.
        """
        pass

    @abstractmethod
    def get_tasks_by_status(self, status: TaskStatus, limit: Optional[int] = None) -> List[Task]:
        """
        Получает список задач с указанным статусом.
        """
        pass

    @abstractmethod
    def update_task(self, task_key: str, new_status: TaskStatus, update_fields: Dict[str, Any]) -> None:
        """
        Обновляет статус и поля существующей задачи.
        :raises TaskNotFoundError: Если задача не найдена.
        """
        pass

    @abstractmethod
    def delete_task(self, task_key: str) -> None:
        """
        Удаляет задачу из хранилища.
        :raises TaskNotFoundError: Если задача не найдена.
        """
        pass