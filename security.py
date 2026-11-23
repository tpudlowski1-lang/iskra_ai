"""Fail-closed WSGI authentication for public Iskra deployments."""
import base64
import hmac
import json
import os

from iskra.security.credentials import (
    CredentialConfigError,
    load_api_credentials,
    principal_for_token,
)
from iskra.security.principal import SYSTEM_ADMIN, PRINCIPAL_ENV_KEY, Principal


class ApiTokenMiddleware:
    def __init__(self, application, token=None, credentials_json=None, credential_store=None):
        self.application = application
        self.credential_store = credential_store
        self.token = token if token is not None else os.environ.get("API_TOKEN", "")
        raw_credentials = (
            credentials_json
            if credentials_json is not None
            else os.environ.get("ISKRA_API_CREDENTIALS_JSON", "")
        )
        try:
            self.credentials = load_api_credentials(raw_credentials)
            self.configuration_error = False
        except CredentialConfigError:
            self.credentials = {}
            self.configuration_error = True

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

        if self.configuration_error:
            return self._response(
                start_response,
                "503 Service Unavailable",
                {"error": "service_not_configured", "message": "Invalid server-side credential configuration."},
            )

        if not self.token and not self.credentials:
            return self._response(
                start_response,
                "503 Service Unavailable",
                {"error": "service_not_configured", "message": "Administrator must configure API_TOKEN or ISKRA_API_CREDENTIALS_JSON."},
            )

        supplied = self._provided_token(environ)
        principal = None
        if supplied and self.credential_store is not None:
            try:
                candidate = self.credential_store.authenticate(supplied)
            except Exception:
                return self._response(
                    start_response,
                    "503 Service Unavailable",
                    {"error": "authentication_unavailable", "message": "Credential verification is temporarily unavailable."},
                )
            if isinstance(candidate, Principal):
                principal = candidate
            elif candidate is not None:
                # Never trust a backend that returns an untyped identity object.
                principal = None
            elif self.token and hmac.compare_digest(supplied, self.token):
                principal = SYSTEM_ADMIN
        elif supplied and self.token and hmac.compare_digest(supplied, self.token):
            principal = SYSTEM_ADMIN
        elif supplied:
            principal = principal_for_token(supplied, self.credentials)

        if principal is None:
            return self._response(
                start_response,
                "401 Unauthorized",
                {"error": "unauthorized", "message": "Valid API credential required."},
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

        # Principal is derived only from a verified server-side credential.
        # Request body, query parameters and caller-supplied tenant headers are ignored.
        environ[PRINCIPAL_ENV_KEY] = principal
        return self.application(environ, secured_start_response)
