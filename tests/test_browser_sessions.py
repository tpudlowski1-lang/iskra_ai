import base64
import os
import tempfile
import time
import unittest

from flask import Flask

from iskra.api.routes import create_api_blueprint
from iskra.security.principal import Principal
from iskra.security.sqlite_credentials import SQLiteCredentialStore
from security import ApiTokenMiddleware


class BrowserSessionSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database = os.path.join(self.temp_dir.name, "private", "credentials.sqlite3")
        self.store = SQLiteCredentialStore(database)
        self.principal = Principal("tenant-owner", "tenant-blue", frozenset({"admin"}))
        self.issued = self.store.issue(self.principal)
        self.app = Flask(__name__)
        self.app.config["ISKRA_CREDENTIAL_STORE"] = self.store
        self.app.register_blueprint(create_api_blueprint(object()))

        @self.app.get("/assistant")
        def assistant_shell():
            return "public assistant shell"

        self.app.wsgi_app = ApiTokenMiddleware(
            self.app.wsgi_app,
            credential_store=self.store,
        )
        self.client = self.app.test_client()
        self.base_url = "https://iskra.test"

    def tearDown(self):
        self.temp_dir.cleanup()

    def login(self):
        response = self.client.post(
            "/api/browser/session",
            json={},
            headers={"Authorization": f"Bearer {self.issued.token}"},
            base_url=self.base_url,
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response

    def refresh_csrf(self):
        response = self.client.get("/api/browser/session", base_url=self.base_url)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()["csrf_token"]

    def test_assistant_shell_is_public_but_tenant_api_is_not(self):
        shell = self.client.get("/assistant", base_url=self.base_url)
        self.assertEqual(shell.status_code, 200)
        private = self.client.get("/api/tenant/session", base_url=self.base_url)
        self.assertEqual(private.status_code, 401)

    def test_login_sets_secure_httponly_host_cookie_and_returns_csrf(self):
        response = self.login()
        cookie = response.headers.get("Set-Cookie", "")
        self.assertIn("__Host-iskra_session=", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertIn("Path=/", cookie)
        self.assertNotIn("Domain=", cookie)
        self.assertTrue(response.get_json()["csrf_token"])

        session = self.client.get("/api/tenant/session", base_url=self.base_url)
        self.assertEqual(session.status_code, 200)
        self.assertEqual(session.get_json()["tenant_id"], "tenant-blue")

    def test_cookie_mutation_requires_csrf_and_same_origin(self):
        self.login()
        csrf = self.refresh_csrf()

        missing = self.client.post(
            "/api/tenant/credentials",
            json={"subject": "member-one", "roles": ["member"]},
            base_url=self.base_url,
        )
        self.assertEqual(missing.status_code, 403)
        self.assertEqual(missing.get_json()["error"], "csrf_rejected")

        cross_origin = self.client.post(
            "/api/tenant/credentials",
            json={"subject": "member-one", "roles": ["member"]},
            headers={"X-CSRF-Token": csrf, "Origin": "https://evil.test"},
            base_url=self.base_url,
        )
        self.assertEqual(cross_origin.status_code, 403)

        cross_site = self.client.post(
            "/api/tenant/credentials",
            json={"subject": "member-one", "roles": ["member"]},
            headers={"X-CSRF-Token": csrf, "Sec-Fetch-Site": "cross-site"},
            base_url=self.base_url,
        )
        self.assertEqual(cross_site.status_code, 403)

        accepted = self.client.post(
            "/api/tenant/credentials",
            json={"subject": "member-one", "roles": ["member"]},
            headers={"X-CSRF-Token": csrf, "Origin": "https://iskra.test"},
            base_url=self.base_url,
        )
        self.assertEqual(accepted.status_code, 201, accepted.get_data(as_text=True))

    def test_csrf_token_is_stable_across_page_refreshes_and_tabs(self):
        self.login()
        first_csrf = self.refresh_csrf()
        second_csrf = self.refresh_csrf()
        self.assertEqual(first_csrf, second_csrf)

        accepted = self.client.post(
            "/api/tenant/credentials",
            json={"subject": "member-from-second-tab", "roles": ["member"]},
            headers={"X-CSRF-Token": first_csrf},
            base_url=self.base_url,
        )
        self.assertEqual(accepted.status_code, 201, accepted.get_data(as_text=True))

    def test_logout_revokes_server_session_and_clears_cookie(self):
        self.login()
        csrf = self.refresh_csrf()
        response = self.client.post(
            "/api/browser/session/logout",
            headers={"X-CSRF-Token": csrf},
            base_url=self.base_url,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Max-Age=0", response.headers.get("Set-Cookie", ""))
        self.assertEqual(
            self.client.get("/api/tenant/session", base_url=self.base_url).status_code,
            401,
        )

    def test_revoking_api_credential_invalidates_browser_session(self):
        self.login()
        self.assertEqual(
            self.client.get("/api/tenant/session", base_url=self.base_url).status_code,
            200,
        )
        self.assertTrue(self.store.revoke(self.issued.credential_id))
        self.assertEqual(
            self.client.get("/api/tenant/session", base_url=self.base_url).status_code,
            401,
        )

    def test_static_legacy_token_cannot_be_exchanged_for_browser_session(self):
        application = Flask("legacy-token-session-test")
        application.register_blueprint(create_api_blueprint(object()))
        application.config["ISKRA_CREDENTIAL_STORE"] = self.store
        secured = ApiTokenMiddleware(
            application.wsgi_app,
            token="legacy-system-secret",
            credential_store=self.store,
        )
        from werkzeug.test import Client
        from werkzeug.wrappers import Response

        client = Client(secured, Response)
        response = client.post(
            "/api/browser/session",
            json={},
            headers={"Authorization": "Bearer legacy-system-secret"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json["error"], "persistent_credential_required")

    def test_basic_auth_mutations_require_same_origin(self):
        application = Flask("basic-auth-csrf-test")

        @application.post("/mutate")
        def mutate():
            return {"status": "ok"}

        secured = ApiTokenMiddleware(application.wsgi_app, token="basic-secret")
        from werkzeug.test import Client
        from werkzeug.wrappers import Response

        client = Client(secured, Response)
        basic = base64.b64encode(b"user:basic-secret").decode("ascii")
        cross_origin = client.post(
            "/mutate",
            headers={
                "Authorization": f"Basic {basic}",
                "Origin": "https://evil.test",
                "Host": "iskra.test",
            },
        )
        self.assertEqual(cross_origin.status_code, 403)

        no_origin = client.post(
            "/mutate",
            headers={"Authorization": f"Basic {basic}", "Host": "iskra.test"},
        )
        self.assertEqual(no_origin.status_code, 403)

        same_origin = client.post(
            "/mutate",
            headers={
                "Authorization": f"Basic {basic}",
                "Origin": "https://iskra.test",
                "Host": "iskra.test",
            },
        )
        self.assertEqual(same_origin.status_code, 200)

    def test_browser_session_expires(self):
        now = time.time()
        session_token = "s" * 48
        csrf_token = "c" * 48
        self.store.create_browser_session(
            self.principal,
            self.issued.credential_id,
            session_token,
            csrf_token,
            now + 30,
        )
        self.assertIsNotNone(self.store.authenticate_browser_session(session_token, now=now + 10))
        self.assertIsNone(self.store.authenticate_browser_session(session_token, now=now + 31))


if __name__ == "__main__":
    unittest.main(verbosity=2)
