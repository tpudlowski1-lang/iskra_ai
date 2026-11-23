import io
import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import knowledge
from security import ApiTokenMiddleware


class TenantKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "iskra_knowledge.sqlite3")
        self.a = knowledge.create_tenant(self.db, "Firma Alfa")
        self.b = knowledge.create_tenant(self.db, "Firma Beta")

    def tearDown(self):
        self.tmp.cleanup()

    def test_tenant_key_authentication_returns_only_its_tenant(self):
        self.assertEqual(knowledge.authenticate_tenant_key(self.db, self.a["api_key"]), self.a["tenant_id"])
        self.assertIsNone(knowledge.authenticate_tenant_key(self.db, self.a["api_key"] + "x"))

    def test_text_document_is_chunked_and_searchable(self):
        text = ("Procedura reklamacji: klient składa reklamację w terminie 14 dni. " * 30).encode()
        result = knowledge.add_document(self.db, self.a["tenant_id"], "procedura.txt", text)
        self.assertGreater(result["chunks"], 1)
        hits = knowledge.search_documents(self.db, self.a["tenant_id"], "reklamacji terminie")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["filename"], "procedura.txt")

    def test_documents_are_isolated_between_tenants(self):
        knowledge.add_document(self.db, self.a["tenant_id"], "alfa.txt",
                               "Tajny kod klienta ALFA-991".encode())
        self.assertEqual(knowledge.search_documents(self.db, self.b["tenant_id"], "ALFA-991"), [])

    def test_duplicate_upload_is_idempotent_per_tenant(self):
        payload = b"Polityka zwrotow: 30 dni."
        first = knowledge.add_document(self.db, self.a["tenant_id"], "zwroty.txt", payload)
        second = knowledge.add_document(self.db, self.a["tenant_id"], "kopie.txt", payload)
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["document_id"], second["document_id"])

    def test_delete_removes_document_and_search_index(self):
        item = knowledge.add_document(self.db, self.a["tenant_id"], "regulamin.txt",
                                      b"Warunki gwarancji wynosza dwa lata.")
        self.assertTrue(knowledge.delete_document(self.db, self.a["tenant_id"], item["document_id"]))
        self.assertEqual(knowledge.search_documents(self.db, self.a["tenant_id"], "gwarancji"), [])

    def test_tenant_cannot_delete_another_tenants_document(self):
        item = knowledge.add_document(self.db, self.a["tenant_id"], "alfa.txt", b"Dokument prywatny Alfa.")
        self.assertFalse(knowledge.delete_document(self.db, self.b["tenant_id"], item["document_id"]))
        self.assertEqual(len(knowledge.list_documents(self.db, self.a["tenant_id"])), 1)

    def test_unsupported_and_empty_files_are_rejected(self):
        with self.assertRaises(ValueError):
            knowledge.add_document(self.db, self.a["tenant_id"], "malware.exe", b"data")
        with self.assertRaises(ValueError):
            knowledge.add_document(self.db, self.a["tenant_id"], "empty.txt", b"")

    def test_docx_extraction(self):
        import zipfile
        xml = b'''<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body><w:p><w:r><w:t>Instrukcja bezpieczenstwa dokumentu.</w:t></w:r></w:p></w:body>
        </w:document>'''
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("word/document.xml", xml)
        result = knowledge.add_document(self.db, self.a["tenant_id"], "instrukcja.docx", stream.getvalue())
        self.assertEqual(result["chunks"], 1)
        self.assertTrue(knowledge.search_documents(self.db, self.a["tenant_id"], "bezpieczenstwa"))

    def test_middleware_limits_tenant_key_to_document_routes(self):
        calls = []
        def app(environ, start_response):
            calls.append(environ.get("iskra.tenant_id"))
            start_response("200 OK", [])
            return [b"ok"]
        middleware = ApiTokenMiddleware(app, token="admin-secret", data_dir=self.tmp.name)
        def request(path, key):
            env = {"PATH_INFO": path, "HTTP_X_ISKRA_TENANT_KEY": key}
            result = {}
            body = b"".join(middleware(env, lambda status, headers, exc_info=None: result.update(status=status)))
            return result["status"], body
        status, _ = request("/api/search", self.a["api_key"])
        self.assertEqual(status, "200 OK")
        status, _ = request("/api/network", self.a["api_key"])
        self.assertEqual(status, "401 Unauthorized")
        self.assertEqual(calls, [self.a["tenant_id"]])

    def test_admin_token_is_required_to_create_tenants(self):
        calls = []
        def app(environ, start_response):
            calls.append(environ.get("iskra.auth_role"))
            start_response("200 OK", [])
            return [b"ok"]
        middleware = ApiTokenMiddleware(app, token="admin-secret")
        result = {}
        list(middleware({"PATH_INFO": "/admin/tenants", "HTTP_AUTHORIZATION": "Bearer admin-secret"},
                        lambda status, headers, exc_info=None: result.update(status=status)))
        self.assertEqual(result["status"], "200 OK")
        self.assertEqual(calls, ["admin"])



class TenantAdminLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "iskra.sqlite3")
        self.tenant = knowledge.create_tenant(self.db, "Do usunięcia")

    def tearDown(self):
        self.tmp.cleanup()

    def test_key_rotation_revokes_old_key(self):
        new_key = knowledge.rotate_tenant_key(self.db, self.tenant["tenant_id"])
        self.assertTrue(new_key)
        self.assertIsNone(knowledge.authenticate_tenant_key(self.db, self.tenant["api_key"]))
        self.assertEqual(knowledge.authenticate_tenant_key(self.db, new_key), self.tenant["tenant_id"])

    def test_tenant_deletion_removes_company_data(self):
        knowledge.add_document(self.db, self.tenant["tenant_id"], "dane.txt", b"Poufne dane firmy.")
        self.assertTrue(knowledge.delete_tenant(self.db, self.tenant["tenant_id"]))
        self.assertIsNone(knowledge.authenticate_tenant_key(self.db, self.tenant["api_key"]))
        self.assertEqual(knowledge.list_tenants(self.db), [])
        self.assertFalse(knowledge.delete_tenant(self.db, self.tenant["tenant_id"]))


class TenantApiIntegrationTests(unittest.TestCase):
    def setUp(self):
        import app as iskra
        self.iskra = iskra
        self.tmp = tempfile.TemporaryDirectory()
        self.old_data_dir = iskra.DATA_DIR
        self.old_network_path = iskra.PLIK_SIECI
        self.old_wsgi_app = iskra.app.wsgi_app
        iskra.DATA_DIR = self.tmp.name
        iskra.PLIK_SIECI = os.path.join(self.tmp.name, "wiedza.json")
        iskra.app.wsgi_app = ApiTokenMiddleware(
            iskra.app.wsgi_app, token="integration-admin-secret", data_dir=self.tmp.name
        )
        self.client = iskra.app.test_client()
        self.old_router_generate = iskra.bot.router.generate

    def tearDown(self):
        self.iskra.app.wsgi_app = self.old_wsgi_app
        self.iskra.bot.router.generate = self.old_router_generate
        self.iskra.DATA_DIR = self.old_data_dir
        self.iskra.PLIK_SIECI = self.old_network_path
        self.tmp.cleanup()

    def test_workspace_page_is_public_and_contains_no_tenant_data(self):
        response = self.client.get("/workspace")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Przestr", response.data)
        self.assertIn(b"sessionStorage", response.data)

    def test_end_to_end_tenant_isolation_through_flask_routes(self):
        admin = {"Authorization": "Bearer integration-admin-secret"}
        a = self.client.post("/admin/tenants", json={"name": "Alfa"}, headers=admin)
        b = self.client.post("/admin/tenants", json={"name": "Beta"}, headers=admin)
        self.assertEqual(a.status_code, 201)
        self.assertEqual(b.status_code, 201)
        key_a = a.get_json()["api_key"]
        key_b = b.get_json()["api_key"]
        upload = self.client.post(
            "/api/documents", data={"file": (io.BytesIO(b"Oferta specjalna ALFA-440"), "oferta.txt")},
            headers={"X-Iskra-Tenant-Key": key_a}, content_type="multipart/form-data"
        )
        self.assertEqual(upload.status_code, 201)
        search_a = self.client.post("/api/search", json={"query": "ALFA-440"},
                                    headers={"X-Iskra-Tenant-Key": key_a})
        search_b = self.client.post("/api/search", json={"query": "ALFA-440"},
                                    headers={"X-Iskra-Tenant-Key": key_b})
        self.assertEqual(len(search_a.get_json()["results"]), 1)
        self.assertEqual(search_b.get_json()["results"], [])
        self.assertEqual(self.client.get("/api/network", headers={"X-Iskra-Tenant-Key": key_a}).status_code, 401)
        self.assertEqual(self.client.get("/api/documents", headers={"X-Iskra-Tenant-Key": key_b}).status_code, 200)
        self.assertEqual(self.client.delete(
            "/api/documents/" + upload.get_json()["document_id"],
            headers={"X-Iskra-Tenant-Key": key_b}
        ).status_code, 404)



    def test_api_rejects_non_object_json_payloads(self):
        admin = {"Authorization": "Bearer integration-admin-secret"}
        self.assertEqual(self.client.post("/admin/tenants", json=["not", "object"],
                                          headers=admin).status_code, 400)
        created = self.client.post("/admin/tenants", json={"name": "Walidacja"}, headers=admin)
        key = created.get_json()["api_key"]
        headers = {"X-Iskra-Tenant-Key": key}
        self.assertEqual(self.client.post("/api/search", json=["query"], headers=headers).status_code, 400)
        self.assertEqual(self.client.post("/api/chat", json=["question"], headers=headers).status_code, 400)

    def test_grounded_chat_returns_only_valid_citations(self):
        admin = {"Authorization": "Bearer integration-admin-secret"}
        created = self.client.post("/admin/tenants", json={"name": "Firma RAG"}, headers=admin)
        key = created.get_json()["api_key"]
        tenant_headers = {"X-Iskra-Tenant-Key": key}
        self.client.post(
            "/api/documents",
            data={"file": (io.BytesIO(b"Termin zwrotu wynosi 30 dni od zakupu."), "zwroty.txt")},
            headers=tenant_headers, content_type="multipart/form-data"
        )
        captured = {}
        def fake_generate(prompt, system_prompt=None):
            captured["prompt"] = prompt
            captured["system_prompt"] = system_prompt
            return json.dumps({
                "answer": "Zwrot jest możliwy w terminie 30 dni [S1].",
                "citations": ["S1"],
                "insufficient_evidence": False,
            })
        self.iskra.bot.router.generate = fake_generate
        response = self.client.post("/api/chat", json={"question": "Jaki jest termin zwrotu?"},
                                    headers=tenant_headers)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["grounded"])
        self.assertEqual(payload["citations"], ["S1"])
        self.assertEqual(payload["sources"][0]["filename"], "zwroty.txt")
        self.assertIn("NIEZAUFANYMI DANYMI", captured["system_prompt"])
        self.assertIn("30 dni", captured["prompt"])

    def test_chat_does_not_call_model_without_matching_sources(self):
        created = self.client.post("/admin/tenants", json={"name": "Pusta firma"},
                                   headers={"Authorization": "Bearer integration-admin-secret"})
        key = created.get_json()["api_key"]
        calls = []
        self.iskra.bot.router.generate = lambda *args, **kwargs: calls.append(True) or None
        response = self.client.post("/api/chat", json={"question": "Jaki jest numer umowy?"},
                                    headers={"X-Iskra-Tenant-Key": key})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["grounded"])
        self.assertEqual(calls, [])

    def test_chat_rejects_fabricated_source_ids(self):
        created = self.client.post("/admin/tenants", json={"name": "Firma cytowań"},
                                   headers={"Authorization": "Bearer integration-admin-secret"})
        key = created.get_json()["api_key"]
        tenant_headers = {"X-Iskra-Tenant-Key": key}
        self.client.post(
            "/api/documents",
            data={"file": (io.BytesIO(b"Okres gwarancji wynosi dwa lata."), "gwarancja.txt")},
            headers=tenant_headers, content_type="multipart/form-data"
        )
        self.iskra.bot.router.generate = lambda *args, **kwargs: json.dumps({
            "answer": "Gwarancja trwa rok [S99].",
            "citations": ["S99"],
            "insufficient_evidence": False,
        })
        response = self.client.post("/api/chat", json={"question": "Jaki jest okres gwarancji?"},
                                    headers=tenant_headers)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json()["error"], "invalid_model_response")

