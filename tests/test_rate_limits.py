import unittest

from app import app, _rate_limit_identity


class RateLimitIdentityTests(unittest.TestCase):
    def test_authenticated_tenant_is_the_rate_limit_identity(self):
        with app.test_request_context(
            "/api/chat",
            environ_overrides={"iskra.tenant_id": "tenant-123", "REMOTE_ADDR": "192.0.2.1"},
        ):
            self.assertEqual(_rate_limit_identity(), "tenant:tenant-123")

    def test_admin_falls_back_to_client_ip_identity(self):
        with app.test_request_context(
            "/admin/tenants",
            environ_overrides={"REMOTE_ADDR": "192.0.2.55"},
        ):
            self.assertEqual(_rate_limit_identity(), "192.0.2.55")


if __name__ == "__main__":
    unittest.main(verbosity=2)
