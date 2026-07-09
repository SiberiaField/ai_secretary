"""
Скрипт для вывода списка всех папок на IMAP-сервере.
Помогает узнать точные названия системных папок (Черновики, Корзина, Спам),
чтобы правильно указать их в конфигурации агента.

Запуск:
    python -m scripts.list_folders
"""
from __future__ import annotations

import asyncio
import os

import imapclient


async def main() -> None:
    # Загружаем настройки из тех же переменных окружения
    host = os.environ["TEST_IMAP_HOST"]
    port = int(os.environ.get("TEST_IMAP_PORT", "993"))
    user = os.environ["TEST_IMAP_USER"]
    password = os.environ["TEST_IMAP_APP_PASSWORD"]

    print(f"Подключение к {host}:{port} под пользователем {user}...")
    
    # Инициализируем клиент синхронно, как в вашем примере
    client = imapclient.IMAPClient(host, port=port, ssl=True)
    client.login(user, password)

    print("\nСписок папок на сервере:")
    print("-" * 50)

    # Получаем папки. Метод возвращает список кортежей: 
    # (flags, delimiter, folder_name)
    folders = client.list_folders()

    for flags, delimiter, folder_name in folders:
        # flags — это системные флаги (например, b'\\Drafts', b'\\Trash')
        # folder_name — это точное имя папки, которое нужно передавать в конфиг
        decoded_flags = [f.decode("utf-8") for f in flags]
        
        print(f"Имя папки:  {folder_name!r}")
        print(f"Флаги:      {decoded_flags}")
        print(f"Разделитель: {delimiter.decode('utf-8')!r}")
        print("-" * 50)

    client.logout()
    print("Отключено.")


if __name__ == "__main__":
    asyncio.run(main())