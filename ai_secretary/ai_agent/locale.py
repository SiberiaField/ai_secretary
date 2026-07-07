from dataclasses import dataclass


@dataclass
class AgentLocale:
    """
    Класс для хранения языковых шаблонов внутренних сообщений агента.
    """
    tool_not_found: str = "Error: Tool '{tool_name}' not found. Available tools: {available_tools}"
    tool_execution_error: str = "Error executing tool '{tool_name}': {error}. Please check arguments or try a different approach."
    tool_calling_error: str = (
        "Error: Failed to parse tool call. {error}\n"
        "Your output was:\n```\n{raw_output}\n```\n"
        "Please retry with a properly formatted tool call."
    )

    @classmethod
    def en(cls) -> 'AgentLocale':
        """Возвращает английскую локализацию (по умолчанию)."""
        return cls()

    @classmethod
    def ru(cls) -> 'AgentLocale':
        """Возвращает русскую локализацию."""
        return cls(
            tool_not_found="Ошибка: Инструмент '{tool_name}' не найден. Доступные инструменты: {available_tools}",
            tool_execution_error="Ошибка при выполнении инструмента '{tool_name}': {error}. Пожалуйста, проверьте аргументы или попробуйте другой подход.",
            tool_calling_error=(
                "Ошибка: Не удалось распарсить вызов инструмента. {error}\n"
                "Ваш вывод был:\n```\n{raw_output}\n```\n"
                "Пожалуйста, повторите вызов инструмента в корректном формате."
            ),
        )