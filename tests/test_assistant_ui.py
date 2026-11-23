import os
import unittest

os.environ["ISKRA_TESTING"] = "true"

from app import app


class AssistantUiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_assistant_page_is_served_with_external_assets(self):
        response = self.client.get("/assistant")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Asystent wiedzy", body)
        self.assertIn("/static/assistant.css", body)
        self.assertIn("/static/assistant.js", body)
        self.assertIn('type="password"', body)

    def test_assistant_script_does_not_persist_api_token(self):
        response = self.client.get("/static/assistant.js")
        self.assertEqual(response.status_code, 200)
        script = response.get_data(as_text=True)
        self.assertNotIn("localStorage", script)
        self.assertNotIn("sessionStorage", script)
        self.assertIn("textContent", script)
        self.assertIn("/api/tenant/chat", script)

    def test_assistant_page_has_security_headers(self):
        response = self.client.get("/assistant")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertIn("default-src 'self'", response.headers.get("Content-Security-Policy", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
