"""Fail-closed WSGI authentication for public Iskra deployments."""
import base64
import hashlib
import hmac
import json
import os
from http.cookies import CookieError, SimpleCookie
from urllib.parse import urlsplit

from iskra.security.credentials import (
    CredentialConfigError,
    load_api_credentials,
    principal_for_token,
)
from iskra.security.principal import (
    BROWSER_SESSION_COOKIE_NAME,
    BROWSER_SESSION_CSRF_DIGEST_ENV_KEY,
    BROWSER_SESSION_CSRF_TOKEN_ENV_KEY,
    BROWSER_SESSION_TOKEN_ENV_KEY,
    PRINCIPAL_CREDENTIAL_ID_ENV_KEY,
    PRINCIPAL_ENV_KEY,
    SYSTEM_ADMIN,
    Principal,
)


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
    def _provided_token_details(environ):
        authorization = environ.get("HTTP_AUTHORIZATION", "")
        scheme, separator, credentials = authorization.partition(" ")
        if separator and scheme.lower() == "bearer":
            return credentials.strip(), "bearer"
        if separator and scheme.lower() == "basic":
            try:
                decoded = base64.b64decode(credentials.strip(), validate=True).decode("utf-8")
                _username, colon, password = decoded.partition(":")
                return (password if colon else ""), "basic"
            except (ValueError, UnicodeDecodeError):
                return "", "basic"
        token = environ.get("HTTP_X_API_TOKEN", "")
        return token, "header" if token else ""

    @staticmethod
    def _provided_token(environ):
        return ApiTokenMiddleware._provided_token_details(environ)[0]

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

    @staticmethod
    def _browser_session_cookie(environ):
        cookie_header = environ.get("HTTP_COOKIE", "")
        if not isinstance(cookie_header, str) or not cookie_header:
            return ""
        cookies = SimpleCookie()
        try:
            cookies.load(cookie_header)
        except CookieError:
            return ""
        morsel = cookies.get(BROWSER_SESSION_COOKIE_NAME)
        return morsel.value if morsel is not None else ""

    @staticmethod
    def _is_public_shell_request(environ):
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = environ.get("PATH_INFO", "/")
        return method in {"GET", "HEAD"} and path in {
            "/assistant",
            "/static/assistant.css",
            "/static/assistant.js",
        }

    def __call__(self, environ, start_response):
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

        if environ.get("PATH_INFO", "/") == "/health" or self._is_public_shell_request(environ):
            return self.application(environ, secured_start_response)

        if self.configuration_error:
            return self._response(
                start_response,
                "503 Service Unavailable",
                {"error": "service_not_configured", "message": "Invalid server-side credential configuration."},
            )

        if not self.token and not self.credentials and self.credential_store is None:
            return self._response(
                start_response,
                "503 Service Unavailable",
                {"error": "service_not_configured", "message": "Administrator must configure API_TOKEN or ISKRA_API_CREDENTIALS_JSON."},
            )

        supplied, supplied_scheme = self._provided_token_details(environ)
        principal = None
        credential_id = None
        browser_session_token = ""
        browser_session = None

        if supplied and self.credential_store is not None:
            try:
                authenticated = None
                if hasattr(self.credential_store, "authenticate_with_metadata"):
                    authenticated = self.credential_store.authenticate_with_metadata(supplied)
                if authenticated is not None:
                    principal, credential_id = authenticated
                else:
                    candidate = self.credential_store.authenticate(supplied)
                    if isinstance(candidate, Principal):
                        principal = candidate
                    elif candidate is not None:
                        principal = None
            except Exception:
                return self._response(
                    start_response,
                    "503 Service Unavailable",
                    {"error": "authentication_unavailable", "message": "Credential verification is temporarily unavailable."},
                )
            if principal is None and self.token and hmac.compare_digest(supplied, self.token):
                principal = SYSTEM_ADMIN
            elif principal is None:
                principal = principal_for_token(supplied, self.credentials)
        elif supplied and self.token and hmac.compare_digest(supplied, self.token):
            principal = SYSTEM_ADMIN
        elif supplied:
            principal = principal_for_token(supplied, self.credentials)
        else:
            browser_session_token = self._browser_session_cookie(environ)
            if browser_session_token and self.credential_store is not None:
                try:
                    browser_session = self.credential_store.authenticate_browser_session(browser_session_token)
                except Exception:
                    return self._response(
                        start_response,
                        "503 Service Unavailable",
                        {"error": "authentication_unavailable", "message": "Browser session verification is temporarily unavailable."},
                    )
                if browser_session is not None:
                    principal = browser_session.principal

        if principal is None:
            return self._response(
                start_response,
                "401 Unauthorized",
                {"error": "unauthorized", "message": "Valid API credential or browser session required."},
                [("WWW-Authenticate", 'Basic realm="Iskra AI", charset="UTF-8"')],
            )

        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        if supplied_scheme == "basic" and method not in {"GET", "HEAD", "OPTIONS"}:
            fetch_site = str(environ.get("HTTP_SEC_FETCH_SITE", "")).lower()
            origin = environ.get("HTTP_ORIGIN", "")
            host = str(environ.get("HTTP_HOST", "")).lower()
            try:
                origin_host = urlsplit(origin).netloc.lower() if origin else ""
            except ValueError:
                origin_host = ""
            if fetch_site == "cross-site" or not host or origin_host != host:
                return self._response(
                    start_response, "403 Forbidden",
                    {"error": "csrf_rejected", "message": "Basic-authenticated browser mutations require a same-origin request."},
                )

        if browser_session is not None:
            if method not in {"GET", "HEAD", "OPTIONS"}:
                fetch_site = str(environ.get("HTTP_SEC_FETCH_SITE", "")).lower()
                origin = environ.get("HTTP_ORIGIN", "")
                host = str(environ.get("HTTP_HOST", "")).lower()
                if fetch_site == "cross-site":
                    return self._response(
                        start_response, "403 Forbidden",
                        {"error": "csrf_rejected", "message": "Cross-site browser requests are not allowed."},
                    )
                if origin:
                    try:
                        origin_host = urlsplit(origin).netloc.lower()
                    except ValueError:
                        origin_host = ""
                    if not host or origin_host != host:
                        return self._response(
                            start_response, "403 Forbidden",
                            {"error": "csrf_rejected", "message": "Request origin does not match this host."},
                        )
                csrf_token = environ.get("HTTP_X_CSRF_TOKEN", "")
                csrf_digest = (
                    hashlib.sha256(csrf_token.encode("utf-8")).hexdigest()
                    if isinstance(csrf_token, str) and csrf_token else ""
                )
                if not csrf_digest or not hmac.compare_digest(csrf_digest, browser_session.csrf_digest):
                    return self._response(
                        start_response, "403 Forbidden",
                        {"error": "csrf_rejected", "message": "A valid CSRF token is required."},
                    )

        # Principal and credential/session identifiers are installed only by
        # this middleware; request bodies and tenant headers are never trusted.
        environ[PRINCIPAL_ENV_KEY] = principal
        if credential_id:
            environ[PRINCIPAL_CREDENTIAL_ID_ENV_KEY] = credential_id
        if browser_session is not None:
            environ[BROWSER_SESSION_TOKEN_ENV_KEY] = browser_session_token
            environ[BROWSER_SESSION_CSRF_DIGEST_ENV_KEY] = browser_session.csrf_digest
            environ[BROWSER_SESSION_CSRF_TOKEN_ENV_KEY] = browser_session.csrf_token
        return self.application(environ, secured_start_response)
