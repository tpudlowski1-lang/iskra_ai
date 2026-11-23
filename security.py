"""Fail-closed WSGI authentication for public Iskra deployments."""
import base64
import hmac
import json
import os
import sqlite3

from iskra.security.credentials import SQLiteCredentialStore
from iskra.security.principal import SYSTEM_ADMIN, PRINCIPAL_ENV_KEY, Principal


class ApiTokenMiddleware:
    def __init__(self, application, token=None, credential_store=None):
        self.application = application
        self.token = token if token is not None else os.environ.get("API_TOKEN", "")
        self.credential_store = credential_store
        database_path = os.environ.get("CREDENTIAL_DB_PATH", "")
        if self.credential_store is None and database_path:
            self.credential_store = SQLiteCredentialStore(database_path)
        self.principal = SYSTEM_ADMIN

    @staticmethod
    def _provided_token(environ):
        authorization = environ.get("HTTP_AUTHORIZATION", "")
        scheme, separator, credentials = authorization.partition(" ")
        if separator and scheme.lower() == "bearer":
            return credentials.strip()
        if separator and scheme.lower() == "basic":
            try:
                decoded = base64.b64decode(credentials.strip(), validate=True).decode("utf-8")
                _username, colon, password = decoded.partition(":")
                return password if colon else ""
            except (ValueError, UnicodeDecodeError):
                return ""
        return environ.get("HTTP_X_API_TOKEN", "")

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
        if environ.get("PATH_INFO", "/") == "/health":
            return self.application(environ, start_response)

        if not self.token and self.credential_store is None:
            return self._response(
                start_response, "503 Service Unavailable",
                {"error": "service_not_configured", "message": "Configure API_TOKEN or CREDENTIAL_DB_PATH."},
            )

        supplied = self._provided_token(environ)
        principal = None
        if supplied and self.credential_store is not None:
            try:
                principal = self.credential_store.authenticate(supplied)
            except (OSError, sqlite3.Error):
                # Credential storage failures must never fall back to anonymous access.
                return self._response(
                    start_response, "503 Service Unavailable",
                    {"error": "authentication_unavailable"},
                )

        if principal is None and supplied and self.token and hmac.compare_digest(supplied, self.token):
            # Backward compatibility: the legacy shared token maps to the
            # system administrator until it is explicitly retired.
            principal = self.principal

        if not isinstance(principal, Principal):
            return self._response(
                start_response, "401 Unauthorized",
                {"error": "unauthorized", "message": "Valid API token required."},
                [("WWW-Authenticate", 'Basic realm="Iskra AI", charset="UTF-8"')],
            )

        def secured_start_response(status, headers, exc_info=None):
            headers = list(headers)
            existing = {name.lower() for name, _ in headers}
            for name, value in [
                ("X-Content-Type-Options", "nosniff"),
                ("X-Frame-Options", "DENY"),
                ("Referrer-Policy", "no-referrer"),
                ("Cache-Control", "no-store"),
            ]:
                if name.lower() not in existing:
                    headers.append((name, value))
            return start_response(status, headers, exc_info)

        # Principal and tenant scope come exclusively from the credential store.
        # Client-provided identity fields are never read or trusted.
        environ[PRINCIPAL_ENV_KEY] = principal
        return self.application(environ, secured_start_response)
