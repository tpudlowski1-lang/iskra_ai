"""HTTP API blueprint factory with injected graph dependency."""
from flask import Blueprint, jsonify


def create_api_blueprint(graph):
    """Build API routes around an explicitly supplied graph service."""
    api = Blueprint("iskra_api", __name__)

    @api.get("/api/network")
    def get_network():
        with graph.lock:
            return jsonify(graph.dane)

    @api.get("/health")
    def health():
        with graph.lock:
            return jsonify({"status": "ok", "neurons": len(graph.dane["neurons"])})

    return api
