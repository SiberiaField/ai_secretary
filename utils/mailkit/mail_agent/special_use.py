from __future__ import annotations
from typing import Optional


def resolve_special_folder(client, special_use_flag: bytes) -> Optional[str]:
    """
    Ищет системную папку по IMAP SPECIAL-USE атрибуту (RFC 6154),
    а не по имени. Решает проблему локализованных имён Gmail,
    флаг присваивается сервером независимо от языка интерфейса.
    """
    for flags, _delimiter, folder_name in client.list_folders():
        if special_use_flag in flags:
            return folder_name
    return None