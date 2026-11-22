import io
import json
import os
import tempfile
import unittest

import knowledge
from security import ApiTokenMiddleware


class TenantKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "iskra.sqlite3")
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
        middleware = ApiTokenMiddleware(app, token="admin-secret")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
