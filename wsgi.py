"""Production WSGI entry point with fail-closed authentication."""
import os

from app import app
from security import ApiTokenMiddleware

credential_store = None
database_path = os.environ.get("ISKRA_CREDENTIAL_DB_PATH", "").strip()
if database_path:
    from iskra.security.sqlite_credentials import SQLiteCredentialStore
    credential_store = SQLiteCredentialStore(database_path)

app.wsgi_app = ApiTokenMiddleware(
    app.wsgi_app,
    credential_store=credential_store,
)
