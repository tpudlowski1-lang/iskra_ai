"""Regression tests for tenant-aware rate limiting."""
import unittest

from flask import Flask

from iskra.security.principal import PRINCIPAL_ENV_KEY, Principal
from iskra.security.rate_limit import create_rate_limiter, rate_limit_key


class RateLimitKeyTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def test_authenticated_key_uses_server_derived_tenant(self):
        principal = Principal("alice", "tenant-alpha", frozenset({"member"}))
        with self.app.test_request_context(
            "/",
            headers={"X-Tenant-ID": "tenant-attacker"},
            environ_overrides={PRINCIPAL_ENV_KEY: principal},
        ):
            self.assertEqual(rate_limit_key(), "tenant:tenant-alpha")

    def test_untrusted_tenant_header_does_not_change_fallback_key(self):
        with self.app.test_request_context(
            "/",
            headers={"X-Tenant-ID": "tenant-attacker"},
            environ_overrides={"REMOTE_ADDR": "192.0.2.10"},
        ):
            self.assertEqual(rate_limit_key(), "192.0.2.10")

    def test_missing_principal_uses_remote_address(self):
        with self.app.test_request_context("/", environ_overrides={"REMOTE_ADDR": "192.0.2.11"}):
            self.assertEqual(rate_limit_key(), "192.0.2.11")


class RateLimitBehaviorTests(unittest.TestCase):
    def test_explicit_test_environment_disables_application_limiter(self):
        app = Flask(__name__)
        create_rate_limiter(app, environ={"ISKRA_TESTING": "true"})
        self.assertIs(app.config["RATELIMIT_ENABLED"], False)

    def test_default_limiter_returns_429_after_configured_limit(self):
        app = Flask(__name__)
        create_rate_limiter(app, environ={}, default_limits=["2 per minute"])

        @app.get("/resource")
        def resource():
            return {"ok": True}

        client = app.test_client()
        self.assertEqual(client.get("/resource").status_code, 200)
        self.assertEqual(client.get("/resource").status_code, 200)
        self.assertEqual(client.get("/resource").status_code, 429)

    def test_explicit_disable_skips_global_limiter(self):
        app = Flask(__name__)
        self.assertIsNone(create_rate_limiter(
            app, environ={"ISKRA_RATE_LIMIT_ENABLED": "false"}
        ))

    def test_invalid_enabled_flag_is_rejected(self):
        app = Flask(__name__)
        with self.assertRaises(ValueError):
            create_rate_limiter(app, environ={"ISKRA_RATE_LIMIT_ENABLED": "sometimes"})

    def test_empty_storage_uri_is_rejected(self):
        app = Flask(__name__)
        with self.assertRaises(ValueError):
            create_rate_limiter(app, environ={"RATELIMIT_STORAGE_URI": ""})


if __name__ == "__main__":
    unittest.main(verbosity=2)
