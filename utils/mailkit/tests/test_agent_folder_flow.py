import unittest
from email.message import EmailMessage as MimeMsg
from email.policy import default as default_policy

from mail_agent.agent import create_folder_based_agent
from mail_agent.config import MailAccountConfig
from mail_agent.models import ProcessingStatus
from tests.fakes import FakeIMAPClient


def _make_raw_incoming(subject="Вопрос", from_addr="student@example.com", message_id="<1@example.com>") -> bytes:
    msg = MimeMsg(policy=default_policy)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = "secretary@dept.example"
    msg["Message-ID"] = message_id
    msg.set_content("Здравствуйте, у меня вопрос по практике.")
    return msg.as_bytes()


class FolderFlowTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = FakeIMAPClient()
        self.config = MailAccountConfig(imap_host="imap.example.com", drafts_folder="Drafts")
        self.agent = create_folder_based_agent(
            client=self.client, config=self.config, from_address="secretary@dept.example"
        )

    async def test_fetch_then_mark_processed_removes_from_inbox(self):
        self.client.seed_message("INBOX", _make_raw_incoming())

        new_messages = await self.agent.fetch_new_messages()
        self.assertEqual(len(new_messages), 1)
        self.assertEqual(new_messages[0].subject, "Вопрос")

        await self.agent.mark_processed(new_messages[0], ProcessingStatus.PROCESSED)

        self.assertEqual(len(self.client.folders["INBOX"]), 0)
        target = self.config.folder_map[ProcessingStatus.PROCESSED]
        self.assertEqual(len(self.client.folders[target]), 1)

        # повторный fetch больше ничего не возвращает — письмо уже не в INBOX
        self.assertEqual(await self.agent.fetch_new_messages(), [])

    async def test_needs_attention_moves_to_dedicated_folder(self):
        self.client.seed_message("INBOX", _make_raw_incoming(message_id="<2@example.com>"))
        [msg] = await self.agent.fetch_new_messages()

        await self.agent.mark_processed(msg, ProcessingStatus.NEEDS_ATTENTION)

        target = self.config.folder_map[ProcessingStatus.NEEDS_ATTENTION]
        self.assertEqual(len(self.client.folders[target]), 1)
        self.assertEqual(len(self.client.folders["INBOX"]), 0)

    async def test_save_draft_appends_to_drafts_with_thread_headers(self):
        self.client.seed_message("INBOX", _make_raw_incoming(message_id="<3@example.com>"))
        [msg] = await self.agent.fetch_new_messages()

        draft_ref = await self.agent.save_draft(msg, body_html="<p>Ответ студенту</p>")

        self.assertEqual(draft_ref.folder, "Drafts")
        stored = self.client.folders["Drafts"][draft_ref.uid]
        self.assertIn(r"\Draft", stored["flags"])

        # оригинальное письмо в INBOX никуда не делось — save_draft не меняет статус
        self.assertEqual(len(self.client.folders["INBOX"]), 1)

    async def test_update_draft_preserves_thread_and_replaces_body(self):
        self.client.seed_message("INBOX", _make_raw_incoming(message_id="<4@example.com>"))
        [msg] = await self.agent.fetch_new_messages()
        draft_ref = await self.agent.save_draft(msg, body_html="<p>Черновик v1</p>")

        new_ref = await self.agent.update_draft(draft_ref, body_html="<p>Черновик v2, исправлено</p>")

        self.assertNotEqual(new_ref.uid, draft_ref.uid)  # IMAP пересоздаёт письмо
        self.assertNotIn(draft_ref.uid, self.client.folders["Drafts"])  # старое удалено
        self.assertIn(new_ref.uid, self.client.folders["Drafts"])

    async def test_repeated_processing_run_is_idempotent(self):
        self.client.seed_message("INBOX", _make_raw_incoming(message_id="<5@example.com>"))
        self.client.seed_message("INBOX", _make_raw_incoming(subject="Второй вопрос", message_id="<6@example.com>"))

        first_batch = await self.agent.fetch_new_messages()
        self.assertEqual(len(first_batch), 2)
        for m in first_batch:
            await self.agent.mark_processed(m, ProcessingStatus.PROCESSED)

        second_batch = await self.agent.fetch_new_messages()
        self.assertEqual(second_batch, [])


if __name__ == "__main__":
    unittest.main()
