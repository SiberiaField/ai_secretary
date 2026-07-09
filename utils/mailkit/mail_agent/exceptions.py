class MailAgentError(Exception):
    """Базовый класс ошибок модуля."""


class MailConnectionError(MailAgentError):
    """Сетевая проблема / сервер недоступен."""


class AuthenticationError(MailConnectionError):
    """Отдельно от сетевых проблем: неверный пароль или истёкший
    OAuth2-токен — оркестратор может реагировать иначе (например,
    запросить обновление токена, а не просто retry с задержкой)."""


class DraftError(MailAgentError):
    """Ошибка при сохранении/обновлении/удалении черновика."""


class FlaggingError(MailAgentError):
    """Ошибка при попытке пометить/переместить письмо."""
