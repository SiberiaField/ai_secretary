"""
Мини-имитация imapclient.IMAPClient в памяти — ровно те методы, которыми
пользуется ImapMailAgent (см. ImapClientLike в agent.py). Позволяет
тестировать всю логику модуля (fetch/save_draft/status tracking) без
сети и без установки imapclient.
"""
from __future__ import annotations

from typing import Dict, Optional


class FakeIMAPClient:
    def __init__(self) -> None:
        # folder -> {uid: {"raw": bytes, "flags": set[str]}}
        self.folders: Dict[str, Dict[int, dict]] = {"INBOX": {}, "Drafts": {}}
        self._next_uid = 1
        self._selected: Optional[str] = None

    # -- вспомогательное для тестов (не часть ImapClientLike) --------------

    def seed_message(self, folder: str, raw: bytes, flags=()) -> int:
        uid = self._next_uid
        self._next_uid += 1
        self.folders.setdefault(folder, {})[uid] = {"raw": raw, "flags": set(flags)}
        return uid

    # -- методы, которые реально дёргает ImapMailAgent ----------------------

    def select_folder(self, folder: str, readonly: bool = False) -> dict:
        self.folders.setdefault(folder, {})
        self._selected = folder
        return {b"UIDVALIDITY": 1}

    def search(self, criteria):
        return list(self.folders[self._selected].keys())

    def fetch(self, messages, data):
        result = {}
        for uid in messages:
            entry = self.folders[self._selected].get(uid)
            if entry is None:
                continue
            result[uid] = {
                b"BODY[]": entry["raw"],
                b"FLAGS": tuple(entry["flags"]),
            }
        return result

    def append(self, folder, msg, flags=(), msg_time=None):
        uid = self._next_uid
        self._next_uid += 1
        self.folders.setdefault(folder, {})[uid] = {"raw": msg, "flags": set(flags)}
        return f"OK [APPENDUID 1 {uid}] APPEND completed".encode()

    def move(self, messages, folder):
        for uid in messages:
            entry = self.folders[self._selected].pop(uid)
            self.folders.setdefault(folder, {})[uid] = entry

    def add_flags(self, messages, flags):
        for uid in messages:
            self.folders[self._selected][uid]["flags"].update(flags)

    def remove_flags(self, messages, flags):
        for uid in messages:
            self.folders[self._selected][uid]["flags"].difference_update(flags)

    def folder_exists(self, folder):
        return folder in self.folders

    def create_folder(self, folder):
        self.folders.setdefault(folder, {})

    def delete_messages(self, messages):
        for uid in messages:
            self.folders[self._selected][uid]["flags"].add(r"\Deleted")

    def expunge(self):
        self.folders[self._selected] = {
            uid: e for uid, e in self.folders[self._selected].items()
            if r"\Deleted" not in e["flags"]
        }

    def logout(self):
        pass
