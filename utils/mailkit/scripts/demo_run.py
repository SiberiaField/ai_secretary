"""
Демка, читающая 10 новых сообщений, переносящая их после обработки
в спец. папку и создающая черновики ответов, в данном случае одинаковые шаблоны.

Запуск:
    python -m scripts.demo_run
"""
from __future__ import annotations

import asyncio
import os

import imapclient

from mail_agent.agent import create_folder_based_agent
from mail_agent.config import MailAccountConfig
from mail_agent.models import ProcessingStatus


async def main() -> None:
    host = os.environ["TEST_IMAP_HOST"]
    port = int(os.environ.get("TEST_IMAP_PORT", "993"))
    user = os.environ["TEST_IMAP_USER"]
    password = os.environ["TEST_IMAP_APP_PASSWORD"]

    client = imapclient.IMAPClient(host, port=port, ssl=True)
    client.login(user, password)

    config = MailAccountConfig(imap_host=host, drafts_folder=None) # Пока работает только с пользовательской папкой - под исправление
    agent = create_folder_based_agent(client, config, from_address=user)

    messages = await agent.fetch_new_messages(limit=10)
    print(f"Новых писем в INBOX: {len(messages)}")

    for msg in messages:
        print(f"- {msg.subject!r} от {msg.from_addr.address} (вложений: {len(msg.attachments)})")

        draft = await agent.save_draft(
            msg,
            body_html="<p>Спасибо за письмо! Мы скоро ответим.</p>"
            "<p>— секретарь кафедры (черновик, сгенерирован автоматически)</p>",
        )
        print(f"  черновик сохранён: uid={draft.uid} в папке {draft.folder!r}")

        await agent.mark_processed(msg, ProcessingStatus.PROCESSED)
        print("  письмо перемещено в папку 'Обработано'")

    client.logout()


if __name__ == "__main__":
    asyncio.run(main())
