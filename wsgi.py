"""Production WSGI entry point with fail-closed authentication.

Use `wsgi:app` (not `app:app`) for public deployments so every non-health
request passes through the authentication middleware.
"""
import os

from iskra.security.store_config import credential_store_from_env
from security import ApiTokenMiddleware
from werkzeug.middleware.proxy_fix import ProxyFix


def create_wsgi_app(application=None, environ=None):
    """Wrap a Flask application using the supplied server environment.

    The factory is injectable so production wiring can be integration-tested
    without mutating the process environment or importing a global Flask app.
    """
    env = os.environ if environ is None else environ
    if application is None:
        from app import app as application

    credential_store = credential_store_from_env(env)
    application.config["ISKRA_CREDENTIAL_STORE"] = credential_store

    # Trust exactly one reverse proxy only when the deployment explicitly opts in.
    # Render terminates public TLS at its load balancer and forwards HTTP to Gunicorn.
    trust_proxy_headers = str(env.get("ISKRA_TRUST_PROXY_HEADERS", "")).strip().lower() in {
        "1", "true", "yes", "on"
    }
    secured_application = ApiTokenMiddleware(
        application.wsgi_app,
        token=env.get("API_TOKEN", ""),
        credentials_json=env.get("ISKRA_API_CREDENTIALS_JSON", ""),
        credential_store=credential_store,
    )
    if trust_proxy_headers:
        # ProxyFix must run before authentication so Origin checks see the
        # externally visible scheme, not the proxy-to-Gunicorn HTTP hop.
        secured_application = ProxyFix(secured_application, x_proto=1)
    return secured_application


app = create_wsgi_app()
