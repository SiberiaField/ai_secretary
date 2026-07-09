"""
Кладёт тестовое "входящее" письмо прямо в INBOX тестового аккаунта через
IMAP APPEND — без реальной отправки. Это и есть простой способ
генерировать тестовые сценарии без второго почтового аккаунта.

Требует: pip install imapclient, реальный IMAP-сервер, переменные
окружения из .env.example.

Запуск:
    python -m scripts.seed_test_message
    python -m scripts.seed_test_message --scenario attachment
"""
from __future__ import annotations

import argparse
import os
from email.message import EmailMessage
from email.policy import default

import imapclient

SCENARIOS = {
    "question": dict(
        subject="Вопрос по индивидуальному заданию на практику",
        from_addr="test.student@example.com",
        body="Здравствуйте!\n\nПодскажите, пожалуйста, где взять индивидуальное "
             "задание на практику.\n\nСпасибо,\nСтудент",
    ),
    "unclear": dict(
        subject="???",
        from_addr="confusing.sender@example.com",
        body="асдлфкjasdlkfj непонятный текст без структуры 12345 ??",
    ),
    "attachment": dict(
        subject="Отчёт по практике во вложении",
        from_addr="test.student2@example.com",
        body="Здравствуйте, прикладываю отчёт по практике.",
    ),
}


def build_message(scenario: str, to_addr: str) -> bytes:
    data = SCENARIOS[scenario]
    msg = EmailMessage(policy=default)
    msg["Subject"] = data["subject"]
    msg["From"] = data["from_addr"]
    msg["To"] = to_addr
    msg.set_content(data["body"])

    if scenario == "attachment":
        msg.add_attachment(
            b"content of a fake report file",
            maintype="text",
            subtype="plain",
            filename="report.txt",
        )

    return msg.as_bytes()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=list(SCENARIOS), default="question")
    args = parser.parse_args()

    host = os.environ["TEST_IMAP_HOST"]
    port = int(os.environ.get("TEST_IMAP_PORT", "993"))
    user = os.environ["TEST_IMAP_USER"]
    password = os.environ["TEST_IMAP_APP_PASSWORD"]

    raw = build_message(args.scenario, to_addr=user)

    with imapclient.IMAPClient(host, port=port, ssl=True) as client:
        client.login(user, password)
        client.select_folder("INBOX")
        client.append("INBOX", raw)

    print(f"Тестовое письмо (сценарий: {args.scenario!r}) добавлено в INBOX {user}.")


if __name__ == "__main__":
    main()
