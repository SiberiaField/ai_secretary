from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from .models import ProcessingStatus


@dataclass
class MailAccountConfig:
    imap_host: str
    imap_port: int = 993

    inbox_folder: str = "INBOX"

    drafts_folder: str = "Черновики"

    folder_map: Dict[ProcessingStatus, str] = field(
        default_factory=lambda: {
            ProcessingStatus.PROCESSED: "Секретарь/Обработано",
            ProcessingStatus.NEEDS_ATTENTION: "Секретарь/Требует внимания",
        }
    )
    auto_create_folders: bool = True
