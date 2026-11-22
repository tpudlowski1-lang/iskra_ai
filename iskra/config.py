"""Validated runtime configuration for the Iskra Flask application."""
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    port: int
    data_dir: str


def load_settings(environ=None, project_root=None):
    """Load settings with safe bounds and a deterministic project-local default."""
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
    return Settings(port=port, data_dir=data_dir)
