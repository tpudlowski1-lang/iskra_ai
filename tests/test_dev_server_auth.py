import unittest

from werkzeug.test import Client
from werkzeug.wrappers import Response

import app as iskra_app


class DevelopmentEntrypointSecurityTests(unittest.TestCase):
    def test_direct_development_wsgi_is_fail_closed_without_mutating_flask_app(self):
        original_wsgi = iskra_app.app.wsgi_app
        secured_wsgi = iskra_app.create_development_wsgi_app(environ={})
        self.assertIs(iskra_app.app.wsgi_app, original_wsgi)

        client = Client(secured_wsgi, Response)
        health = client.get("/health")
        self.assertEqual(health.status_code, 200)

        private = client.get("/api/network")
        self.assertEqual(private.status_code, 503)
        self.assertEqual(private.get_json()["error"], "service_not_configured")


if __name__ == "__main__":
    unittest.main(verbosity=2)
