import os
import unittest

os.environ["ENABLE_AUTONOMOUS_LOOP"] = "false"
import app as iskra


class SecurityBaselineTests(unittest.TestCase):
    def test_dashboard_does_not_use_inner_html_for_graph_data(self):
        response = iskra.app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertNotIn("innerHTML", html)
        self.assertIn("textContent", html)
        self.assertIn("replaceChildren", html)

    def test_security_headers_are_present(self):
        response = iskra.app.test_client().get("/health")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("Referrer-Policy"), "no-referrer")
        self.assertIn("frame-ancestors 'none'", response.headers.get("Content-Security-Policy", ""))
        self.assertIn("object-src 'none'", response.headers.get("Content-Security-Policy", ""))

    def test_api_response_also_receives_security_headers(self):
        response = iskra.app.test_client().get("/api/network")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")


if __name__ == "__main__":
    unittest.main(verbosity=2)
