import uuid
import os
import tempfile
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional

from task_managers.base import Task, TaskManager, TaskStatus, TaskNotFoundError


class FileTaskManager(TaskManager):
    """
    Реализация TaskManager, использующая файловую систему как хранилище.
    Статусы = подпапки. Задачи = JSON-файлы с именем <id>.json.
    """

    def __init__(self, root_path: str | Path):
        """
        :param root_path: Путь к корневой папке, где будут храниться папки статусов.
        """
        self.root_path = Path(root_path).resolve()
        
        self.root_path.mkdir(parents=True, exist_ok=True)
        for status in TaskStatus:
            self._get_folder_for_status(status).mkdir(parents=True, exist_ok=True)

    def _get_folder_for_status(self, status: TaskStatus) -> Path:
        """Возвращает путь к папке для заданного статуса."""
        return self.root_path / status.value

    def _find_task_file(self, task_key: str) -> Optional[Path]:
        """
        Ищет файл <task_key>.json во всех папках статусов.
        Возвращает путь к файлу или None, если не найден.
        """
        filename = f"{task_key}.json"
        for status in TaskStatus:
            file_path = self._get_folder_for_status(status) / filename
            if file_path.exists():
                return file_path
        return None

    async def _read_task(self, file_path: Path) -> Task:
        """Читает и десериализует задачу из JSON-файла."""
        with open(file_path, 'r', encoding='utf-8') as f:
            json_str = await asyncio.to_thread(f.read)
        return Task.model_validate_json(json_str)

    def _write_task(self, task: Task, file_path: Path) -> None:
        """
        Атомарно записывает задачу в JSON-файл.
        Использует временный файл + os.replace для защиты от сбоев.
        """
        json_str = task.model_dump_json(indent=2)
        
        fd, tmp_path = tempfile.mkstemp(
            dir=file_path.parent, 
            prefix=f".{task.id}_", 
            suffix=".tmp"
        )
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(json_str)
            os.replace(tmp_path, file_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    # --- Реализация абстрактных методов ---

    async def create_task(self, task_data: Dict[str, Any], data_type: str, initial_status: TaskStatus = TaskStatus.PENDING) -> str:
        task_id = str(uuid.uuid4())
        
        data_copy = task_data.copy()
        
        task = Task(
            id=task_id,
            status=initial_status,
            data_type=data_type,
            data=data_copy
        )
        
        file_path = self._get_folder_for_status(initial_status) / f"{task_id}.json"
        await asyncio.to_thread(self._write_task, task=task, file_path=file_path)
        
        return task_id

    async def get_task(self, task_key: str) -> Task:
        file_path = await asyncio.to_thread(self._find_task_file, task_key=task_key)
        
        if not file_path:
            raise TaskNotFoundError(f"Задача {task_key} не найдена")
            
        task = await self._read_task(file_path)
        
        folder_status = TaskStatus(file_path.parent.name)
        if task.status != folder_status:
            task.status = folder_status
            
        return task

    async def get_tasks_by_status(self, status: TaskStatus, limit: Optional[int] = None) -> List[Task]:
        folder = self._get_folder_for_status(status)
        tasks: List[Task] = []
        
        json_files = sorted(
            folder.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        if limit is not None:
            json_files = json_files[:limit]
            
        for file_path in json_files:
            try:
                task = await self._read_task(file_path)
                task.status = status  # Гарантируем статус от папки
                tasks.append(task)
            except Exception as e:
                print(f"Warning: не удалось прочитать задачу {file_path.name}: {e}")
                
        return tasks

    async def update_task(self, task_key: str, new_status: TaskStatus, update_fields: Dict[str, Any] | None) -> None:
        old_file_path = await asyncio.to_thread(self._find_task_file, task_key=task_key)
        
        if not old_file_path:
            raise TaskNotFoundError(f"Задача {task_key} не найдена для обновления")
            
        old_task = await self._read_task(old_file_path)
        
        new_data = old_task.data.copy()
        if update_fields:
            new_data.update(update_fields)
        
        new_task = Task(
            id=old_task.id,
            status=new_status,
            data_type=old_task.data_type,
            data=new_data
        )
        
        old_file_path.unlink()
        
        new_file_path = self._get_folder_for_status(new_status) / f"{task_key}.json"
        await asyncio.to_thread(self._write_task, task=new_task, file_path=new_file_path)

    async def delete_task(self, task_key: str) -> None:
        file_path = await asyncio.to_thread(self._find_task_file, task_key=task_key)
        
        if not file_path:
            raise TaskNotFoundError(f"Задача {task_key} не найдена для удаления")
            
        file_path.unlink()