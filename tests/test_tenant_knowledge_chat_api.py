import hashlib
import io
import json
import tempfile
import threading
import unittest

from flask import Flask

from iskra.api.routes import create_api_blueprint
from iskra.documents.repository import SQLiteDocumentRepository
from iskra.documents.service import DocumentService
from iskra.documents.parsers import parse_document
from iskra.assistant.chat import KnowledgeChatService
from iskra.security.principal import Principal
from iskra.llm.tenant_policy import TenantProviderPolicy
from security import ApiTokenMiddleware


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class FakeRouter:
    def __init__(self):
        self.calls = []
        self.allowed_providers = {"deepseek"}
        self.response_override = None
        self.return_none = False

    def generate(self, prompt, system_prompt=None, allowed_providers=None):
        payload = json.loads(prompt)
        self.calls.append((payload, system_prompt))
        if self.return_none:
            return None
        if self.response_override is not None:
            return self.response_override
        source = payload["sources"][0]
        return json.dumps({
            "answer": f"Informacja z dokumentu {source['document_id']}.",
            "citation_ids": [source["document_id"]],
        })


class TenantKnowledgeChatApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database = f"{self.tmp.name}/private/documents.sqlite3"
        repository = SQLiteDocumentRepository(database)
        self.document_service = DocumentService(repository, parser=parse_document)
        self.alpha = Principal("member-a", "tenant-alpha", frozenset({"member"}))
        self.alpha_admin = Principal("admin-a", "tenant-alpha", frozenset({"admin"}))
        self.beta = Principal("member-b", "tenant-beta", frozenset({"member"}))

        self.alpha_doc = self.document_service.add_document(
            self.alpha, "alpha-procedure.txt",
            b"ALPHA-SECRET: zatwierdzenie wydatkow do 1000 PLN przez lidera zespolu."
        )
        self.beta_doc = self.document_service.add_document(
            self.beta, "beta-procedure.txt",
            b"BETA-PRIVATE-CODE: zatwierdzenie wydatkow do 500 PLN przez kierownika."
        )

        class Graph:
            fundament = {"neurons": {}, "synapses": []}
            dane = {"neurons": {}, "synapses": []}
            lock = threading.RLock()

            def laduj(self):
                return None

        self.router = FakeRouter()
        self.chat_service = KnowledgeChatService(
            self.document_service,
            self.router,
            TenantProviderPolicy({
                "tenant-alpha": ["deepseek"],
                "tenant-beta": ["deepseek"],
            }),
        )
        credentials = json.dumps([
            {"token_sha256": token_hash("alpha-member-token"), "subject": "member-a", "tenant_id": "tenant-alpha", "roles": ["member"]},
            {"token_sha256": token_hash("alpha-admin-token"), "subject": "admin-a", "tenant_id": "tenant-alpha", "roles": ["admin"]},
            {"token_sha256": token_hash("beta-member-token"), "subject": "member-b", "tenant_id": "tenant-beta", "roles": ["member"]},
        ])
        self.app = Flask(__name__)
        self.app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
        self.app.register_blueprint(create_api_blueprint(
            Graph(),
            document_service=self.document_service,
            chat_service=self.chat_service,
            document_ingestion_enabled=False,
        ))
        self.app.wsgi_app = ApiTokenMiddleware(
            self.app.wsgi_app,
            token="system-admin-test-token",
            credentials_json=credentials,
        )
        self.client = self.app.test_client()

        self.enabled_app = Flask(__name__)
        self.enabled_app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
        self.enabled_app.register_blueprint(create_api_blueprint(
            Graph(),
            document_service=self.document_service,
            chat_service=self.chat_service,
            document_ingestion_enabled=True,
        ))
        self.enabled_app.wsgi_app = ApiTokenMiddleware(
            self.enabled_app.wsgi_app,
            token="system-admin-test-token",
            credentials_json=credentials,
        )
        self.enabled_client = self.enabled_app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_cloud_chat_preserves_wire_format_and_uses_tenant_sources(self):
        body = {"pytanie": "ALPHA-SECRET: matematyka i algorytmy"}
        self.assertEqual(self.client.post("/api/chat", json=body).status_code, 401)
        result = self.client.post("/api/chat", json=body, headers=self.auth("alpha-member-token"))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(set(result.json), {"odpowiedz", "kategoria"})
        self.assertEqual(result.json["kategoria"], "LOGIKA_I_MATEMATYKA")
        self.assertIn(self.alpha_doc["document_id"], result.json["odpowiedz"])
        self.assertNotIn(self.beta_doc["document_id"], result.json["odpowiedz"])

    def test_cloud_chat_rejects_invalid_input_and_respects_provider_policy(self):
        headers = self.auth("alpha-member-token")
        self.assertEqual(self.client.post("/api/chat", json={"pytanie": []}, headers=headers).status_code, 400)
        self.router.allowed_providers = set()
        response = self.client.post("/api/chat", json={"pytanie":"ALPHA-SECRET"}, headers=headers)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.router.calls, [])

    def test_chat_requires_authenticated_principal(self):
        response = self.client.post("/api/tenant/chat", json={"question": "ALPHA-SECRET"})
        self.assertEqual(response.status_code, 401)

    def test_chat_returns_only_the_authenticated_tenants_document_citations(self):
        response = self.client.post(
            "/api/tenant/chat",
            headers=self.auth("alpha-member-token"),
            json={"question": "ALPHA-SECRET kto zatwierdza wydatki"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["status"], "answered")
        self.assertTrue(body["grounded"])
        self.assertEqual(body["citations"][0]["document_id"], self.alpha_doc["document_id"])
        self.assertNotEqual(body["citations"][0]["document_id"], self.beta_doc["document_id"])
        sent_sources = self.router.calls[-1][0]["sources"]
        self.assertEqual([s["document_id"] for s in sent_sources], [self.alpha_doc["document_id"]])

    def test_tenant_cannot_retrieve_another_tenants_document_through_chat(self):
        response = self.client.post(
            "/api/tenant/chat",
            headers=self.auth("alpha-member-token"),
            json={"question": "BETA-PRIVATE-CODE"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "no_sources")
        self.assertFalse(response.get_json()["grounded"])
        self.assertEqual(self.router.calls, [])

    def test_beta_chat_receives_only_beta_sources(self):
        response = self.client.post(
            "/api/tenant/chat",
            headers=self.auth("beta-member-token"),
            json={"question": "BETA-PRIVATE-CODE"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["citations"][0]["document_id"], self.beta_doc["document_id"])
        self.assertEqual(
            [s["document_id"] for s in self.router.calls[-1][0]["sources"]],
            [self.beta_doc["document_id"]],
        )

    def test_model_cannot_forge_cross_tenant_citation(self):
        self.router.response_override = json.dumps({
            "answer": "Poufna odpowiedz",
            "citation_ids": [self.beta_doc["document_id"]],
        })
        response = self.client.post(
            "/api/tenant/chat",
            headers=self.auth("alpha-member-token"),
            json={"question": "ALPHA-SECRET"},
        )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json()["error"], "invalid_model_response")

    def test_tenant_without_explicit_provider_policy_gets_503_without_router_call(self):
        self.chat_service.provider_policy = TenantProviderPolicy({
            "tenant-beta": ["deepseek"],
        })
        response = self.client.post(
            "/api/tenant/chat",
            headers=self.auth("alpha-member-token"),
            json={"question": "ALPHA-SECRET"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.router.calls, [])

    def test_chat_returns_503_when_no_provider_is_allowlisted(self):
        self.router.return_none = True
        response = self.client.post(
            "/api/tenant/chat",
            headers=self.auth("alpha-member-token"),
            json={"question": "ALPHA-SECRET"},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "inference_unavailable")

    def test_chat_validates_question_payload(self):
        response = self.client.post(
            "/api/tenant/chat",
            headers=self.auth("alpha-member-token"),
            json={"question": " "},
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            "/api/tenant/chat",
            headers=self.auth("alpha-member-token"),
            json={"question": "x" * 1001},
        )
        self.assertEqual(response.status_code, 400)

    def test_document_list_is_tenant_scoped(self):
        response = self.client.get("/api/tenant/documents", headers=self.auth("alpha-member-token"))
        self.assertEqual(response.status_code, 200)
        ids = [doc["document_id"] for doc in response.get_json()["documents"]]
        self.assertEqual(ids, [self.alpha_doc["document_id"]])
        self.assertNotIn(self.beta_doc["document_id"], ids)

    def test_document_search_is_tenant_scoped(self):
        response = self.client.get(
            "/api/tenant/documents/search?q=BETA-PRIVATE-CODE",
            headers=self.auth("alpha-member-token"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["results"], [])

    def test_document_ingestion_is_disabled_by_default_even_for_admin(self):
        response = self.client.post(
            "/api/tenant/documents",
            headers=self.auth("alpha-admin-token"),
            data={"file": (io.BytesIO(b"new document"), "new.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "document_ingestion_disabled")

    def test_document_ingestion_requires_admin_when_enabled(self):
        denied = self.enabled_client.post(
            "/api/tenant/documents",
            headers=self.auth("alpha-member-token"),
            data={"file": (io.BytesIO(b"new document"), "member.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(denied.status_code, 403)

        created = self.enabled_client.post(
            "/api/tenant/documents",
            headers=self.auth("alpha-admin-token"),
            data={"file": (io.BytesIO(b"admin uploaded document"), "admin.txt")},
            content_type="multipart/form-data",
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.get_json()["filename"], "admin.txt")

    def test_delete_is_tenant_scoped_and_admin_only(self):
        response = self.client.delete(
            f"/api/tenant/documents/{self.beta_doc['document_id']}",
            headers=self.auth("alpha-admin-token"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["deleted"])
        denied = self.client.delete(
            f"/api/tenant/documents/{self.alpha_doc['document_id']}",
            headers=self.auth("alpha-member-token"),
        )
        self.assertEqual(denied.status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
