import imaplib
import email
from email.message import Message
from email.header import Header
import uuid
from typing import Dict, Any, List, Optional

from task_managers.base import Task, TaskManager, TaskStatus, TaskNotFoundError


class IMAPTaskManager(TaskManager):
    """
    Реализация TaskManager, использующая IMAP-сервер как хранилище.
    Статусы = Папки. Задачи = Письма с JSON-телом и Subject="<id>.json".
    """

    def __init__(self, host: str, username: str, password: str, storage_folder: str, port: int = 993, status_folder_map: Optional[Dict[TaskStatus, str]] = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        
        # Маппинг статусов на имена папок. 
        # Если не передан, используются дефолтные значения.
        self.status_folder_map = status_folder_map or {
            TaskStatus.PENDING: "Pending",
            TaskStatus.IN_PROGRESS: "In_Progress",
            TaskStatus.COMPLETED: "Completed",
            TaskStatus.FAILED: "Failed",
            TaskStatus.CANCELLED: "Cancelled"
        }
        
        self.mail = None
        self._connect()
        self._ensure_folders_exist()

    def _connect(self):
        """Подключение к серверу и авторизация."""
        try:
            self.mail = imaplib.IMAP4_SSL(self.host, self.port)
            self.mail.login(self.username, self.password)
        except Exception as e:
            raise ConnectionError(f"Не удалось подключиться к IMAP: {e}")

    def _ensure_folders_exist(self):
        """Создает папки для статусов, если их еще нет."""
        existing_folders = [f.decode() if isinstance(f, bytes) else f for f in self.mail.list()[1]]
        for status, folder_name in self.status_folder_map.items():
            # Проверка наличия папки (упрощенная)
            if not any(folder_name in f for f in existing_folders):
                try:
                    self.mail.create(folder_name)
                    self.mail.subscribe(folder_name)
                except Exception as e:
                    print(f"Warning: Could not create folder {folder_name}: {e}")

    def _get_folder_by_status(self, status: TaskStatus) -> str:
        return self.status_folder_map.get(status, "INBOX")

    def _create_email_message(self, task: Task) -> Message:
        """Создает MIME-сообщение из объекта Task."""
        msg = Message()
        # "Имя файла" в Subject
        msg['Subject'] = Header(f"{task.id}.json", 'utf-8')
        msg['From'] = self.username
        msg['To'] = self.username # Отправляем сами себе
        
        # Полезная нагрузка - полный JSON задачи
        json_data = task.model_dump_json()
        msg.set_payload(json_data, charset='utf-8')
        
        return msg

    def _find_task_message(self, task_key: str) -> tuple[Optional[str], Optional[str], Optional[bytes]]:
        """
        Ищет письмо с Subject="<task_key>.json" во всех папках статусов.
        Возвращает (folder_name, uid, raw_email_bytes).
        """
        target_subject = f"{task_key}.json"
        
        for status, folder in self.status_folder_map.items():
            self.mail.select(folder)
            # Ищем по заголовку Subject
            status, data = self.mail.search(None, f'SUBJECT "{target_subject}"')
            
            if status == 'OK' and data[0]:
                ids = data[0].split()
                if ids:
                    # Берем первое совпадение
                    mail_id = ids[-1] 
                    status, msg_data = self.mail.fetch(mail_id, '(RFC822)')
                    if status == 'OK':
                        raw_email = msg_data[0][1]
                        return folder, mail_id, raw_email
        
        return None, None, None

    def _parse_email_to_task(self, raw_email: bytes) -> Task:
        """Парсит сырое письмо обратно в объект Task."""
        msg = email.message_from_bytes(raw_email)
        
        # Получаем тело письма
        payload = msg.get_payload(decode=True)
        if not payload:
            raise ValueError("Пустое тело письма")
            
        json_str = payload.decode('utf-8')
        
        # Pydantic сам распарсит JSON и валидирует данные
        return Task.model_validate_json(json_str)

    # --- Реализация абстрактных методов ---

    def create_task(self, task_data: Dict[str, Any], data_type: str, initial_status: TaskStatus = TaskStatus.PENDING) -> str:
        task_id = str(uuid.uuid4())     
        
        task = Task(
            id=task_id, 
            status=initial_status, 
            data_type=data_type,
            data=task_data
        )
        
        msg = self._create_email_message(task)
        folder = self._get_folder_by_status(initial_status)
        
        self.mail.select(folder)
        # APPEND добавляет письмо в папку
        self.mail.append(folder, None, None, msg.as_bytes())
        
        return task_id

    def get_task(self, task_key: str) -> Task:
        folder, mail_id, raw_email = self._find_task_message(task_key)
        
        if not raw_email:
            raise TaskNotFoundError(f"Задача {task_key} не найдена")
            
        task = self._parse_email_to_task(raw_email)
        
        # Синхронизация статуса: Статус в папке приоритетнее, чем в JSON
        # (на случай, если письмо переместили вручную)
        current_folder_status = next((s for s, f in self.status_folder_map.items() if f == folder), None)
        if current_folder_status and task.status != current_folder_status:
            task.status = current_folder_status
            
        return task

    def get_tasks_by_status(self, status: TaskStatus, limit: Optional[int] = None) -> List[Task]:
        folder = self._get_folder_by_status(status)
        self.mail.select(folder)
        
        status, data = self.mail.search(None, 'ALL')
        tasks = []
        
        if status == 'OK' and data[0]:
            ids = data[0].split()
            # Если есть лимит, берем только последние (или первые, зависит от сортировки)
            if limit:
                ids = ids[-limit:] 
                
            for mail_id in ids:
                status, msg_data = self.mail.fetch(mail_id, '(RFC822)')
                if status == 'OK':
                    raw_email = msg_data[0][1]
                    try:
                        task = self._parse_email_to_task(raw_email)
                        task.status = status # Гарантируем статус от папки
                        tasks.append(task)
                    except Exception as e:
                        print(f"Error parsing task {mail_id}: {e}")
                        
        return tasks

    def update_task(self, task_key: str, new_status: TaskStatus, update_fields: Dict[str, Any]) -> None:
        # 1. Найти старую задачу
        old_folder, old_mail_id, raw_email = self._find_task_message(task_key)
        if not raw_email:
            raise TaskNotFoundError(f"Задача {task_key} не найдена для обновления")
            
        old_task = self._parse_email_to_task(raw_email)
        
        # 2. Обновить данные
        # Pydantic модели иммутабельны по умолчанию, создаем новую
        new_data = old_task.data.copy()
        new_data.update(update_fields)
        
        new_task = Task(
            id=old_task.id,
            status=new_status,
            data_type=old_task.data_type,
            data=new_data
        )
        
        # 3. Удалить старую (IMAP не умеет редактировать)
        self.mail.select(old_folder)
        self.mail.store(old_mail_id, '+FLAGS', '\\Deleted')
        self.mail.expunge()
        
        # 4. Создать новую в папке нового статуса
        msg = self._create_email_message(new_task)
        new_folder = self._get_folder_by_status(new_status)
        self.mail.select(new_folder)
        self.mail.append(new_folder, None, None, msg.as_bytes())

    def delete_task(self, task_key: str) -> None:
        folder, mail_id, _ = self._find_task_message(task_key)
        
        if not mail_id:
            raise TaskNotFoundError(f"Задача {task_key} не найдена для удаления")
            
        self.mail.select(folder)
        self.mail.store(mail_id, '+FLAGS', '\\Deleted')
        self.mail.expunge()

    def __del__(self):
        """Корректное отключение при уничтожении объекта."""
        if hasattr(self, 'mail') and self.mail:
            try:
                self.mail.close()
                self.mail.logout()
            except Exception:
                pass