"""Fail-closed WSGI authentication for public Iskra deployments."""
import base64
import hmac
import json
import os

from iskra.security.principal import SYSTEM_ADMIN, PRINCIPAL_ENV_KEY
from iskra.security.token_registry import TokenRegistry


class ApiTokenMiddleware:
    def __init__(self, application, token=None, token_registry=None):
        self.application = application
        self.token = token if token is not None else os.environ.get("API_TOKEN", "")
        raw_registry = os.environ.get("API_TOKEN_REGISTRY", "")
        if token_registry is not None:
            self.token_registry = token_registry
        elif raw_registry:
            # Invalid security configuration must stop startup, not silently
            # downgrade the service to a weaker authentication mode.
            self.token_registry = TokenRegistry.from_json(raw_registry)
        else:
            self.token_registry = TokenRegistry({})
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

        if not self.token and not self.token_registry._entries:
            return self._response(
                start_response, "503 Service Unavailable",
                {"error": "service_not_configured", "message": "Administrator must configure API_TOKEN or API_TOKEN_REGISTRY."},
            )

        supplied = self._provided_token(environ)
        principal = self.token_registry.authenticate(supplied)
        if principal is None and self.token and supplied and hmac.compare_digest(supplied, self.token):
            # Backward compatibility: the legacy shared token remains a single
            # system administrator credential until explicitly retired.
            principal = self.principal

        if principal is None:
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

        # Identity comes exclusively from the validated server-side registry.
        # Client-provided tenant IDs and role headers are never consulted.
        environ[PRINCIPAL_ENV_KEY] = principal
        return self.application(environ, secured_start_response)
