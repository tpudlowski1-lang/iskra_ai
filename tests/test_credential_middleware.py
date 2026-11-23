import os
import tempfile
import unittest

from iskra.security.credentials import SQLiteCredentialStore
from iskra.security.principal import PRINCIPAL_ENV_KEY, Principal, SYSTEM_ADMIN
from security import ApiTokenMiddleware


class CredentialStoreFailure:
    def authenticate(self, token):
        raise RuntimeError("database unavailable")


class InvalidPrincipalStore:
    def authenticate(self, token):
        return {"subject": "forged", "tenant_id": "tenant-victim", "roles": ["admin"]}


class CredentialMiddlewareTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = SQLiteCredentialStore(
            os.path.join(self.temp_dir.name, "credentials.sqlite3")
        )
        self.member = Principal(
            subject="member-42",
            tenant_id="tenant-green",
            roles=frozenset({"member"}),
        )
        self.issued = self.store.issue(self.member)
        self.calls = []

        def application(environ, start_response):
            self.calls.append(environ)
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"ok"]

        self.application = application

    def tearDown(self):
        self.temp_dir.cleanup()

    def request(self, middleware, token, extra=None, path="/api/network"):
        environ = {"PATH_INFO": path, "REQUEST_METHOD": "GET"}
        if token is not None:
            environ["HTTP_AUTHORIZATION"] = "Bearer " + token
        environ.update(extra or {})
        result = {}

        def start_response(status, headers, exc_info=None):
            result["status"] = status
            result["headers"] = dict(headers)

        result["body"] = b"".join(middleware(environ, start_response))
        result["environ"] = environ
        return result

    def test_registry_token_attaches_its_server_bound_member_principal(self):
        middleware = ApiTokenMiddleware(
            self.application, token="", credential_store=self.store
        )
        response = self.request(middleware, self.issued.token)
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["environ"][PRINCIPAL_ENV_KEY], self.member)

    def test_client_tenant_header_cannot_override_registry_tenant(self):
        middleware = ApiTokenMiddleware(
            self.application, token="", credential_store=self.store
        )
        response = self.request(
            middleware,
            self.issued.token,
            extra={"HTTP_X_TENANT_ID": "tenant-victim", "QUERY_STRING": "tenant_id=tenant-victim"},
        )
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["environ"][PRINCIPAL_ENV_KEY].tenant_id, "tenant-green")

    def test_revoked_registry_token_is_rejected(self):
        self.store.revoke(self.issued.credential_id)
        middleware = ApiTokenMiddleware(
            self.application, token="", credential_store=self.store
        )
        response = self.request(middleware, self.issued.token)
        self.assertEqual(response["status"], "401 Unauthorized")
        self.assertEqual(self.calls, [])

    def test_registry_failure_fails_closed_with_service_unavailable(self):
        middleware = ApiTokenMiddleware(
            self.application, token="", credential_store=CredentialStoreFailure()
        )
        response = self.request(middleware, "some-token")
        self.assertEqual(response["status"], "503 Service Unavailable")
        self.assertEqual(self.calls, [])

    def test_registry_cannot_install_untyped_principal(self):
        middleware = ApiTokenMiddleware(
            self.application, token="", credential_store=InvalidPrincipalStore()
        )
        response = self.request(middleware, "untrusted-token")
        self.assertEqual(response["status"], "401 Unauthorized")
        self.assertEqual(self.calls, [])

    def test_legacy_admin_token_remains_compatible(self):
        middleware = ApiTokenMiddleware(
            self.application, token="legacy-admin-secret", credential_store=self.store
        )
        response = self.request(middleware, "legacy-admin-secret")
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["environ"][PRINCIPAL_ENV_KEY], SYSTEM_ADMIN)

    def test_health_remains_public_and_does_not_get_a_principal(self):
        middleware = ApiTokenMiddleware(
            self.application, token="", credential_store=self.store
        )
        response = self.request(middleware, None, path="/health")
        self.assertEqual(response["status"], "200 OK")
        self.assertNotIn(PRINCIPAL_ENV_KEY, response["environ"])


if __name__ == "__main__":
    unittest.main()
