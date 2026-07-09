"""
Разбор входящих писем и сборка исходящих (черновиков) — только
стандартная библиотека (email.*, html.parser), без внешних зависимостей.
"""
from __future__ import annotations

from email import message_from_bytes, policy
from email.message import EmailMessage as MimeEmailMessage
from email.utils import getaddresses, make_msgid, parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import List, Optional, Tuple

from .models import EmailAddress, EmailMessage, IncomingAttachment, OutgoingAttachment


def _parse_addresses(header_value: Optional[str]) -> List[EmailAddress]:
    if not header_value:
        return []
    return [
        EmailAddress(name=name or None, address=addr)
        for name, addr in getaddresses([header_value])
        if addr
    ]


def parse_message(
    raw: bytes,
    *,
    uid: int,
    uid_validity: int,
    folder: str,
    flags: frozenset,
) -> EmailMessage:
    """Строит EmailMessage из сырых байт письма (как их вернул IMAP FETCH)."""
    msg = message_from_bytes(raw, policy=policy.default)

    body_text: Optional[str] = None
    body_html: Optional[str] = None
    attachments: List[IncomingAttachment] = []

    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue

            disposition = part.get_content_disposition()
            content_type = part.get_content_type()

            if disposition == "attachment" or (part.get_filename() and disposition != "inline"):
                payload = part.get_payload(decode=True) or b""
                attachments.append(
                    IncomingAttachment(
                        filename=part.get_filename() or "unnamed",
                        content_type=content_type,
                        size=len(payload),
                    )
                )
                continue

            if content_type == "text/plain" and body_text is None:
                body_text = part.get_content()
            elif content_type == "text/html" and body_html is None:
                body_html = part.get_content()
    else:
        if msg.get_content_type() == "text/html":
            body_html = msg.get_content()
        else:
            body_text = msg.get_content()

    references_header = msg.get("References", "")
    references = references_header.split() if references_header else []

    date_header = msg.get("Date")
    date = None
    if date_header:
        try:
            date = parsedate_to_datetime(date_header)
        except (TypeError, ValueError):
            date = None

    from_addrs = _parse_addresses(msg.get("From"))

    return EmailMessage(
        message_id=(msg.get("Message-ID") or "").strip(),
        uid=uid,
        uid_validity=uid_validity,
        folder=folder,
        in_reply_to=msg.get("In-Reply-To"),
        references=references,
        from_addr=from_addrs[0] if from_addrs else EmailAddress(name=None, address=""),
        to=_parse_addresses(msg.get("To")),
        cc=_parse_addresses(msg.get("Cc")),
        subject=msg.get("Subject", ""),
        date=date,
        body_text=body_text,
        body_html=body_html,
        attachments=attachments,
        flags=frozenset(flags),
    )


def extract_attachment_bytes(raw: bytes, filename: str) -> bytes:
    """Достаёт байты конкретного вложения по имени файла из сырого
    письма - используется для ленивой подгрузки (fetch_attachment_data)."""
    msg = message_from_bytes(raw, policy=policy.default)
    for part in msg.walk():
        if part.get_filename() == filename:
            return part.get_payload(decode=True) or b""
    raise FileNotFoundError(f"Вложение {filename!r} не найдено в письме")


class _HTMLTextExtractor(HTMLParser):
    """Грубое, но зависимость-свободное извлечение текста из HTML — для
    авто-генерации text/plain версии черновика. Когда появится сеть для
    pip, разумно заменить на html2text/BeautifulSoup - качество
    извлечения текста станет заметно лучше на сложной вёрстке."""

    _BLOCK_TAGS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__()
        self._chunks: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1
        if tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)

    def text(self) -> str:
        raw = unescape("".join(self._chunks))
        lines = [line.strip() for line in raw.splitlines()]
        result: List[str] = []
        for line in lines:
            if line or (result and result[-1]):
                result.append(line)
        return "\n".join(result).strip()


def html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.text()


def _set_alternative_body(msg: MimeEmailMessage, body_html: str, body_text: Optional[str]) -> None:
    text_part = body_text if body_text is not None else html_to_text(body_html)
    msg.set_content(text_part)
    msg.add_alternative(body_html, subtype="html")


def build_reply_mime(
    *,
    in_reply_to: EmailMessage,
    from_address: str,
    body_html: str,
    body_text: Optional[str] = None,
    subject: Optional[str] = None,
    attachments: Optional[List[OutgoingAttachment]] = None,
) -> Tuple[bytes, str]:
    """Собирает multipart/alternative MIME-письмо (текст+HTML) с
    заголовками треда, готовое для IMAP APPEND в папку "Черновики".
    Возвращает (сырые байты письма, Message-ID)."""

    msg = MimeEmailMessage(policy=policy.default)
    msg["Subject"] = subject or f"Re: {in_reply_to.subject}"
    msg["From"] = from_address
    msg["To"] = in_reply_to.from_addr.address

    if in_reply_to.message_id:
        msg["In-Reply-To"] = in_reply_to.message_id
        msg["References"] = " ".join([*in_reply_to.references, in_reply_to.message_id])

    message_id = make_msgid()
    msg["Message-ID"] = message_id

    _set_alternative_body(msg, body_html, body_text)

    for att in attachments or []:
        maintype, _, subtype = att.content_type.partition("/")
        msg.add_attachment(
            att.data,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=att.filename,
        )

    return msg.as_bytes(), message_id


def rebuild_draft_mime(
    *,
    old_raw: bytes,
    body_html: str,
    body_text: Optional[str] = None,
) -> Tuple[bytes, str]:
    """Пересобирает черновик, сохраняя заголовки треда старого черновика
    (Subject/From/To/In-Reply-To/References), но с новым телом и новым
    Message-ID (используется в update_draft - IMAP не даёт редактировать
    письмо на месте)."""
    old_msg = message_from_bytes(old_raw, policy=policy.default)

    new_msg = MimeEmailMessage(policy=policy.default)
    for header in ("Subject", "From", "To", "In-Reply-To", "References"):
        value = old_msg.get(header)
        if value:
            new_msg[header] = value

    message_id = make_msgid()
    new_msg["Message-ID"] = message_id

    _set_alternative_body(new_msg, body_html, body_text)

    return new_msg.as_bytes(), message_id
