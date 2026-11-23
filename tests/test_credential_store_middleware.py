import os
import tempfile
import unittest

from flask import Flask, request

from iskra.security.principal import PRINCIPAL_ENV_KEY, Principal, SYSTEM_ADMIN
from iskra.security.sqlite_credentials import SQLiteCredentialStore
from security import ApiTokenMiddleware


class BrokenStore:
    def authenticate(self, token):
        raise OSError("database unavailable")


class InvalidStore:
    def authenticate(self, token):
        return {"subject": "forged", "tenant_id": "tenant-victim", "roles": ["admin"]}


class CredentialMiddlewareIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = SQLiteCredentialStore(
            os.path.join(self.temp_dir.name, "credentials.sqlite3")
        )
        self.member = Principal("member-9", "tenant-silver", frozenset({"member"}))
        self.issued = self.store.issue(self.member)
        self.app = Flask(__name__)

        @self.app.get("/whoami")
        def whoami():
            principal = request.environ[PRINCIPAL_ENV_KEY]
            return {"subject": principal.subject, "tenant_id": principal.tenant_id}

    def tearDown(self):
        self.temp_dir.cleanup()

    def client(self, store=None, token=""):
        app = Flask(__name__)

        @app.get("/whoami")
        def whoami():
            principal = request.environ[PRINCIPAL_ENV_KEY]
            return {"subject": principal.subject, "tenant_id": principal.tenant_id}

        app.wsgi_app = ApiTokenMiddleware(
            app.wsgi_app, token=token, credential_store=store
        )
        return app.test_client()

    def test_persistent_credential_authenticates_bound_tenant(self):
        response = self.client(self.store).get(
            "/whoami", headers={"Authorization": f"Bearer {self.issued.token}"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "subject": "member-9", "tenant_id": "tenant-silver"
        })

    def test_request_tenant_header_cannot_override_registry(self):
        response = self.client(self.store).get(
            "/whoami",
            headers={
                "Authorization": f"Bearer {self.issued.token}",
                "X-Tenant-ID": "tenant-victim",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["tenant_id"], "tenant-silver")

    def test_revoked_registry_token_is_rejected(self):
        self.store.revoke(self.issued.credential_id)
        response = self.client(self.store).get(
            "/whoami", headers={"Authorization": f"Bearer {self.issued.token}"}
        )
        self.assertEqual(response.status_code, 401)

    def test_backend_failure_returns_503_without_fallback(self):
        response = self.client(BrokenStore(), token="legacy-secret").get(
            "/whoami", headers={"Authorization": "Bearer registry-token"}
        )
        self.assertEqual(response.status_code, 503)

    def test_untyped_backend_identity_is_rejected(self):
        response = self.client(InvalidStore()).get(
            "/whoami", headers={"Authorization": "Bearer forged-token"}
        )
        self.assertEqual(response.status_code, 401)

    def test_legacy_admin_token_remains_compatible(self):
        response = self.client(self.store, token="legacy-secret").get(
            "/whoami", headers={"Authorization": "Bearer legacy-secret"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["tenant_id"], "system")

    def test_health_remains_public_when_store_is_enabled(self):
        app = Flask(__name__)

        @app.get("/health")
        def health():
            return {"status": "ok"}

        app.wsgi_app = ApiTokenMiddleware(app.wsgi_app, credential_store=self.store)
        response = app.test_client().get("/health")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
