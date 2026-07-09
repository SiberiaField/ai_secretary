"""
Единственное место в модуле, где реально импортируется imapclient.
Изолировано намеренно: остальная логика (agent.py, status_tracker.py,
mime_utils.py) работает через ImapClientLike (duck typing) и не требует
установленного imapclient — поэтому тесты запускаются без него.

pip install imapclient   # нужно только для использования этой функции
"""
from __future__ import annotations

import asyncio

from .auth import AuthStrategy
from .config import MailAccountConfig
from .exceptions import AuthenticationError, MailConnectionError


async def create_real_client(config: MailAccountConfig, auth: AuthStrategy):
    import imapclient  # локальный импорт, см. docstring модуля

    secret = await auth.get_secret()

    def _connect():
        try:
            client = imapclient.IMAPClient(config.imap_host, port=config.imap_port, ssl=True)
        except OSError as exc:
            raise MailConnectionError(f"Не удалось подключиться к {config.imap_host}: {exc}") from exc

        try:
            if auth.mechanism == "XOAUTH2":
                # TODO: проверить точную сигнатуру oauth2_login по документации
                # imapclient на момент подключения OAuth2 — не тестировалось.
                client.oauth2_login(auth.username, secret)
            else:
                client.login(auth.username, secret)
        except imapclient.exceptions.LoginError as exc:
            raise AuthenticationError(str(exc)) from exc

        return client

    return await asyncio.to_thread(_connect)
