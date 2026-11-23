"""HTTP API blueprint factory with injected graph dependency."""
from flask import Blueprint, jsonify

from iskra.security.policy import require_system_admin


def create_api_blueprint(graph):
    """Build API routes around an explicitly supplied graph service."""
    api = Blueprint("iskra_api", __name__)

    @api.get("/api/network")
    @require_system_admin
    def get_network():
        # The compatibility graph is global and not tenant-partitioned.
        # Only the system administrator may read it.
        graph.laduj()
        with graph.lock:
            return jsonify(graph.dane)

    @api.get("/health")
    def health():
        graph.laduj()
        with graph.lock:
            return jsonify({"status": "ok", "neurons": len(graph.dane["neurons"])})

    return api