class TenantSchemaRecoveryTests(unittest.TestCase):
    def test_schema_is_recreated_when_sqlite_file_is_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "iskra.sqlite3")
            tenant = knowledge.create_tenant(db_path, "Firma przed awarią")
            backup = db_path + ".backup"
            os.replace(db_path, backup)
            with sqlite3.connect(db_path):
                pass
            knowledge.initialize(db_path)
            with sqlite3.connect(db_path) as connection:
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )}
            self.assertIn("tenants", tables)
            self.assertIsNone(knowledge.authenticate_tenant_key(db_path, tenant["api_key"]))




class SemanticRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "iskra_knowledge.sqlite3")
        self.tenant = knowledge.create_tenant(self.db, "Firma semantyczna")

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def fake_embed_many(texts):
        return [[1.0, 0.0] if "umowa" in text.lower() else [0.0, 1.0] for text in texts]

    @staticmethod
    def fake_embed_one(_query):
        return [1.0, 0.0]

    def test_semantic_search_finds_synonym_without_lexical_overlap(self):
        knowledge.add_document(
            self.db, self.tenant["tenant_id"], "kontrakt.txt",
            "Umowa określa zasady współpracy oraz obowiązki stron.".encode(),
            embedding_fn=self.fake_embed_many,
        )
        hits = knowledge.search_documents(
            self.db, self.tenant["tenant_id"], "kontrakt",
            embedding_fn=self.fake_embed_one,
        )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["filename"], "kontrakt.txt")

    def test_semantic_results_remain_tenant_isolated(self):
        knowledge.add_document(
            self.db, self.tenant["tenant_id"], "prywatne.txt",
            "Umowa Alfa 123.".encode(), embedding_fn=self.fake_embed_many,
        )
        other = knowledge.create_tenant(self.db, "Druga firma")
        hits = knowledge.search_documents(
            self.db, other["tenant_id"], "kontrakt",
            embedding_fn=self.fake_embed_one,
        )
        self.assertEqual(hits, [])

    def test_invalid_embedding_falls_back_to_lexical_search(self):
        knowledge.add_document(
            self.db, self.tenant["tenant_id"], "faktura.txt",
            "Faktura VAT płatna w terminie 14 dni.".encode(),
            embedding_fn=lambda texts: [[float("nan")] for _ in texts],
        )
        hits = knowledge.search_documents(self.db, self.tenant["tenant_id"], "faktura")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["filename"], "faktura.txt")

