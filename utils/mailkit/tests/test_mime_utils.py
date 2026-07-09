import unittest
from datetime import datetime

from mail_agent.mime_utils import build_reply_mime, html_to_text, parse_message, rebuild_draft_mime
from mail_agent.models import EmailAddress, EmailMessage


def _sample_incoming() -> EmailMessage:
    return EmailMessage(
        message_id="<orig@example.com>",
        uid=1,
        uid_validity=1,
        folder="INBOX",
        in_reply_to=None,
        references=[],
        from_addr=EmailAddress("Иван Иванов", "ivan@example.com"),
        to=[EmailAddress(None, "secretary@dept.example")],
        cc=[],
        subject="Вопрос по практике",
        date=datetime.now(),
        body_text="Здравствуйте, когда сдавать отчёт?",
        body_html=None,
        attachments=[],
        flags=frozenset(),
    )


class BuildAndParseRoundTrip(unittest.TestCase):
    def test_reply_headers_and_threading(self):
        original = _sample_incoming()
        mime_bytes, message_id = build_reply_mime(
            in_reply_to=original,
            from_address="secretary@dept.example",
            body_html="<p>Здравствуйте! Отчёт нужно сдать <b>до 1 сентября</b>.</p>",
        )
        parsed = parse_message(mime_bytes, uid=99, uid_validity=1, folder="Drafts", flags=frozenset())

        self.assertEqual(parsed.subject, "Re: Вопрос по практике")
        self.assertEqual(parsed.to[0].address, "ivan@example.com")
        self.assertEqual(parsed.in_reply_to, original.message_id)
        self.assertIn(original.message_id, parsed.references)
        self.assertIsNotNone(parsed.body_html)
        self.assertIsNotNone(parsed.body_text)
        self.assertIn("до 1 сентября", parsed.body_text)  # авто-текст из HTML
        self.assertEqual(message_id, parsed.message_id)

    def test_html_to_text_strips_tags(self):
        text = html_to_text("<p>Привет, <b>мир</b>!</p><p>Вторая строка</p>")
        self.assertIn("Привет, мир!", text)
        self.assertIn("Вторая строка", text)
        self.assertNotIn("<b>", text)

    def test_attachment_round_trip(self):
        from mail_agent.models import OutgoingAttachment

        mime_bytes, _ = build_reply_mime(
            in_reply_to=_sample_incoming(),
            from_address="secretary@dept.example",
            body_html="<p>Во вложении — задание.</p>",
            attachments=[
                OutgoingAttachment(
                    filename="task.txt",
                    content_type="text/plain",
                    data=b"individual assignment text",
                )
            ],
        )
        parsed = parse_message(mime_bytes, uid=1, uid_validity=1, folder="Drafts", flags=frozenset())
        self.assertEqual(len(parsed.attachments), 1)
        self.assertEqual(parsed.attachments[0].filename, "task.txt")

        from mail_agent.mime_utils import extract_attachment_bytes
        self.assertEqual(extract_attachment_bytes(mime_bytes, "task.txt"), b"individual assignment text")

    def test_rebuild_draft_preserves_thread_headers(self):
        original = _sample_incoming()
        mime_bytes, _ = build_reply_mime(
            in_reply_to=original, from_address="secretary@dept.example", body_html="<p>v1</p>"
        )
        new_bytes, new_id = rebuild_draft_mime(old_raw=mime_bytes, body_html="<p>v2 — исправленный текст</p>")
        parsed = parse_message(new_bytes, uid=2, uid_validity=1, folder="Drafts", flags=frozenset())

        self.assertEqual(parsed.subject, "Re: Вопрос по практике")
        self.assertEqual(parsed.in_reply_to, original.message_id)
        self.assertIn("исправленный текст", parsed.body_text)
        self.assertEqual(parsed.message_id, new_id)


if __name__ == "__main__":
    unittest.main()
