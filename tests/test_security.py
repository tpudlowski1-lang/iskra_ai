import base64
import json
import unittest

from security import ApiTokenMiddleware


class ApiTokenMiddlewareTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def application(environ, start_response):
            self.calls.append(environ["PATH_INFO"])
            start_response("200 OK", [("Content-Type", "text/plain")])
            return [b"ok"]

        self.application = application

    def request(self, middleware, path="/api/network", headers=None):
        environ = {"PATH_INFO": path, "REQUEST_METHOD": "GET"}
        environ.update(headers or {})
        result = {}

        def start_response(status, response_headers, exc_info=None):
            result["status"] = status
            result["headers"] = dict(response_headers)

        result["body"] = b"".join(middleware(environ, start_response))
        return result

    def test_health_is_public_without_token(self):
        response = self.request(ApiTokenMiddleware(self.application, token=""), path="/health")
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(self.calls, ["/health"])

    def test_missing_server_token_fails_closed(self):
        response = self.request(ApiTokenMiddleware(self.application, token=""))
        self.assertEqual(response["status"], "503 Service Unavailable")
        self.assertEqual(json.loads(response["body"])["error"], "service_not_configured")
        self.assertEqual(self.calls, [])

    def test_missing_client_token_is_rejected(self):
        response = self.request(ApiTokenMiddleware(self.application, token="secret"))
        self.assertEqual(response["status"], "401 Unauthorized")
        self.assertIn("WWW-Authenticate", response["headers"])
        self.assertEqual(self.calls, [])

    def test_bearer_token_is_accepted(self):
        response = self.request(
            ApiTokenMiddleware(self.application, token="secret"),
            headers={"HTTP_AUTHORIZATION": "Bearer secret"},
        )
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["headers"]["X-Content-Type-Options"], "nosniff")

    def test_x_api_token_is_accepted(self):
        response = self.request(
            ApiTokenMiddleware(self.application, token="secret"),
            headers={"HTTP_X_API_TOKEN": "secret"},
        )
        self.assertEqual(response["status"], "200 OK")

    def test_basic_password_is_accepted_for_browser_dashboard(self):
        credentials = base64.b64encode(b"iskra:secret").decode("ascii")
        response = self.request(
            ApiTokenMiddleware(self.application, token="secret"),
            path="/",
            headers={"HTTP_AUTHORIZATION": "Basic " + credentials},
        )
        self.assertEqual(response["status"], "200 OK")

    def test_wrong_token_is_rejected(self):
        response = self.request(
            ApiTokenMiddleware(self.application, token="secret"),
            headers={"HTTP_AUTHORIZATION": "Bearer wrong"},
        )
        self.assertEqual(response["status"], "401 Unauthorized")
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
