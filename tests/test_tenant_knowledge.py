import io
import json
import os
import sqlite3
import tempfile
import unittest

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

    def tearDown(self):
        self.iskra.app.wsgi_app = self.old_wsgi_app
        self.iskra.DATA_DIR = self.old_data_dir
        self.iskra.PLIK_SIECI = self.old_network_path
        self.tmp.cleanup()

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
