import os
import unittest

from werkzeug.test import Client
from werkzeug.wrappers import Response

os.environ["ISKRA_TESTING"] = "true"
import wsgi


class WsgiEntrypointTests(unittest.TestCase):
    def test_wsgi_entrypoint_imports_and_exposes_health_route(self):
        client = Client(wsgi.app, Response)
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

    def test_wsgi_entrypoint_fails_closed_for_private_routes_when_unconfigured(self):
        client = Client(wsgi.app, Response)
        response = client.get("/api/network")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "service_not_configured")


if __name__ == "__main__":
    unittest.main(verbosity=2)
