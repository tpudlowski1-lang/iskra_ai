import os
import tempfile
import unittest

from flask import Flask

from iskra.security.sqlite_credentials import SQLiteCredentialStore

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

    def test_wsgi_factory_injects_persistent_credential_store_into_flask_config(self):
        with tempfile.TemporaryDirectory() as directory:
            application = Flask("tenant-account-wsgi-test")
            middleware = wsgi.create_wsgi_app(
                application,
                environ={
                    "ISKRA_CREDENTIAL_DB_PATH": os.path.join(directory, "private", "credentials.sqlite3"),
                    "API_TOKEN": "",
                    "ISKRA_API_CREDENTIALS_JSON": "",
                },
            )
            self.assertIsInstance(
                application.config["ISKRA_CREDENTIAL_STORE"],
                SQLiteCredentialStore,
            )
            self.assertIsNotNone(middleware)

    def test_wsgi_factory_sets_missing_credential_store_to_none(self):
        application = Flask("tenant-account-no-store-test")
        wsgi.create_wsgi_app(
            application,
            environ={"ISKRA_CREDENTIAL_DB_PATH": "", "API_TOKEN": "", "ISKRA_API_CREDENTIALS_JSON": ""},
        )
        self.assertIsNone(application.config["ISKRA_CREDENTIAL_STORE"])

    def test_wsgi_entrypoint_fails_closed_for_private_routes_when_unconfigured(self):
        client = Client(wsgi.app, Response)
        response = client.get("/api/network")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "service_not_configured")


if __name__ == "__main__":
    unittest.main(verbosity=2)
