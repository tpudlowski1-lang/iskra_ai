"""Validated runtime configuration for the Iskra Flask application."""
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    port: int
    data_dir: str
    tenant_storage_backend: str = "sqlite"
    postgres_dsn: str = ""


def load_settings(environ=None, project_root=None):
    """Load settings with safe bounds and explicit storage backend validation."""
    env = os.environ if environ is None else environ
    root = os.path.abspath(project_root or os.path.dirname(os.path.dirname(__file__)))
    raw_port = env.get("PORT", "10000")
    try:
        port = int(raw_port)
    except (TypeError, ValueError):
        raise ValueError("PORT musi być liczbą całkowitą") from None
    if not 1 <= port <= 65535:
        raise ValueError("PORT musi należeć do zakresu 1..65535")
    data_dir = os.path.abspath(env.get("DATA_DIR") or root)

    backend = str(env.get("ISKRA_TENANT_STORAGE_BACKEND", "sqlite")).strip().lower()
    if backend not in {"sqlite", "postgres"}:
        raise ValueError("ISKRA_TENANT_STORAGE_BACKEND musi mieć wartość sqlite albo postgres")
    postgres_dsn = str(env.get("ISKRA_POSTGRES_DSN", "")).strip()
    if backend == "postgres" and not postgres_dsn:
        raise ValueError("ISKRA_POSTGRES_DSN jest wymagany dla backendu postgres")

    return Settings(
        port=port,
        data_dir=data_dir,
        tenant_storage_backend=backend,
        postgres_dsn=postgres_dsn,
    )
