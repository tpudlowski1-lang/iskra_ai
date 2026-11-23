"""HTTP API blueprint factory with injected graph dependency."""
from flask import Blueprint, jsonify

from iskra.security.policy import require_roles


def create_api_blueprint(graph):
    """Build API routes around an explicitly supplied graph service."""
    api = Blueprint("iskra_api", __name__)

    @api.get("/api/network")
    @require_roles("admin")
    def get_network():
        # The legacy graph is global and not tenant-partitioned. Only system
        # administrators may read it until tenant-aware storage is integrated.
        graph.laduj()
        with graph.lock:
            return jsonify(graph.dane)

    @api.get("/health")
    def health():
        graph.laduj()
        with graph.lock:
            return jsonify({"status": "ok", "neurons": len(graph.dane["neurons"])})

    return api
