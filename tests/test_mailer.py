# -*- coding: utf-8 -*-
"""Mail building and provider selection; no network is touched here."""
import os

os.environ["DESLAB_STORAGE"] = "file"  # tests must never touch a real database

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mailer  # noqa: E402


class MailerTests(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in
                      ("DESLAB_SMTP_USER", "DESLAB_SMTP_PASSWORD", "DESLAB_BREVO_KEY")}
        os.environ["DESLAB_MAIL_DISABLE"] = "1"  # ignore the developer's real secrets file
        for key in self.saved:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_nothing_is_configured_by_default(self):
        self.assertEqual(mailer.provider(), "none")
        self.assertFalse(mailer.send_welcome("a@b.co", "Wei"))
        self.assertIn("not configured", mailer.check())

    def test_smtp_settings_are_detected(self):
        os.environ["DESLAB_SMTP_USER"] = "biomatlab697@gmail.com"
        os.environ["DESLAB_SMTP_PASSWORD"] = "abcdefghijklmnop"
        self.assertEqual(mailer.provider(), "smtp")
        self.assertIn("smtp", mailer.check())

    def test_welcome_mail_carries_the_link_and_the_name(self):
        message = mailer.welcome_message("wei@example.com", "Wei", "https://example.streamlit.app")
        self.assertEqual(message["To"], "wei@example.com")
        self.assertEqual(message["Subject"], "Welcome to BioMat Lab")
        body = message.get_content()
        self.assertIn("Hello Wei", body)
        self.assertIn("https://example.streamlit.app", body)

    def test_reset_mail_carries_a_one_time_link(self):
        link = "https://example.streamlit.app/?reset_token=abc123"
        message = mailer.reset_message("wei@example.com", "Wei", link)
        self.assertEqual(message["Subject"], "Reset your BioMat Lab password")
        body = message.get_content()
        self.assertIn(link, body)
        self.assertIn("60 minutes", body)

    def test_brevo_payload_is_built_from_the_message(self):
        captured = {}

        def fake_post(url, payload, headers):
            captured.update({"url": url, "payload": payload, "headers": headers})
            return 201, "{}"

        os.environ["DESLAB_BREVO_KEY"] = "test-key"
        os.environ["DESLAB_BREVO_SENDER"] = "biomatlab697@gmail.com"
        original = mailer._post_json
        mailer._post_json = fake_post
        try:
            ok = mailer.send(mailer.welcome_message("wei@example.com", "Wei", "https://x"))
        finally:
            mailer._post_json = original
        self.assertTrue(ok)
        self.assertEqual(captured["url"], "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(captured["payload"]["to"], [{"email": "wei@example.com"}])
        self.assertEqual(captured["payload"]["subject"], "Welcome to BioMat Lab")
        self.assertEqual(captured["headers"]["api-key"], "test-key")
        self.assertEqual(mailer.provider(), "brevo")

    def test_a_failed_delivery_is_reported_not_raised(self):
        os.environ["DESLAB_BREVO_KEY"] = "test-key"
        os.environ["DESLAB_BREVO_SENDER"] = "biomatlab697@gmail.com"
        original = mailer._post_json
        mailer._post_json = lambda url, payload, headers: (401, '{"message":"bad key"}')
        try:
            self.assertFalse(mailer.send(mailer.reset_message("a@b.co", "A", "https://x")))
        finally:
            mailer._post_json = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
