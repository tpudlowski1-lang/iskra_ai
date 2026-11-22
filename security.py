"""Fail-closed WSGI authentication for Iskra administrator and tenant API keys."""
import base64
import hmac
import json
import os

import knowledge


class ApiTokenMiddleware:
    TENANT_PATHS = ("/api/documents", "/api/search")

    def __init__(self, application, token=None, data_dir=None):
        self.application = application
        self.token = token if token is not None else os.environ.get("API_TOKEN", "")
        self.data_dir = os.path.abspath(data_dir or os.environ.get("DATA_DIR", os.path.dirname(__file__)))

    def _secured_application(self, environ, start_response):
        def secured_start_response(status, headers, exc_info=None):
            headers = list(headers)
            existing = {name.lower() for name, _ in headers}
            for name, value in (
                ("X-Content-Type-Options", "nosniff"),
                ("X-Frame-Options", "DENY"),
                ("Referrer-Policy", "no-referrer"),
                ("Cache-Control", "no-store"),
            ):
                if name.lower() not in existing:
                    headers.append((name, value))
            return start_response(status, headers, exc_info)
        return self.application(environ, secured_start_response)

    @staticmethod
    def _response(start_response, status, payload, extra_headers=()):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "no-referrer"),
        ]
        headers.extend(extra_headers)
        start_response(status, headers)
        return [body]

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "/")
        if path == "/health":
            return self.application(environ, start_response)

        authorization = environ.get("HTTP_AUTHORIZATION", "")
        scheme, separator, credentials = authorization.partition(" ")
        admin_token = ""
        if separator and scheme.lower() == "bearer":
            admin_token = credentials.strip()
        elif separator and scheme.lower() == "basic":
            try:
                decoded = base64.b64decode(credentials.strip(), validate=True).decode("utf-8")
                _username, colon, password = decoded.partition(":")
                admin_token = password if colon else ""
            except (ValueError, UnicodeDecodeError):
                admin_token = ""
        if not admin_token:
            admin_token = environ.get("HTTP_X_API_TOKEN", "")
        if self.token and admin_token and hmac.compare_digest(admin_token, self.token):
            environ["iskra.auth_role"] = "admin"
            return self._secured_application(environ, start_response)

        tenant_key = environ.get("HTTP_X_ISKRA_TENANT_KEY", "")
        if tenant_key and any(path == prefix or path.startswith(prefix + "/")
                              for prefix in self.TENANT_PATHS):
            tenant_id = knowledge.authenticate_tenant_key(
                os.path.join(self.data_dir, "iskra_knowledge.sqlite3"), tenant_key
            )
            if tenant_id:
                environ["iskra.auth_role"] = "tenant"
                environ["iskra.tenant_id"] = tenant_id
                return self._secured_application(environ, start_response)

        if not self.token:
            return self._response(
                start_response, "503 Service Unavailable",
                {"error": "service_not_configured",
                 "message": "Administrator must configure API_TOKEN."},
            )
        return self._response(
            start_response, "401 Unauthorized",
            {"error": "unauthorized", "message": "Valid administrator or tenant key required."},
            [("WWW-Authenticate", 'Bearer realm="Iskra AI"')],
        )
