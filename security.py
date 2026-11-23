"""Fail-closed WSGI authentication for public Iskra deployments."""
import base64
import hmac
import json
import os

from iskra.security.principal import PRINCIPAL_ENV_KEY, SYSTEM_ADMIN


class ApiTokenMiddleware:
    def __init__(self, application, token=None, credential_store=None):
        self.application = application
        self.token = token if token is not None else os.environ.get("API_TOKEN", "")
        self.credential_store = credential_store

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

    def _authenticate(self, supplied):
        """Resolve identity only from a verified registry record or legacy admin token."""
        if supplied and self.credential_store is not None:
            try:
                principal = self.credential_store.authenticate(supplied)
            except Exception:
                # A credential backend failure must never downgrade to unauthenticated access.
                return None, "unavailable"
            if principal is not None:
                return principal, None

        if supplied and self.token and hmac.compare_digest(supplied, self.token):
            return SYSTEM_ADMIN, None
        return None, None

    def __call__(self, environ, start_response):
        if environ.get("PATH_INFO", "/") == "/health":
            return self.application(environ, start_response)

        if not self.token and self.credential_store is None:
            return self._response(
                start_response,
                "503 Service Unavailable",
                {"error": "service_not_configured", "message": "Configure API_TOKEN or a credential store."},
            )

        supplied = self._provided_token(environ)
        principal, auth_error = self._authenticate(supplied)
        if auth_error == "unavailable":
            return self._response(
                start_response,
                "503 Service Unavailable",
                {"error": "authentication_unavailable", "message": "Credential verification is temporarily unavailable."},
            )
        if principal is None:
            return self._response(
                start_response,
                "401 Unauthorized",
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

        # Only verified server-side credentials can install a request principal.
        # Tenant IDs in query/body/headers are ignored by this authentication layer.
        environ[PRINCIPAL_ENV_KEY] = principal
        return self.application(environ, secured_start_response)
