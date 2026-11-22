import unittest


class WsgiEntrypointTests(unittest.TestCase):
    def test_wsgi_entrypoint_imports_and_exposes_health_route(self):
        import wsgi

        response = wsgi.app.test_client().get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")


if __name__ == "__main__":
    unittest.main(verbosity=2)
