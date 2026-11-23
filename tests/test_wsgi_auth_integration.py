import hashlib
import json
import os
import tempfile
import unittest

from flask import Flask, request

from iskra.security.principal import PRINCIPAL_ENV_KEY, Principal
from iskra.security.sqlite_credentials import SQLiteCredentialStore
from security import ApiTokenMiddleware
from wsgi import create_wsgi_app


class WsgiAuthenticationIntegrationTests(unittest.TestCase):
    def make_client(self, environ):
        application = Flask(__name__)

        @application.get("/health")
        def health():
            return {"status": "ok"}

        @application.get("/private")
        def private():
            principal = request.environ.get(PRINCIPAL_ENV_KEY)
            if principal is None:
                return {"error": "principal_missing"}, 500
            return {
                "subject": principal.subject,
                "tenant_id": principal.tenant_id,
                "roles": sorted(principal.roles),
            }

        application.wsgi_app = create_wsgi_app(application, environ=environ)
        return application.test_client()

    def test_unconfigured_wsgi_is_public_only_for_health(self):
        client = self.make_client({})
        self.assertEqual(client.get("/health").status_code, 200)
        response = client.get("/private")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "service_not_configured")

    def test_legacy_api_token_is_wired_from_wsgi_environment(self):
        client = self.make_client({"API_TOKEN": "legacy-admin-secret"})
        response = client.get(
            "/private",
            headers={"Authorization": "Bearer legacy-admin-secret"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["tenant_id"], "system")

    def test_persistent_registry_is_initialized_and_used_by_wsgi(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "credentials", "registry.sqlite3")
            issuer = SQLiteCredentialStore(database)
            principal = Principal("member-42", "tenant-green", frozenset({"member"}))
            issued = issuer.issue(principal)

            client = self.make_client({"ISKRA_CREDENTIAL_DB_PATH": database})
            response = client.get(
                "/private",
                headers={"Authorization": f"Bearer {issued.token}"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {
                "subject": "member-42",
                "tenant_id": "tenant-green",
                "roles": ["member"],
            })

            self.assertTrue(issuer.revoke(issued.credential_id))
            revoked = client.get(
                "/private",
                headers={"Authorization": f"Bearer {issued.token}"},
            )
            self.assertEqual(revoked.status_code, 401)

    def test_legacy_admin_token_and_registry_can_coexist(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "registry.sqlite3")
            issuer = SQLiteCredentialStore(database)
            member = issuer.issue(
                Principal("member-8", "tenant-amber", frozenset({"member"}))
            )
            client = self.make_client({
                "API_TOKEN": "legacy-admin-secret",
                "ISKRA_CREDENTIAL_DB_PATH": database,
            })

            member_response = client.get(
                "/private",
                headers={"Authorization": f"Bearer {member.token}"},
            )
            admin_response = client.get(
                "/private",
                headers={"Authorization": "Bearer legacy-admin-secret"},
            )
            self.assertEqual(member_response.status_code, 200)
            self.assertEqual(member_response.get_json()["tenant_id"], "tenant-amber")
            self.assertEqual(admin_response.status_code, 200)
            self.assertEqual(admin_response.get_json()["tenant_id"], "system")


    def test_static_registry_works_alongside_persistent_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "registry.sqlite3")
            token = "static-member-secret"
            static_principal = {
                "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
                "subject": "static-member",
                "tenant_id": "tenant-static",
                "roles": ["member"],
            }
            client = self.make_client({
                "ISKRA_CREDENTIAL_DB_PATH": database,
                "ISKRA_API_CREDENTIALS_JSON": json.dumps([static_principal]),
            })
            response = client.get(
                "/private",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {
                "subject": "static-member",
                "tenant_id": "tenant-static",
                "roles": ["member"],
            })


    def test_credential_store_outage_fails_closed_without_static_fallback(self):
        application = Flask(__name__)

        @application.get("/private")
        def private():
            return {"status": "should-not-be-reached"}

        class UnavailableStore:
            def authenticate(self, _token):
                raise RuntimeError("database unavailable")

        token = "static-member-secret"
        static_principal = {
            "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "subject": "static-member",
            "tenant_id": "tenant-static",
            "roles": ["member"],
        }
        secured = ApiTokenMiddleware(
            application.wsgi_app,
            credentials_json=json.dumps([static_principal]),
            credential_store=UnavailableStore(),
        )
        from werkzeug.test import Client
        from werkzeug.wrappers import Response
        response = Client(secured, Response).get(
            "/private",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "authentication_unavailable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