class EmbeddingConfigurationTests(unittest.TestCase):
    def test_semantic_search_is_disabled_without_explicit_opt_in(self):
        from embeddings import EmbeddingProvider
        with patch.dict(os.environ, {
            "ENABLE_SEMANTIC_SEARCH": "false",
            "OPENAI_API_KEY": "test-key",
        }):
            self.assertFalse(EmbeddingProvider().enabled)

    def test_semantic_search_requires_an_api_key(self):
        from embeddings import EmbeddingProvider
        with patch.dict(os.environ, {
            "ENABLE_SEMANTIC_SEARCH": "true",
            "OPENAI_API_KEY": "",
        }):
            self.assertFalse(EmbeddingProvider().enabled)


class EmbeddingSchemaMigrationTests(unittest.TestCase):
    def test_existing_document_database_gets_embedding_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "iskra_knowledge.sqlite3")
            tenant = knowledge.create_tenant(db_path, "Migracja")
            knowledge.add_document(db_path, tenant["tenant_id"], "stary.txt", b"Stary dokument.")
            with sqlite3.connect(db_path) as connection:
                connection.execute("ALTER TABLE document_chunks DROP COLUMN embedding_json")
                connection.commit()
            knowledge._INITIALIZED_PATHS.pop(os.path.abspath(db_path), None)
            knowledge.initialize(db_path)
            with sqlite3.connect(db_path) as connection:
                columns = {row[1] for row in connection.execute("PRAGMA table_info(document_chunks)")}
            self.assertIn("embedding_json", columns)


if __name__ == "__main__":
    unittest.main(verbosity=2)
