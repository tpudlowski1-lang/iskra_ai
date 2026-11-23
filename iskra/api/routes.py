"""HTTP API blueprint factory with injected graph and tenant storage dependencies."""
import sqlite3

from flask import Blueprint, jsonify, request

from iskra.security.policy import require_roles, require_system_admin
from iskra.security.principal import principal_from_environ
from iskra.assistant.chat import InferenceUnavailable, InvalidModelResponse
from iskra.documents.repository import DocumentStorageError


MAX_DOCUMENT_UPLOAD_BYTES = 1024 * 1024


def create_api_blueprint(
    graph,
    tenant_store_factory=None,
    document_service=None,
    chat_service=None,
    document_ingestion_enabled=False,
):
    """Build routes around explicit graph and tenant-store dependencies."""
    api = Blueprint("iskra_api", __name__)

    @api.get("/api/network")
    @require_system_admin
    def get_network():
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
            store = tenant_store_factory(principal)
            snapshot = store.load_or_initialize(graph.fundament)
            return jsonify(snapshot)
        except PermissionError:
            return jsonify({"error": "forbidden"}), 403
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
            store = tenant_store_factory(principal)
            store.save(payload)
            return jsonify({
                "status": "saved",
                "tenant_id": principal.tenant_id,
                "neurons": len(payload.get("neurons", {})),
                "synapses": len(payload.get("synapses", [])),
            })
        except PermissionError:
            return jsonify({"error": "forbidden"}), 403
        except ValueError as exc:
            return jsonify({"error": "invalid_graph_payload", "message": str(exc)}), 400
        except (OSError, sqlite3.Error):
            return jsonify({"error": "tenant_storage_unavailable"}), 503

    @api.post("/api/tenant/chat")
    @require_roles("member", "admin")
    def post_tenant_chat():
        if chat_service is None:
            return jsonify({"error": "chat_unavailable"}), 503
        if not request.is_json:
            return jsonify({"error": "application_json_required"}), 415
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "invalid_chat_payload"}), 400
        question = payload.get("question")
        if not isinstance(question, str) or not question.strip():
            return jsonify({"error": "question_required"}), 400
        principal = principal_from_environ(request.environ)
        try:
            result = chat_service.answer(principal, question)
            return jsonify(result)
        except ValueError:
            return jsonify({"error": "invalid_question"}), 400
        except PermissionError:
            return jsonify({"error": "forbidden"}), 403
        except InferenceUnavailable:
            return jsonify({"error": "inference_unavailable"}), 503
        except InvalidModelResponse:
            return jsonify({"error": "invalid_model_response"}), 502
        except (DocumentStorageError, OSError, sqlite3.Error):
            return jsonify({"error": "document_storage_unavailable"}), 503

    @api.get("/api/tenant/documents")
    @require_roles("member", "admin")
    def list_tenant_documents():
        if document_service is None:
            return jsonify({"error": "document_storage_unavailable"}), 503
        principal = principal_from_environ(request.environ)
        try:
            return jsonify({"documents": document_service.list_documents(principal)})
        except PermissionError:
            return jsonify({"error": "forbidden"}), 403
        except (DocumentStorageError, OSError, sqlite3.Error):
            return jsonify({"error": "document_storage_unavailable"}), 503

    @api.get("/api/tenant/documents/search")
    @require_roles("member", "admin")
    def search_tenant_documents():
        if document_service is None:
            return jsonify({"error": "document_storage_unavailable"}), 503
        query = request.args.get("q", "")
        principal = principal_from_environ(request.environ)
        try:
            return jsonify({"results": document_service.search_documents(principal, query, limit=5)})
        except ValueError:
            return jsonify({"error": "invalid_query"}), 400
        except PermissionError:
            return jsonify({"error": "forbidden"}), 403
        except (DocumentStorageError, OSError, sqlite3.Error):
            return jsonify({"error": "document_storage_unavailable"}), 503

    @api.post("/api/tenant/documents")
    @require_roles("admin")
    def add_tenant_document():
        if not document_ingestion_enabled:
            return jsonify({"error": "document_ingestion_disabled"}), 503
        if document_service is None:
            return jsonify({"error": "document_storage_unavailable"}), 503
        uploaded = request.files.get("file")
        if uploaded is None or not uploaded.filename:
            return jsonify({"error": "file_required"}), 400
        try:
            data = uploaded.stream.read(MAX_DOCUMENT_UPLOAD_BYTES + 1)
            if len(data) > MAX_DOCUMENT_UPLOAD_BYTES:
                return jsonify({"error": "file_too_large"}), 413
            principal = principal_from_environ(request.environ)
            result = document_service.add_document(principal, uploaded.filename, data)
            return jsonify(result), 201
        except ValueError:
            return jsonify({"error": "invalid_document"}), 400
        except RuntimeError:
            return jsonify({"error": "document_processing_failed"}), 422
        except PermissionError:
            return jsonify({"error": "forbidden"}), 403
        except (DocumentStorageError, OSError, sqlite3.Error):
            return jsonify({"error": "document_storage_unavailable"}), 503

    @api.delete("/api/tenant/documents/<document_id>")
    @require_roles("admin")
    def delete_tenant_document(document_id):
        if document_service is None:
            return jsonify({"error": "document_storage_unavailable"}), 503
        principal = principal_from_environ(request.environ)
        try:
            deleted = document_service.delete_document(principal, document_id)
            return jsonify({"deleted": bool(deleted)})
        except ValueError:
            return jsonify({"error": "invalid_document_id"}), 400
        except PermissionError:
            return jsonify({"error": "forbidden"}), 403
        except (DocumentStorageError, OSError, sqlite3.Error):
            return jsonify({"error": "document_storage_unavailable"}), 503

    @api.get("/health")
    def health():
        graph.laduj()
        with graph.lock:
            return jsonify({"status": "ok", "neurons": len(graph.dane["neurons"])})

    return api
