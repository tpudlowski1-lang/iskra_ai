import base64
import json
import os
import tempfile
import unittest

from iskra.security.policy import require_roles, require_system_admin
from iskra.security.credentials import SQLiteCredentialStore
from iskra.security.principal import (
    PRINCIPAL_ENV_KEY,
    Principal,
    SYSTEM_ADMIN,
    principal_from_environ,
)
from security import ApiTokenMiddleware


class ApiTokenMiddlewareTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def application(environ, start_response):
            self.calls.append(environ["PATH_INFO"])
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"ok"]

        self.application = application

    def request(self, middleware, path="/api/network", headers=None):
        environ = {"PATH_INFO": path, "REQUEST_METHOD": "GET"}
        environ.update(headers or {})
        result = {}

        def start_response(status, response_headers, exc_info=None):
            result["status"] = status
            result["headers"] = dict(response_headers)

        result["body"] = b"".join(middleware(environ, start_response))
        result["environ"] = environ
        return result

    def test_health_is_public_without_token(self):
        response = self.request(ApiTokenMiddleware(self.application, token=""), path="/health")
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(self.calls, ["/health"])

    def test_missing_server_token_fails_closed(self):
        response = self.request(ApiTokenMiddleware(self.application, token=""))
        self.assertEqual(response["status"], "503 Service Unavailable")
        self.assertEqual(json.loads(response["body"])["error"], "service_not_configured")
        self.assertEqual(self.calls, [])

    def test_missing_client_token_is_rejected(self):
        response = self.request(ApiTokenMiddleware(self.application, token="secret"))
        self.assertEqual(response["status"], "401 Unauthorized")
        self.assertIn("WWW-Authenticate", response["headers"])
        self.assertEqual(self.calls, [])

    def test_bearer_token_is_accepted_and_attaches_trusted_principal(self):
        response = self.request(
            ApiTokenMiddleware(self.application, token="secret"),
            headers={"HTTP_AUTHORIZATION": "Bearer secret"},
        )
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["headers"]["X-Content-Type-Options"], "nosniff")
        self.assertEqual(principal_from_environ(response["environ"]), SYSTEM_ADMIN)

    def test_x_api_token_is_accepted(self):
        response = self.request(
            ApiTokenMiddleware(self.application, token="secret"),
            headers={"HTTP_X_API_TOKEN": "secret"},
        )
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(principal_from_environ(response["environ"]), SYSTEM_ADMIN)

    def test_basic_password_is_accepted_for_browser_dashboard(self):
        credentials = base64.b64encode(b"iskra:secret").decode("ascii")
        response = self.request(
            ApiTokenMiddleware(self.application, token="secret"),
            path="/",
            headers={"HTTP_AUTHORIZATION": "Basic " + credentials},
        )
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(principal_from_environ(response["environ"]), SYSTEM_ADMIN)

    def test_wrong_token_is_rejected_without_principal(self):
        response = self.request(
            ApiTokenMiddleware(self.application, token="secret"),
            headers={"HTTP_AUTHORIZATION": "Bearer wrong"},
        )
        self.assertEqual(response["status"], "401 Unauthorized")
        self.assertIsNone(principal_from_environ(response["environ"]))
        self.assertEqual(self.calls, [])

    def test_health_does_not_receive_authenticated_principal(self):
        response = self.request(
            ApiTokenMiddleware(self.application, token="secret"),
            path="/health",
        )
        self.assertEqual(response["status"], "200 OK")
        self.assertIsNone(principal_from_environ(response["environ"]))

    def test_sqlite_credential_authentication_attaches_tenant_principal(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteCredentialStore(os.path.join(directory, "credentials.sqlite3"))
            member = Principal("member-1", "tenant-a", frozenset({"member"}))
            issued = store.issue(member)
            response = self.request(
                ApiTokenMiddleware(self.application, token="", credential_store=store),
                headers={"HTTP_AUTHORIZATION": "Bearer " + issued.token},
            )
            self.assertEqual(response["status"], "200 OK")
            self.assertEqual(principal_from_environ(response["environ"]), member)

    def test_revoked_credential_is_rejected_by_middleware(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteCredentialStore(os.path.join(directory, "credentials.sqlite3"))
            issued = store.issue(Principal("member-1", "tenant-a", frozenset({"member"})))
            store.revoke(issued.credential_id)
            response = self.request(
                ApiTokenMiddleware(self.application, token="", credential_store=store),
                headers={"HTTP_AUTHORIZATION": "Bearer " + issued.token},
            )
            self.assertEqual(response["status"], "401 Unauthorized")
            self.assertEqual(self.calls, [])


class PrincipalTests(unittest.TestCase):
    def test_principal_is_immutable_and_normalizes_roles(self):
        principal = Principal("user-1", "tenant-a", frozenset({"member"}))
        self.assertEqual(principal.roles, frozenset({"member"}))
        with self.assertRaises(AttributeError):
            principal.tenant_id = "tenant-b"

    def test_invalid_principal_is_rejected(self):
        with self.assertRaises(ValueError):
            Principal("", "tenant-a", frozenset({"member"}))
        with self.assertRaises(ValueError):
            Principal("user-1", "tenant-a", frozenset({"owner"}))

    def test_client_supplied_tenant_id_is_not_a_principal(self):
        environ = {"QUERY_STRING": "tenant_id=tenant-victim"}
        self.assertIsNone(principal_from_environ(environ))

    def test_only_trusted_principal_instance_is_accepted(self):
        self.assertIsNone(principal_from_environ({PRINCIPAL_ENV_KEY: {"tenant_id": "spoofed"}}))
        self.assertEqual(
            principal_from_environ({PRINCIPAL_ENV_KEY: SYSTEM_ADMIN}),
            SYSTEM_ADMIN,
        )


class AuthorizationPolicyTests(unittest.TestCase):
    def test_policy_rejects_missing_principal(self):
        from flask import Flask

        app = Flask(__name__)

        @app.get("/admin")
        @require_roles("admin")
        def admin():
            return "ok"

        response = app.test_client().get("/admin")
        self.assertEqual(response.status_code, 401)

    def test_policy_rejects_wrong_role(self):
        from flask import Flask

        app = Flask(__name__)

        @app.get("/admin")
        @require_roles("admin")
        def admin():
            return "ok"

        @app.before_request
        def attach_member():
            from flask import request
            request.environ[PRINCIPAL_ENV_KEY] = Principal(
                "member-1", "tenant-a", frozenset({"member"})
            )

        response = app.test_client().get("/admin")
        self.assertEqual(response.status_code, 403)

    def test_policy_accepts_required_role(self):
        from flask import Flask

        app = Flask(__name__)

        @app.get("/admin")
        @require_roles("admin")
        def admin():
            return "ok"

        @app.before_request
        def attach_admin():
            from flask import request
            request.environ[PRINCIPAL_ENV_KEY] = SYSTEM_ADMIN

        response = app.test_client().get("/admin")
        self.assertEqual(response.status_code, 200)

    def test_system_admin_policy_rejects_tenant_admin(self):
        from flask import Flask

        app = Flask(__name__)

        @app.get("/global")
        @require_system_admin
        def global_data():
            return "secret"

        @app.before_request
        def attach_tenant_admin():
            from flask import request
            request.environ[PRINCIPAL_ENV_KEY] = Principal(
                "admin-1", "tenant-a", frozenset({"admin"})
            )

        response = app.test_client().get("/global")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
