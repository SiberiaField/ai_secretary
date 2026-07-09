from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol


class AuthStrategy(Protocol):
    """Отвечает только за то, как получить секрет для логина.
    Сам логин (login/oauth2_login на клиенте) делает client_factory —
    здесь только "откуда взять пароль/токен". Метод асинхронный,
    т.к. вызывается из async-кода ДО ухода в поток с блокирующим
    imapclient (там уже нужен готовый plain-строковый секрет)."""

    username: str
    mechanism: str  # "PASSWORD" | "XOAUTH2"

    async def get_secret(self) -> str: ...


@dataclass
class PasswordAuth:
    """MVP: обычный пароль или app-password (Google Workspace с
    базовой авторизацией, либо личный Gmail с 2FA + app password)."""
    username: str
    password: str
    mechanism: str = "PASSWORD"

    async def get_secret(self) -> str:
        return self.password


@dataclass
class OAuth2Auth:
    """Заготовка под Gmail/Microsoft OAuth2 (XOAUTH2). НЕ реализован"""
    username: str
    token_provider: Callable[[], Awaitable[str]]
    mechanism: str = "XOAUTH2"

    async def get_secret(self) -> str:
        return await self.token_provider()
