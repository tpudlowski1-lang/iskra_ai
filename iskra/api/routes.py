"""HTTP API blueprint factory with injected graph and tenant storage dependencies."""
import sqlite3

from flask import Blueprint, jsonify, request

from iskra.security.policy import require_roles, require_system_admin
from iskra.security.principal import principal_from_environ


def create_api_blueprint(graph, tenant_store_factory=None):
    """Build routes around explicit graph and tenant-store dependencies."""
    api = Blueprint("iskra_api", __name__)

    @api.get("/api/network")
    @require_system_admin
    def get_network():
        # Legacy global graph: system administrator only.
        graph.laduj()
        with graph.lock:
            return jsonify(graph.dane)

    @api.get("/api/tenant/network")
    @require_roles("member", "admin")
    def get_tenant_network():
        if tenant_store_factory is None:
            return jsonify({"error": "tenant_storage_unavailable"}), 503
        principal = principal_from_environ(request.environ)
        try:
            store = tenant_store_factory(principal.tenant_id)
            # Initialization is serialized in SQLite so a first-read request
            # cannot overwrite a concurrent tenant write.
            snapshot = store.load_or_initialize(graph.fundament)
            return jsonify(snapshot)
        except (OSError, sqlite3.Error):
            return jsonify({"error": "tenant_storage_unavailable"}), 503

    @api.put("/api/tenant/network")
    @require_roles("member", "admin")
    def put_tenant_network():
        if tenant_store_factory is None:
            return jsonify({"error": "tenant_storage_unavailable"}), 503
        if not request.is_json:
            return jsonify({"error": "application_json_required"}), 415
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "invalid_graph_payload"}), 400

        required_neurons = set(graph.fundament.get("neurons", {}))
        submitted_neurons = payload.get("neurons")
        submitted_synapses = payload.get("synapses")
        if not isinstance(submitted_neurons, dict) or not required_neurons.issubset(submitted_neurons):
            return jsonify({"error": "foundational_pillars_required"}), 400
        required_edges = {
            (edge.get("from"), edge.get("to"))
            for edge in graph.fundament.get("synapses", [])
            if isinstance(edge, dict)
        }
        submitted_edges = set()
        if isinstance(submitted_synapses, list):
            for edge in submitted_synapses:
                if (isinstance(edge, dict)
                        and isinstance(edge.get("from"), str)
                        and isinstance(edge.get("to"), str)):
                    submitted_edges.add((edge["from"], edge["to"]))
        if not required_edges.issubset(submitted_edges):
            return jsonify({"error": "foundational_connections_required"}), 400

        principal = principal_from_environ(request.environ)
        try:
            store = tenant_store_factory(principal.tenant_id)
            store.save(payload)
            return jsonify({
                "status": "saved",
                "tenant_id": principal.tenant_id,
                "neurons": len(payload.get("neurons", {})),
                "synapses": len(payload.get("synapses", [])),
            })
        except ValueError as exc:
            return jsonify({"error": "invalid_graph_payload", "message": str(exc)}), 400
        except (OSError, sqlite3.Error):
            return jsonify({"error": "tenant_storage_unavailable"}), 503

    @api.get("/health")
    def health():
        graph.laduj()
        with graph.lock:
            return jsonify({"status": "ok", "neurons": len(graph.dane["neurons"])})

    return api
