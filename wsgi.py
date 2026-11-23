"""Production WSGI entry point with fail-closed authentication.

Use `wsgi:app` (not `app:app`) for public deployments so every non-health
request passes through the authentication middleware.
"""
import os

from security import ApiTokenMiddleware


def create_wsgi_app(application=None, environ=None):
    """Wrap a Flask application using the supplied server environment.

    The factory is injectable so production wiring can be integration-tested
    without mutating the process environment or importing a global Flask app.
    """
    env = os.environ if environ is None else environ
    if application is None:
        from app import app as application

    credential_store = None
    database_path = str(env.get("ISKRA_CREDENTIAL_DB_PATH", "") or "").strip()
    if database_path:
        from iskra.security.sqlite_credentials import SQLiteCredentialStore

        credential_store = SQLiteCredentialStore(database_path)

    application.config["ISKRA_CREDENTIAL_STORE"] = credential_store

    return ApiTokenMiddleware(
        application.wsgi_app,
        token=env.get("API_TOKEN", ""),
        credentials_json=env.get("ISKRA_API_CREDENTIALS_JSON", ""),
        credential_store=credential_store,
    )


app = create_wsgi_app()
