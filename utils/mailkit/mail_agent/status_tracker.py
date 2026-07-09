from __future__ import annotations

from typing import Dict, List, Protocol

from .models import EmailMessage, ProcessingStatus


class FolderOps(Protocol):
    """Минимум, который нужен трекеру статуса от ImapMailAgent.
    Выделено отдельным протоколом (а не завязано на конкретный класс
    агента), чтобы не тащить циклическую зависимость и чтобы трекер
    можно было тестировать отдельно при желании."""

    async def ensure_folder(self, folder: str) -> None: ...
    async def move_message(self, message: EmailMessage, target_folder: str) -> None: ...
    async def set_flag(self, message: EmailMessage, flag: str) -> None: ...
    async def remove_flag(self, message: EmailMessage, flag: str) -> None: ...


class StatusTracker(Protocol):
    """Отвечает на вопрос "что уже обработано" и фиксирует новый статус.
    Обе части (2) визуальная пометка и (4) хранение статуса из исходного
    ТЗ у folder-based реализации схлопываются в одно действие (move)."""

    async def filter_new(self, candidates: List[EmailMessage]) -> List[EmailMessage]: ...
    async def record_status(self, message: EmailMessage, status: ProcessingStatus) -> None: ...


class FolderStatusTracker:
    """Статус = расположение письма в почтовых папках/лейблах. Ничего,
    кроме самого IMAP-сервера, не хранит - секретарь видит "Требует
    внимания" прямо в клиенте как обычную папку с непрочитанными.

    fetch_new_messages() у агента и так читает конкретную "рабочую"
    папку (обычно INBOX) - если письмо обработано, его там физически
    больше нет, так что filter_new() здесь - identity-операция.
    """

    def __init__(
        self,
        folder_ops: FolderOps,
        folder_map: Dict[ProcessingStatus, str],
        auto_create: bool = True,
    ) -> None:
        self._ops = folder_ops
        self._folder_map = folder_map
        self._auto_create = auto_create
        self._ensured: set = set()

    async def filter_new(self, candidates: List[EmailMessage]) -> List[EmailMessage]:
        return list(candidates)

    async def record_status(self, message: EmailMessage, status: ProcessingStatus) -> None:
        target = self._folder_map.get(status)
        if target is None:
            return  # NEW и любые не замапленные статусы — no-op в MVP
        if self._auto_create and target not in self._ensured:
            await self._ops.ensure_folder(target)
            self._ensured.add(target)
        await self._ops.move_message(message, target)


class PostgresStatusTracker:
    """Альтернатива: статус хранится в Postgres, письма остаются в INBOX
    (папки/лейблы не трогаем). Для видимости NEEDS_ATTENTION дополнительно
    ставит \\Flagged через folder_ops.
    """

    def __init__(self, dsn: str, folder_ops: FolderOps) -> None:
        self._dsn = dsn
        self._ops = folder_ops
        self._pool = None

    async def connect(self) -> None:
        import asyncpg  # ленивый импорт — не требуется, если бэкенд не используется

        self._pool = await asyncpg.create_pool(dsn=self._dsn)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mail_agent_status (
                    message_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    folder TEXT NOT NULL,
                    uid INTEGER NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

    async def filter_new(self, candidates: List[EmailMessage]) -> List[EmailMessage]:
        if not candidates:
            return []
        ids = [m.message_id for m in candidates]
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT message_id FROM mail_agent_status "
                "WHERE message_id = ANY($1) AND status = 'processed'",
                ids,
            )
        processed_ids = {r["message_id"] for r in rows}
        return [m for m in candidates if m.message_id not in processed_ids]

    async def record_status(self, message: EmailMessage, status: ProcessingStatus) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO mail_agent_status (message_id, status, folder, uid)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (message_id) DO UPDATE
                    SET status = EXCLUDED.status, updated_at = now()
                """,
                message.message_id, status.value, message.folder, message.uid,
            )
        if status == ProcessingStatus.NEEDS_ATTENTION:
            await self._ops.set_flag(message, r"\Flagged")
        elif status == ProcessingStatus.PROCESSED:
            await self._ops.remove_flag(message, r"\Flagged")
