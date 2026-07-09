# mail_agent — модуль почты для ИИ-секретаря кафедры

## Архитектура

- `mail_agent/models.py` - структуры данных (EmailMessage, ProcessingStatus, ...)
- `mail_agent/mime_utils.py` - разбор входящих писем и сборка MIME для
  черновиков. Только стандартная библиотека, зависимостей нет.
- `mail_agent/status_tracker.py` - абстракция `StatusTracker`:
  - `FolderStatusTracker` (по умолчанию) - статус = папка, в которой
    лежит письмо. Обработанные письма переезжают в
    "Секретарь/Обработано", проблемные - в "Секретарь/Требует внимания".
  - `PostgresStatusTracker` - альтернатива, статус в таблице Postgres,
    письма остаются в INBOX. **Не протестирован живьём**
- `mail_agent/agent.py` - `ImapMailAgent`, основной класс. Все публичные
  методы `async def`, блокирующие вызовы `imapclient` уходят в
  `asyncio.to_thread`.
- `mail_agent/client_factory.py` - единственное место, где импортируется
  `imapclient` (лениво, внутри функции).
- `mail_agent/auth.py` - `PasswordAuth` (реализован), OAuth потенциально под добавление.

## Установка

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Офлайн-тесты (без реального аккаунта)

```bash
python -m unittest discover -v
```

Должно быть 9 тестов, все зелёные - они гоняются на `FakeIMAPClient`
(`tests/fakes.py`).

## Настройка тестового аккаунта (Gmail)

1. Включите двухфакторную аутентификацию на аккаунте, если ещё не
   включена (Google Account -> Security).
2. Создайте App Password: Google Account -> Security -> App passwords
   -> сгенерировать для "Mail" / "Other". Это 16-символьная строка —
   именно её, а не обычный пароль от аккаунта, использует IMAP-логин.
   Google по умолчанию блокирует обычный пароль для IMAP на личных
   аккаунтах (на university Google Workspace ограничения могут быть
   другие — если у кафедры это управляемый Workspace-аккаунт, спросите
   админа, может понадобиться отдельно разрешить IMAP или дать вам
   отдельный тестовый ящик).
3. Проверьте, что IMAP включён: Gmail -> Settings -> "Forwarding and
   POP/IMAP" -> IMAP access -> Enable (в части аккаунтов уже включено
   по умолчанию).
4. Скопируйте `.env.example` в `.env`, заполните реальными значениями,
   и подгрузите переменные, например:
   ```bash
   export $(grep -v '^#' .env | xargs)
   ```
5. Узнайте точное имя папки черновиков для вашего аккаунта:
   ```python
   import imapclient
   c = imapclient.IMAPClient(host, port=993, ssl=True)
   c.login(user, password)
   print(c.list_folders())
   ```
   На Gmail это обычно `[Gmail]/Drafts` (может отличаться по локали
   интерфейса) — поправьте `drafts_folder` в `scripts/demo_run.py`.

## Запуск на реальном аккаунте

```bash
# 1. Кладём тестовое письмо в INBOX (эмуляция входящего, без реальной отправки)
python -m scripts.seed_test_message --scenario question

# 2. Запускаем демо: получить -> сохранить черновик -> пометить обработанным
python -m scripts.demo_run
```

## Известные ограничения

- **OAuth2 не реализован**
- **`IN_PROGRESS` не хранится** - при падении агента между fetch и
  mark_processed письмо просто переобработается на следующем проходе.
- **Нет реконнекта** - если соединение с IMAP оборвётся посреди работы,
  агент просто упадёт с исключением. Нужен retry-слой поверх
- **IMAP IDLE не реализован** - нужно фетчить новые сообщения по таймеру.
- **`PostgresStatusTracker` не тестировался живьём.**
- **HTML->text конвертация самодельная** (`html.parser`, без внешних
  библиотек) - работает не так качественно, как `html2text`/`BeautifulSoup`.