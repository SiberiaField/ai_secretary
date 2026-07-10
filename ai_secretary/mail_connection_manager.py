from __future__ import annotations

import asyncio
import imaplib
import logging
import ssl
from typing import Awaitable, Callable, TypeVar

from mail_agent import ImapMailAgent
from mail_agent.auth import AuthStrategy, PasswordAuth
from mail_agent.agent import create_folder_based_agent
from mail_agent.client_factory import create_real_client
from mail_agent.config import MailAccountConfig

logger = logging.getLogger(__name__)

T = TypeVar("T")

_CONNECTION_ERRORS = (ssl.SSLError, imaplib.IMAP4.abort, OSError)


class MailConnectionManager:
    """
    Единственная точка доступа к ImapMailAgent для всего приложения.

    1. Сериализация: все обращения к mail_agent идут через call(),
       под одним общим локом — конкурентный доступ к stateful
       IMAP-сессии из poll_mail/sorting_agent/sending_agent иначе
       ломает TLS-сокет (RECORD_LAYER_FAILURE).
    2. Реконнект: при обрыве соединения (SSL/сокет) пересоздаёт
       клиент и повторяет операцию один раз, вместо падения демона
       навсегда (mail_agent сам не переподключается — см. README).
    """

    def __init__(self, mail_agent: ImapMailAgent, mail_config: MailAccountConfig, auth: AuthStrategy):
        self.mail_agent = mail_agent
        self._mail_config = mail_config
        self._auth = auth
        self._lock = asyncio.Lock()

    @staticmethod
    def _is_connection_error(exc: BaseException) -> bool:
        if isinstance(exc, _CONNECTION_ERRORS):
            return True
        cause = exc.__cause__
        return isinstance(cause, _CONNECTION_ERRORS) if cause else False

    async def _reconnect(self) -> None:
        logger.warning("[MailConnection] Обрыв соединения — переподключаюсь...")
        new_client = await create_real_client(self._mail_config, self._auth)
        self.mail_agent.replace_client(new_client)
        logger.info("[MailConnection] Переподключение выполнено.")

    async def call(self, bound_method: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        async with self._lock:
            try:
                return await bound_method(*args, **kwargs)
            except Exception as e:
                if not self._is_connection_error(e):
                    raise
                logger.error(f"[MailConnection] Ошибка соединения: {e}. Реконнект + повтор.")
                await self._reconnect()
                return await bound_method(*args, **kwargs)


async def build_mail_connection(config) -> MailConnectionManager:
    auth = PasswordAuth(username=config.mail.imap_user, password=config.mail.imap_app_password)
    mail_config = MailAccountConfig(
        imap_host=config.mail.imap_host,
        imap_port=config.mail.imap_port,
        drafts_folder=config.mail.drafts_folder,
    )
    client = await create_real_client(mail_config, auth)
    mail_agent = create_folder_based_agent(client, mail_config, from_address=config.mail.imap_user)
    return MailConnectionManager(mail_agent, mail_config, auth)