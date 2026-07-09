"""
Основная реализация поверх imapclient (ставится отдельно:
pip install imapclient). Блокирующие вызовы оборачиваются в
asyncio.to_thread, чтобы наружу модуль был async.

Класс НЕ импортирует imapclient на верхнем уровне и не завязан на его
конкретный тип — только на протокол ImapClientLike (тот небольшой набор
методов, которым реально пользуется агент). Настоящий клиент создаётся
в client_factory.py. Это позволяет тестировать всю логику агента
(fetch/draft/status-tracking) на FakeIMAPClient без установки imapclient.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, Protocol

from .config import MailAccountConfig
from .exceptions import DraftError
from .mime_utils import build_reply_mime, extract_attachment_bytes, parse_message, rebuild_draft_mime, build_new_mime
from .models import DraftRef, EmailMessage, OutgoingAttachment, ProcessingStatus
from .status_tracker import FolderStatusTracker, StatusTracker


class ImapClientLike(Protocol):
    """Минимум методов imapclient.IMAPClient, которым пользуется агент —
    именно этот протокол подставляется в тестах через FakeIMAPClient."""

    def select_folder(self, folder: str, readonly: bool = False) -> dict: ...
    def search(self, criteria: List[str]) -> List[int]: ...
    def fetch(self, messages: List[int], data: List[str]) -> Dict[int, dict]: ...
    def append(self, folder: str, msg: bytes, flags: tuple = (), msg_time=None) -> Any: ...
    def move(self, messages: List[int], folder: str) -> Any: ...
    def add_flags(self, messages: List[int], flags: List[str]) -> Any: ...
    def remove_flags(self, messages: List[int], flags: List[str]) -> Any: ...
    def folder_exists(self, folder: str) -> bool: ...
    def create_folder(self, folder: str) -> Any: ...
    def delete_messages(self, messages: List[int]) -> Any: ...
    def expunge(self) -> Any: ...
    def logout(self) -> Any: ...


_APPENDUID_RE = re.compile(rb"APPENDUID \d+ (\d+)")


class ImapMailAgent:
    def __init__(
        self,
        client: ImapClientLike,
        config: MailAccountConfig,
        from_address: str,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._client = client
        self._config = config
        self._from_address = from_address
        self._log = logger or logging.getLogger(__name__)
        self._status_tracker: Optional[StatusTracker] = None

    # TASK_ID_HEADER = "X-AISecretary-Task-Id"

    def attach_status_tracker(self, tracker: StatusTracker) -> None:
        """StatusTracker подключается отдельным шагом (не через
        конструктор), т.к. FolderStatusTracker сам зависит от агента
        (ему нужны ensure_folder/move_message) — так избегаем
        циклической инициализации. См. create_folder_based_agent()."""
        self._status_tracker = tracker

    def _require_tracker(self) -> StatusTracker:
        if self._status_tracker is None:
            raise RuntimeError(
                "StatusTracker не подключён — вызовите attach_status_tracker() "
                "или создайте агента через create_folder_based_agent()."
            )
        return self._status_tracker

    async def _run(self, func, *args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)

    # ---- 1. получение писем -------------------------------------------------

    async def fetch_new_messages(
        self, folder: Optional[str] = None, limit: Optional[int] = None
    ) -> List[EmailMessage]:
        folder = folder or self._config.inbox_folder
        # readonly=True -> сервер сам не проставит \Seen при выборе папки
        folder_status = await self._run(self._client.select_folder, folder, readonly=True)
        uid_validity = folder_status.get(b"UIDVALIDITY", 0)

        uids = sorted(await self._run(self._client.search, ["ALL"]))
        if limit:
            uids = uids[:limit]
        if not uids:
            return []

        fetched = await self._run(self._client.fetch, uids, ["BODY.PEEK[]", "FLAGS"])

        messages: List[EmailMessage] = []
        for uid in uids:
            data = fetched.get(uid)
            if not data:
                continue
            raw = data[b"BODY[]"]
            flags = frozenset(
                f.decode() if isinstance(f, bytes) else f for f in data.get(b"FLAGS", ())
            )
            messages.append(
                parse_message(raw, uid=uid, uid_validity=uid_validity, folder=folder, flags=flags)
            )

        return await self._require_tracker().filter_new(messages)

    async def fetch_attachment_data(self, message: EmailMessage, filename: str) -> bytes:
        await self._run(self._client.select_folder, message.folder, readonly=True)
        data = await self._run(self._client.fetch, [message.uid], ["BODY.PEEK[]"])
        raw = data[message.uid][b"BODY[]"]
        return extract_attachment_bytes(raw, filename)

    async def mark_processed(self, message: EmailMessage, status: ProcessingStatus) -> None:
        await self._require_tracker().record_status(message, status)

    # ---- 2. черновики ---------------------------------------------------------

    async def save_draft(
        self,
        in_reply_to: EmailMessage,
        body_html: str,
        body_text: Optional[str] = None,
        subject: Optional[str] = None,
        attachments: Optional[List[OutgoingAttachment]] = None,
    ) -> DraftRef:
        mime_bytes, message_id = build_reply_mime(
            in_reply_to=in_reply_to,
            from_address=self._from_address,
            body_html=body_html,
            body_text=body_text,
            subject=subject,
            attachments=attachments,
        )
        try:
            result = await self._run(
                self._client.append, self._config.drafts_folder, mime_bytes, flags=(r"\Draft",)
            )
        except Exception as exc:
            raise DraftError(f"Не удалось сохранить черновик: {exc}") from exc

        uid = self._extract_appended_uid(result)
        return DraftRef(uid=uid, folder=self._config.drafts_folder, message_id=message_id)
    
    async def save_new_draft(
        self,
        to_address: str,
        subject: str,
        body_html: str,
        body_text: Optional[str] = None,
        attachments: Optional[List[OutgoingAttachment]] = None,
        # task_id: Optional[str] = None,
    ) -> DraftRef:
        # extra_headers = {self.TASK_ID_HEADER: task_id} if task_id else None
        mime_bytes, message_id = build_new_mime(
            from_address=self._from_address,
            to_address=to_address,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            attachments=attachments,
            # extra_headers=extra_headers,
        )
        try:
            result = await self._run(
                self._client.append, self._config.drafts_folder, mime_bytes, flags=(r"\Draft",)
            )
        except Exception as exc:
            raise DraftError(f"Не удалось сохранить черновик: {exc}") from exc

        uid = self._extract_appended_uid(result)
        return DraftRef(uid=uid, folder=self._config.drafts_folder, message_id=message_id)

    async def update_draft(
        self,
        draft_ref: DraftRef,
        body_html: str,
        body_text: Optional[str] = None,
    ) -> DraftRef:
        await self._run(self._client.select_folder, draft_ref.folder)
        old_data = await self._run(self._client.fetch, [draft_ref.uid], ["BODY.PEEK[]"])
        old_raw = old_data[draft_ref.uid][b"BODY[]"]

        new_mime, message_id = rebuild_draft_mime(old_raw=old_raw, body_html=body_html, body_text=body_text)

        await self.delete_draft(draft_ref)
        try:
            result = await self._run(
                self._client.append, self._config.drafts_folder, new_mime, flags=(r"\Draft",)
            )
        except Exception as exc:
            raise DraftError(f"Не удалось пересохранить черновик: {exc}") from exc

        uid = self._extract_appended_uid(result)
        return DraftRef(uid=uid, folder=self._config.drafts_folder, message_id=message_id)

    async def delete_draft(self, draft_ref: DraftRef) -> None:
        await self._run(self._client.select_folder, draft_ref.folder)
        await self._run(self._client.delete_messages, [draft_ref.uid])
        await self._run(self._client.expunge)

    @staticmethod
    def _extract_appended_uid(append_result: Any) -> int:
        # При поддержке сервером UIDPLUS (Gmail поддерживает) APPEND
        # возвращает ответ вида "...[APPENDUID 38505 3955]..." — парсим.
        # TODO(ограничение MVP): если сервер не поддерживает UIDPLUS,
        # нужен fallback через SEARCH по Message-ID сразу после APPEND —
        # не реализовано, т.к. не смог проверить на реальном сервере.
        raw = append_result if isinstance(append_result, bytes) else bytes(str(append_result), "utf-8")
        match = _APPENDUID_RE.search(raw)
        return int(match.group(1)) if match else -1

    # ---- FolderOps: используется StatusTracker'ами ----------------------------

    async def ensure_folder(self, folder: str) -> None:
        exists = await self._run(self._client.folder_exists, folder)
        if not exists:
            await self._run(self._client.create_folder, folder)

    async def move_message(self, message: EmailMessage, target_folder: str) -> None:
        await self._run(self._client.select_folder, message.folder)
        await self._run(self._client.move, [message.uid], target_folder)

    async def set_flag(self, message: EmailMessage, flag: str) -> None:
        await self._run(self._client.select_folder, message.folder)
        await self._run(self._client.add_flags, [message.uid], [flag])

    async def remove_flag(self, message: EmailMessage, flag: str) -> None:
        await self._run(self._client.select_folder, message.folder)
        await self._run(self._client.remove_flags, [message.uid], [flag])


def create_folder_based_agent(
    client: ImapClientLike,
    config: MailAccountConfig,
    from_address: str,
    logger: Optional[logging.Logger] = None,
) -> ImapMailAgent:
    """Основной способ создать агента для MVP: статус = расположение
    письма в папках, отдельная БД не нужна."""
    agent = ImapMailAgent(client=client, config=config, from_address=from_address, logger=logger)
    agent.attach_status_tracker(
        FolderStatusTracker(agent, config.folder_map, config.auto_create_folders)
    )
    return agent
