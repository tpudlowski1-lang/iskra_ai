import unittest

from flask import Flask

from iskra.api.routes import create_api_blueprint
from iskra.security.principal import PRINCIPAL_ENV_KEY, Principal, SYSTEM_ADMIN


class FakeGraph:
    def __init__(self):
        from threading import RLock
        self.lock = RLock()
        self.dane = {"neurons": {"secret": {"label": "private"}}, "synapses": []}

    def laduj(self):
        return None


class GlobalGraphBoundaryTests(unittest.TestCase):
    def make_client(self, principal):
        app = Flask(__name__)
        app.register_blueprint(create_api_blueprint(FakeGraph()))

        @app.before_request
        def attach_principal():
            from flask import request
            if principal is not None:
                request.environ[PRINCIPAL_ENV_KEY] = principal

        return app.test_client()

    def test_request_without_principal_is_denied(self):
        response = self.make_client(None).get("/api/network")
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(b"private", response.data)

    def test_member_cannot_read_global_graph(self):
        member = Principal("member-1", "tenant-a", frozenset({"member"}))
        response = self.make_client(member).get("/api/network")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b"private", response.data)

    def test_tenant_admin_cannot_read_global_graph(self):
        tenant_admin = Principal("admin-1", "tenant-a", frozenset({"admin"}))
        response = self.make_client(tenant_admin).get("/api/network")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b"private", response.data)

    def test_only_system_admin_can_read_global_graph(self):
        response = self.make_client(SYSTEM_ADMIN).get("/api/network")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"private", response.data)

    def test_health_remains_public(self):
        response = self.make_client(None).get("/health")
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
