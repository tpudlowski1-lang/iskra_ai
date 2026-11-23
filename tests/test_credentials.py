import hashlib
import json
import unittest

from flask import Flask

from iskra.security.credentials import (
    CredentialConfigError,
    load_api_credentials,
    principal_for_token,
)
from iskra.security.policy import require_roles
from iskra.security.principal import PRINCIPAL_ENV_KEY, Principal
from security import ApiTokenMiddleware


class CredentialRegistryTests(unittest.TestCase):
    def setUp(self):
        self.raw_token = "tenant-a-secret-token"
        self.digest = hashlib.sha256(self.raw_token.encode("utf-8")).hexdigest()
        self.config = json.dumps([{
            "token_sha256": self.digest,
            "subject": "user-17",
            "tenant_id": "tenant-a",
            "roles": ["member"],
        }])

    def test_resolves_hashed_token_to_server_side_principal(self):
        credentials = load_api_credentials(self.config)
        principal = principal_for_token(self.raw_token, credentials)
        self.assertEqual(principal, Principal("user-17", "tenant-a", frozenset({"member"})))

    def test_unknown_or_empty_token_is_rejected(self):
        credentials = load_api_credentials(self.config)
        self.assertIsNone(principal_for_token("wrong-token", credentials))
        self.assertIsNone(principal_for_token("", credentials))
        self.assertIsNone(principal_for_token(None, credentials))

    def test_raw_token_is_not_present_in_loaded_registry(self):
        credentials = load_api_credentials(self.config)
        self.assertNotIn(self.raw_token, credentials)
        self.assertIn(self.digest, credentials)

    def test_invalid_json_fails_closed(self):
        with self.assertRaises(CredentialConfigError):
            load_api_credentials("{not-json")

    def test_duplicate_digest_is_rejected(self):
        record = {
            "token_sha256": self.digest,
            "subject": "user-17",
            "tenant_id": "tenant-a",
            "roles": ["member"],
        }
        with self.assertRaises(CredentialConfigError):
            load_api_credentials(json.dumps([record, record]))

    def test_invalid_role_is_rejected(self):
        record = {
            "token_sha256": self.digest,
            "subject": "user-17",
            "tenant_id": "tenant-a",
            "roles": ["owner"],
        }
        with self.assertRaises(CredentialConfigError):
            load_api_credentials(json.dumps([record]))


class TenantCredentialBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.member_token = "member-secret"
        digest = hashlib.sha256(self.member_token.encode("utf-8")).hexdigest()
        credentials = json.dumps([{
            "token_sha256": digest,
            "subject": "member-1",
            "tenant_id": "tenant-a",
            "roles": ["member"],
        }])

        app = Flask(__name__)

        @app.get("/global-graph")
        @require_roles("admin")
        def global_graph():
            return "global graph"

        @app.get("/principal")
        def principal_view():
            from flask import request
            principal = request.environ[PRINCIPAL_ENV_KEY]
            return {"subject": principal.subject, "tenant_id": principal.tenant_id}

        app.wsgi_app = ApiTokenMiddleware(
            app.wsgi_app,
            token="system-admin-secret",
            credentials_json=credentials,
        )
        self.client = app.test_client()

    def test_member_cannot_read_legacy_global_graph(self):
        response = self.client.get(
            "/global-graph",
            headers={"Authorization": f"Bearer {self.member_token}"},
        )
        self.assertEqual(response.status_code, 403)

    def test_system_admin_can_read_legacy_global_graph(self):
        response = self.client.get(
            "/global-graph",
            headers={"Authorization": "Bearer system-admin-secret"},
        )
        self.assertEqual(response.status_code, 200)

    def test_tenant_identity_comes_from_credential_not_request_header(self):
        response = self.client.get(
            "/principal",
            headers={
                "Authorization": f"Bearer {self.member_token}",
                "X-Tenant-ID": "tenant-victim",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "subject": "member-1",
            "tenant_id": "tenant-a",
        })

    def test_malformed_server_credentials_fail_closed(self):
        app = Flask(__name__)

        @app.get("/private")
        def private():
            return "should not run"

        app.wsgi_app = ApiTokenMiddleware(
            app.wsgi_app,
            token="system-admin-secret",
            credentials_json="{invalid",
        )
        response = app.test_client().get(
            "/private",
            headers={"Authorization": "Bearer system-admin-secret"},
        )
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
