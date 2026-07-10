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
    
    Потокобезопасность обеспечивается через asyncio.Lock для каждой задачи.
    """

    def __init__(self, root_path: str | Path):
        self.root_path = Path(root_path).resolve()
        
        self._locks_guard = asyncio.Lock()
        self._task_locks: Dict[str, asyncio.Lock] = {}
        
        self.root_path.mkdir(parents=True, exist_ok=True)
        for status in TaskStatus:
            self._get_folder_for_status(status).mkdir(parents=True, exist_ok=True)

    def _get_folder_for_status(self, status: TaskStatus) -> Path:
        return self.root_path / status.value

    async def _get_task_lock(self, task_key: str) -> asyncio.Lock:
        """Лениво получает или создаёт блокировку для конкретной задачи."""
        async with self._locks_guard:
            lock = self._task_locks.get(task_key)
            if lock is None:
                lock = asyncio.Lock()
                self._task_locks[task_key] = lock
            return lock

    async def _release_task_lock(self, task_key: str) -> None:
        """
        Удаляет блокировку из словаря, если она не используется.
        Вызывается после завершения работы с задачей, чтобы не накапливать память.
        """
        async with self._locks_guard:
            lock = self._task_locks.get(task_key)
            if lock is not None and not lock.locked():
                self._task_locks.pop(task_key, None)

    def _find_task_file_sync(self, task_key: str) -> Optional[Path]:
        """
        Синхронная версия поиска файла задачи.
        Ищет файл <task_key>.json во всех папках статусов.
        """
        filename = f"{task_key}.json"
        for status in TaskStatus:
            file_path = self._get_folder_for_status(status) / filename
            if file_path.exists():
                return file_path
        return None

    async def _read_task(self, file_path: Path) -> Task:
        """Читает и десериализует задачу из JSON-файла."""
        def _read() -> str:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        
        try:
            json_str = await asyncio.to_thread(_read)
        except FileNotFoundError:
            raise TaskNotFoundError(f"Файл задачи исчез: {file_path}")
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
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            raise

    async def _safe_unlink(self, path: Path) -> None:
        """Безопасное удаление файла — игнорирует отсутствие файла."""
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError:
            pass

    # --- Реализация абстрактных методов ---

    async def create_task(
        self,
        task_data: Dict[str, Any],
        data_type: str,
        initial_status: TaskStatus = TaskStatus.PENDING,
    ) -> str:
        task_id = str(uuid.uuid4())
        
        task = Task(
            id=task_id,
            status=initial_status,
            data_type=data_type,
            data=task_data.copy(),
        )
        
        file_path = self._get_folder_for_status(initial_status) / f"{task_id}.json"
        await asyncio.to_thread(self._write_task, task=task, file_path=file_path)
        
        return task_id

    async def get_task(self, task_key: str) -> Task:
        lock = await self._get_task_lock(task_key)
        try:
            async with lock:
                file_path = await asyncio.to_thread(
                    self._find_task_file_sync, task_key=task_key
                )
                if not file_path:
                    raise TaskNotFoundError(f"Задача {task_key} не найдена")
                
                task = await self._read_task(file_path)
                
                folder_status = TaskStatus(file_path.parent.name)
                task.status = folder_status
                return task
        finally:
            await self._release_task_lock(task_key)

    async def get_tasks_by_status(
        self, status: TaskStatus, limit: Optional[int] = None
    ) -> List[Task]:
        folder = self._get_folder_for_status(status)
        tasks: List[Task] = []
        
        def _collect_files() -> List[tuple[Path, float]]:
            result = []
            try:
                entries = list(folder.glob("*.json"))
            except OSError:
                return result
            for p in entries:
                try:
                    result.append((p, p.stat().st_mtime))
                except FileNotFoundError:
                    continue
            return result
        
        files_with_mtime = await asyncio.to_thread(_collect_files)
        files_with_mtime.sort(key=lambda x: x[1], reverse=True)
        
        if limit is not None:
            files_with_mtime = files_with_mtime[:limit]
        
        for file_path, _ in files_with_mtime:
            try:
                task = await self._read_task(file_path)
                task.status = status
                tasks.append(task)
            except TaskNotFoundError:
                continue
            except Exception as e:
                print(f"Warning: не удалось прочитать задачу {file_path.name}: {e}")
                
        return tasks

    async def update_task(
        self,
        task_key: str,
        new_status: TaskStatus,
        update_fields: Dict[str, Any] | None,
    ) -> None:
        lock = await self._get_task_lock(task_key)
        try:
            async with lock:
                old_file_path = await asyncio.to_thread(
                    self._find_task_file_sync, task_key=task_key
                )
                if not old_file_path:
                    raise TaskNotFoundError(
                        f"Задача {task_key} не найдена для обновления"
                    )
                
                old_task = await self._read_task(old_file_path)
                
                new_data = old_task.data.copy()
                if update_fields:
                    new_data.update(update_fields)
                
                new_task = Task(
                    id=old_task.id,
                    status=new_status,
                    data_type=old_task.data_type,
                    data=new_data,
                )
                
                new_file_path = (
                    self._get_folder_for_status(new_status) / f"{task_key}.json"
                )
                
                await asyncio.to_thread(
                    self._write_task, task=new_task, file_path=new_file_path
                )
                
                if old_file_path.resolve() != new_file_path.resolve():
                    await self._safe_unlink(old_file_path)
        finally:
            await self._release_task_lock(task_key)

    async def delete_task(self, task_key: str) -> None:
        lock = await self._get_task_lock(task_key)
        try:
            async with lock:
                file_path = await asyncio.to_thread(
                    self._find_task_file_sync, task_key=task_key
                )
                if not file_path:
                    raise TaskNotFoundError(
                        f"Задача {task_key} не найдена для удаления"
                    )
                await self._safe_unlink(file_path)
        finally:
            await self._release_task_lock(task_key)