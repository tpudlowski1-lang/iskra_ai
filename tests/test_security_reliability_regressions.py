"""Security and reliability regression tests for the Iskra core."""
import unittest
from flask import Flask, jsonify
from iskra.security.policy import require_roles, require_system_admin
from iskra.security.principal import PRINCIPAL_ENV_KEY, Principal, SYSTEM_ADMIN
from iskra.llm.router import RouterProvider

class AuthorizationBoundaryTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        @app.get("/member")
        @require_roles("member")
        def member_route():
            return jsonify({"ok": True})
        @app.get("/system")
        @require_system_admin
        def system_route():
            return jsonify({"ok": True})
        self.client = app.test_client()

    def test_missing_principal_returns_401(self):
        self.assertEqual(self.client.get("/member").status_code, 401)

    def test_wrong_role_returns_403(self):
        response = self.client.get("/member", environ_overrides={
            PRINCIPAL_ENV_KEY: Principal("user", "tenant-1", frozenset({"admin"}))
        })
        self.assertEqual(response.status_code, 403)

    def test_member_role_passes(self):
        response = self.client.get("/member", environ_overrides={
            PRINCIPAL_ENV_KEY: Principal("user", "tenant-1", frozenset({"member"}))
        })
        self.assertEqual(response.status_code, 200)

    def test_admin_outside_system_tenant_is_denied(self):
        response = self.client.get("/system", environ_overrides={
            PRINCIPAL_ENV_KEY: Principal("admin", "tenant-1", frozenset({"admin"}))
        })
        self.assertEqual(response.status_code, 403)

    def test_system_admin_is_allowed(self):
        response = self.client.get("/system", environ_overrides={
            PRINCIPAL_ENV_KEY: SYSTEM_ADMIN
        })
        self.assertEqual(response.status_code, 200)

class RouterResilienceTests(unittest.TestCase):
    def test_provider_exception_does_not_break_fallback(self):
        router = RouterProvider()
        calls = []
        from iskra.llm.router import _ACTIVE_DEADLINE
        def broken(_):
            calls.append(("primary", _ACTIVE_DEADLINE.get()))
            raise TimeoutError("simulated provider timeout")
        router.primary = "deepseek"
        router.fallbacks = ["openai"]
        router.allowed_providers = {"deepseek", "openai"}
        router.providers = {
            "deepseek": broken,
            "openai": lambda _: calls.append(("fallback", _ACTIVE_DEADLINE.get())) or '{"answer": "ok"}',
        }
        self.assertEqual(router.generate("hello"), '{"answer": "ok"}')
        self.assertEqual([item[0] for item in calls], ["primary", "fallback"])
        self.assertEqual(calls[0][1], calls[1][1])

    def test_all_provider_exceptions_return_none(self):
        router = RouterProvider()
        router.primary = "first"
        router.fallbacks = ["second"]
        router.providers = {
            "first": lambda _: (_ for _ in ()).throw(ConnectionError()),
            "second": lambda _: (_ for _ in ()).throw(RuntimeError()),
        }
        self.assertIsNone(router.generate("hello"))


    def test_expired_shared_deadline_stops_before_calling_provider(self):
        router = RouterProvider()
        calls = []
        router.primary = "primary"
        router.fallbacks = []
        router.providers = {
            "primary": lambda prompt: calls.append(prompt) or '{"ok": true}',
        }
        from unittest.mock import patch
        with patch("iskra.llm.router.time.monotonic", side_effect=[0.0, 101.0]):
            self.assertIsNone(router.generate("hello"))
        self.assertEqual(calls, [])

    def test_request_timeouts_are_bounded_by_remaining_deadline(self):
        router = RouterProvider()
        from unittest.mock import patch
        with patch("iskra.llm.router.time.monotonic", return_value=10.0):
            timeout = router._request_timeout(15.0)
        self.assertIsNotNone(timeout)
        self.assertGreater(timeout[0], 0)
        self.assertGreater(timeout[1], 0)
        self.assertLessEqual(sum(timeout), 5.0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
