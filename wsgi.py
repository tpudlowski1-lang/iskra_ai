"""Production WSGI entry point with fail-closed API-token authentication."""
from app import app
from security import ApiTokenMiddleware

app.wsgi_app = ApiTokenMiddleware(app.wsgi_app)
