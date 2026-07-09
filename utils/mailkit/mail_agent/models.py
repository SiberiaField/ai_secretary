from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import FrozenSet, List, Optional


@dataclass(frozen=True)
class EmailAddress:
    name: Optional[str]
    address: str


@dataclass(frozen=True)
class IncomingAttachment:
    """Метаданные вложения ВХОДЯЩЕГО письма. Байты - по требованию,
    через ImapMailAgent.fetch_attachment_data()."""
    filename: str
    content_type: str
    size: int


@dataclass(frozen=True)
class OutgoingAttachment:
    """Вложение для черновика - байты обязательны, т.к. их нужно
    реально прикрепить к новому MIME-сообщению."""
    filename: str
    content_type: str
    data: bytes


@dataclass
class EmailMessage:
    """Иммутабельный (по соглашению) снимок письма на момент получения."""

    message_id: str
    uid: int
    uid_validity: int
    folder: str

    in_reply_to: Optional[str]
    references: List[str]

    from_addr: EmailAddress
    to: List[EmailAddress]
    cc: List[EmailAddress]

    subject: str
    date: Optional[datetime]

    body_text: Optional[str]
    body_html: Optional[str]
    attachments: List[IncomingAttachment]

    flags: FrozenSet[str]


class ProcessingStatus(str, Enum):
    NEW = "new"
    PROCESSED = "processed"
    NEEDS_ATTENTION = "needs_attention"
    # IN_PROGRESS - на будущее


@dataclass(frozen=True)
class DraftRef:
    uid: int
    folder: str
    message_id: str
