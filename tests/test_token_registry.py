import json
import unittest
from unittest.mock import patch

from flask import Flask

from iskra.api.routes import create_api_blueprint
from iskra.security.principal import PRINCIPAL_ENV_KEY, Principal, principal_from_environ
from iskra.security.token_registry import TokenRegistry
from security import ApiTokenMiddleware


class TokenRegistryTests(unittest.TestCase):
    def setUp(self):
        self.member_token = "member-token-for-tests"
        self.admin_token = "tenant-admin-token-for-tests"
        self.registry_json = json.dumps({
            TokenRegistry.digest(self.member_token): {
                "subject": "member-17",
                "tenant_id": "tenant-a",
                "roles": ["member"],
            },
            TokenRegistry.digest(self.admin_token): {
                "subject": "admin-17",
                "tenant_id": "tenant-a",
                "roles": ["admin"],
            },
        })

    def test_registry_resolves_token_to_server_owned_principal(self):
        registry = TokenRegistry.from_json(self.registry_json)
        principal = registry.authenticate(self.member_token)
        self.assertEqual(principal, Principal("member-17", "tenant-a", frozenset({"member"})))

    def test_unknown_token_is_rejected(self):
        registry = TokenRegistry.from_json(self.registry_json)
        self.assertIsNone(registry.authenticate("not-in-registry"))

    def test_registry_rejects_raw_tokens_as_keys(self):
        with self.assertRaises(ValueError):
            TokenRegistry({"raw-token": {
                "subject": "u", "tenant_id": "t", "roles": ["member"]
            }})

    def test_registry_rejects_unknown_roles(self):
        digest = TokenRegistry.digest("x")
        with self.assertRaises(ValueError):
            TokenRegistry({digest: {
                "subject": "u", "tenant_id": "t", "roles": ["owner"]
            }})

    def test_malformed_registry_fails_closed_at_initialization(self):
        with patch.dict("os.environ", {"API_TOKEN_REGISTRY": "not-json"}):
            with self.assertRaises(ValueError):
                ApiTokenMiddleware(lambda environ, start: [])

    def test_registry_token_attaches_principal_not_client_tenant(self):
        registry = TokenRegistry.from_json(self.registry_json)
        calls = []

        def application(environ, start_response):
            calls.append(principal_from_environ(environ))
            start_response("200 OK", [])
            return [b"ok"]

        middleware = ApiTokenMiddleware(application, token="", token_registry=registry)
        environ = {
            "PATH_INFO": "/api/network",
            "HTTP_AUTHORIZATION": "Bearer " + self.member_token,
            "HTTP_X_TENANT_ID": "tenant-victim",
            "QUERY_STRING": "tenant_id=tenant-victim",
        }
        result = {}

        def start_response(status, headers, exc_info=None):
            result["status"] = status

        b"".join(middleware(environ, start_response))
        self.assertEqual(result["status"], "200 OK")
        self.assertEqual(calls[0].tenant_id, "tenant-a")
        self.assertEqual(calls[0].subject, "member-17")

    def test_registry_only_mode_works_without_legacy_token(self):
        registry = TokenRegistry.from_json(self.registry_json)
        middleware = ApiTokenMiddleware(lambda env, start: [b"ok"], token="", token_registry=registry)
        environ = {"PATH_INFO": "/"}
        result = {}

        def start_response(status, headers, exc_info=None):
            result["status"] = status

        environ["HTTP_AUTHORIZATION"] = "Bearer " + self.admin_token
        self.assertEqual(b"".join(middleware(environ, start_response)), b"ok")
        self.assertEqual(result["status"], "200 OK")


class GlobalGraphAuthorizationTests(unittest.TestCase):
    class FakeGraph:
        def __init__(self):
            from threading import RLock
            self.lock = RLock()
            self.dane = {"neurons": {"secret": {"label": "private"}}, "synapses": []}

        def laduj(self):
            return None

    def make_client(self, principal):
        app = Flask(__name__)
        app.register_blueprint(create_api_blueprint(self.FakeGraph()))

        @app.before_request
        def attach_principal():
            from flask import request
            if principal is not None:
                request.environ[PRINCIPAL_ENV_KEY] = principal

        return app.test_client()

    def test_member_cannot_read_global_graph(self):
        member = Principal("member-1", "tenant-a", frozenset({"member"}))
        response = self.make_client(member).get("/api/network")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b"private", response.data)

    def test_tenant_admin_can_read_global_graph(self):
        admin = Principal("admin-1", "tenant-a", frozenset({"admin"}))
        response = self.make_client(admin).get("/api/network")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"private", response.data)

    def test_health_remains_public(self):
        response = self.make_client(None).get("/health")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
