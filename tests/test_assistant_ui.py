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
        self.assertIn('id="account-panel"', body)
        self.assertIn('id="credential-form"', body)
        self.assertIn('id="issued-token"', body)

    def test_assistant_script_does_not_persist_api_token(self):
        response = self.client.get("/static/assistant.js")
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        script = response.get_data(as_text=True)
        self.assertNotIn("localStorage", script)
        self.assertNotIn("sessionStorage", script)
        self.assertIn("textContent", script)
        self.assertIn("/api/tenant/chat", script)
        self.assertIn("/api/tenant/session", script)
        self.assertIn("/api/browser/session", script)
        self.assertIn("X-CSRF-Token", script)
        self.assertNotIn("apiToken", script)
        self.assertNotIn('headers.set("Authorization"', script)
        self.assertIn("/api/tenant/credentials", script)
        self.assertIn("showIssuedToken", script)
        self.assertIn("credentialForm", script)
        self.assertIn("documents.forEach((doc)", script)
        self.assertNotIn("documents.forEach((document)", script)
        self.assertIn("sessionGeneration", script)
        self.assertIn("generation !== sessionGeneration", script)

    def test_session_loading_ignores_responses_from_stale_generations(self):
        response = self.client.get("/static/assistant.js")
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        script = response.get_data(as_text=True)
        start = script.index("  async function loadSession() {")
        end = script.index("\n  async function loadCredentials()", start)
        load_session = script[start:end]

        self.assertIn("const generation = sessionGeneration;", load_session)
        fetch_guard = load_session.index("if (generation !== sessionGeneration) return;", load_session.index("await apiRequest"))
        json_guard = load_session.index("if (generation !== sessionGeneration) return;", load_session.index("await response.json()"))
        roles_write = load_session.index("sessionRoles =")
        panel_write = load_session.index("accountPanel.hidden =")
        self.assertLess(fetch_guard, json_guard)
        self.assertLess(json_guard, roles_write)
        self.assertLess(json_guard, panel_write)
        self.assertIn("if (generation === sessionGeneration)", load_session)

    def test_assistant_page_has_security_headers(self):
        response = self.client.get("/assistant")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertIn("default-src 'self'", response.headers.get("Content-Security-Policy", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
