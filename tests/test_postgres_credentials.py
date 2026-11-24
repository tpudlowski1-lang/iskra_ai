"""Exercise two independent credential clients against a disposable PostgreSQL database."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from iskra.security.credential_store import CredentialStoreUnavailable, LastTenantAdminError
from iskra.security.postgres_credentials import PostgresCredentialStore
from iskra.security.principal import Principal
from iskra.security.store_config import credential_store_from_env

ROOT = Path(__file__).resolve().parents[1]
ADMIN = os.environ.get("ISKRA_TEST_POSTGRES_ADMIN_DSN")


@unittest.skipUnless(ADMIN, "Disposable PostgreSQL integration service is not configured")
class PostgresCredentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # CI supplies an administrator for a disposable PostgreSQL service.
        cls.control = psycopg.connect(ADMIN, autocommit=True)
        cls.addClassCleanup(cls.control.close)
        cls.suffix = uuid4().hex[:12]
        cls.secret = secrets.token_hex(32)
        cls.database = "iskra_auth_test_" + cls.suffix
        cls.logins = {}
        for group in ("iskra_auth_owner", "iskra_auth_runtime", "iskra_auth_operator"):
            if not cls.control.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (group,)).fetchone():
                cls.control.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(group)))
        for role in ("runtime", "operator", "graph"):
            name = f"test_{role}_{cls.suffix}"
            password = secrets.token_urlsafe(36)
            cls.control.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(name), sql.Literal(password)))
            cls.addClassCleanup(cls.control.execute, sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))
            if role != "graph":
                cls.control.execute(sql.SQL("GRANT {} TO {}").format(
                    sql.Identifier("iskra_auth_" + role), sql.Identifier(name)))
            cls.logins[role] = make_conninfo(ADMIN, dbname=cls.database, user=name, password=password)
        cls.create_empty_database(cls.database)
        cls.admin = make_conninfo(ADMIN, dbname=cls.database)
        with psycopg.connect(cls.admin) as conn:
            conn.execute("CREATE SCHEMA iskra_auth AUTHORIZATION iskra_auth_owner")
            for filename in ("0001_tenant_graph.sql", "0002_tenant_documents.sql", "0003_credential_store.sql"):
                conn.execute((ROOT / "migrations" / filename).read_text(), prepare=False)
            conn.execute("RESET ROLE")
            conn.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON public.iskra_graph_neurons, "
                                 "public.iskra_graph_synapses, public.iskra_tenant_documents, "
                                 "public.iskra_tenant_document_chunks TO {}").format(
                                     sql.Identifier("test_graph_" + cls.suffix)))
        cls.operator = PostgresCredentialStore(cls.logins["operator"], "", operator=True)
        cls.addClassCleanup(cls.operator.close)
        cls.clients = []
        for _ in range(2):
            client = PostgresCredentialStore(cls.logins["runtime"], cls.secret)
            cls.clients.append(client)
            cls.addClassCleanup(client.close)

    @classmethod
    def create_empty_database(cls, name):
        ident = sql.Identifier(name)
        cls.control.execute(sql.SQL("CREATE DATABASE {}").format(ident))
        cls.addClassCleanup(cls.control.execute, sql.SQL("DROP DATABASE {} WITH (FORCE)").format(ident))

    def setUp(self):
        self.principal = Principal("pilot", "tenant-" + uuid4().hex, frozenset({"admin"}))
        self.key = self.operator.issue(self.principal)

    def create_session(self):
        session = secrets.token_urlsafe(48)
        store = self.clients[0]
        csrf = store.issue_browser_csrf_token(session)
        expiry = store.create_browser_session(self.principal, self.key.credential_id, session, csrf, time.time() + 300)
        return session, csrf, expiry

    def test_session_lifecycle_across_clients_and_digests_only(self):
        first, second = self.clients
        self.assertEqual(second.authenticate(self.key.token), self.principal)
        session, csrf, expiry = self.create_session()
        self.assertEqual(second.authenticate_browser_session(session).csrf_token, csrf)
        self.assertTrue(first.rotate_browser_session_csrf(session, csrf))
        self.assertIsNone(second.authenticate_browser_session(session, now=expiry))
        rotated_secret = PostgresCredentialStore(self.logins["runtime"], secrets.token_hex(32))
        self.addCleanup(rotated_secret.close)
        self.assertIsNone(rotated_secret.authenticate_browser_session(session))
        with psycopg.connect(self.admin) as conn:
            for table in ("api_credentials", "browser_sessions", "credential_audit_events"):
                rows = conn.execute(sql.SQL("SELECT row_to_json(t)::text FROM iskra_auth.{} t").format(
                    sql.Identifier(table))).fetchall()
                for row, in rows:
                    for raw in (session, csrf, self.key.token):
                        self.assertNotIn(raw, row)
        self.assertTrue(first.revoke_browser_session(session))
        self.assertIsNone(second.authenticate_browser_session(session))
        session, _, _ = self.create_session()
        replacement = self.operator.rotate(self.key.credential_id)
        self.assertIsNone(second.authenticate_browser_session(session))
        self.assertIsNone(first.authenticate(self.key.token))
        self.assertEqual(second.authenticate(replacement.token), self.principal)
        self.assertTrue(self.operator.revoke(replacement.credential_id))
        self.assertIsNone(second.authenticate(replacement.token))
        self.assertIn(self.key.credential_id, {r["credential_id"] for r in self.operator.list_audit_events()})

    def test_tenant_scope_and_last_admin_serialization(self):
        store = self.clients[0]
        other = Principal("other", "other-" + uuid4().hex, frozenset({"admin"}))
        foreign = self.operator.issue(other)
        self.assertFalse(store.revoke_for_tenant(self.principal, foreign.credential_id))
        with self.assertRaises(ValueError):
            store.rotate_for_tenant(self.principal, foreign.credential_id)
        added = store.issue_for_tenant(self.principal, "second", roles={"admin"})
        gate = threading.Barrier(2)
        def mutate(index):
            gate.wait(timeout=5)
            try:
                if index == 0:
                    self.clients[0].revoke_for_tenant(self.principal, self.key.credential_id)
                else:
                    self.clients[1].rotate_for_tenant(self.principal, added.credential_id, roles={"member"})
                return "changed"
            except LastTenantAdminError:
                return "preserved"
        with ThreadPoolExecutor(2) as workers:
            self.assertCountEqual(workers.map(mutate, (0, 1)), ("changed", "preserved"))
        rows = store.list_for_tenant(self.principal)
        self.assertEqual({r["tenant_id"] for r in rows}, {self.principal.tenant_id})
        self.assertEqual(sum(r["active"] and "admin" in r["roles"] for r in rows), 1)

    def test_bootstrap_privileges_schema_and_expiry(self):
        with psycopg.connect(self.logins["runtime"]) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM iskra_auth.api_credentials").fetchone(), (0,))
            self.assertEqual(conn.execute("SELECT count(*) FROM iskra_auth.lookup_session('missing')").fetchone(), (0,))
            self.assertFalse(conn.execute("SELECT has_table_privilege(current_user,"
                                          "'iskra_auth.credential_audit_events','SELECT')").fetchone()[0])
            fns = conn.execute("""
                SELECT p.prosecdef, owner.rolname, owner.rolcanlogin, p.proconfig,
                       has_function_privilege('public',p.oid,'EXECUTE')
                  FROM pg_proc p JOIN pg_roles owner ON owner.oid=p.proowner
                 WHERE p.pronamespace='iskra_auth'::regnamespace
            """).fetchall()
            self.assertEqual(len(fns), 2)
            for definer, owner, login, config, public in fns:
                self.assertEqual((definer, owner, login, public), (True, "iskra_auth_owner", False, False))
                self.assertIn("search_path=pg_catalog, pg_temp", config)
        with self.assertRaises(CredentialStoreUnavailable):
            PostgresCredentialStore(self.logins["operator"], self.secret)
        with self.assertRaises(CredentialStoreUnavailable):
            PostgresCredentialStore(make_conninfo(self.logins["runtime"], dbname="postgres"), self.secret)
        with self.assertRaises(ValueError):
            credential_store_from_env({"ISKRA_CREDENTIAL_STORE_BACKEND":"postgres", "ISKRA_POSTGRES_DSN":self.admin})
        with psycopg.connect(self.admin) as conn:
            conn.execute("UPDATE iskra_auth.api_credentials SET created_at=1, expires_at=2 WHERE credential_id=%s",
                         (self.key.credential_id,))
        self.assertIsNone(self.clients[1].authenticate(self.key.token))

    def test_pool_timeout_and_unrecognized_migration_fail_closed(self):
        from contextlib import ExitStack

        client = self.clients[1]
        with ExitStack() as held:
            for _ in range(4):
                held.enter_context(client.pool.connection())
            with self.assertRaises(CredentialStoreUnavailable):
                client.authenticate(self.key.token)
        self.assertEqual(client.authenticate(self.key.token), self.principal)
        with psycopg.connect(self.admin) as conn:
            conn.execute("INSERT INTO iskra_auth.schema_version VALUES (4)")
        try:
            with self.assertRaises(CredentialStoreUnavailable):
                PostgresCredentialStore(self.logins["runtime"], self.secret)
        finally:
            with psycopg.connect(self.admin) as conn:
                conn.execute("DELETE FROM iskra_auth.schema_version WHERE version=4")

    def test_transaction_rolls_back_rotation_if_audit_fails(self):
        # Constrain just this synthetic event so that audit insertion fails after the update.
        constraint = sql.Identifier("test_audit_" + uuid4().hex)
        with psycopg.connect(self.admin) as conn:
            conn.execute(sql.SQL("ALTER TABLE iskra_auth.credential_audit_events ADD CONSTRAINT {} "
                                 "CHECK (event_type <> 'credential_rotated' OR credential_id <> {})").format(
                                     constraint, sql.Literal(self.key.credential_id)))
        with self.assertRaises(CredentialStoreUnavailable):
            self.operator.rotate(self.key.credential_id)
        self.assertEqual(self.clients[0].authenticate(self.key.token), self.principal)
        self.assertEqual(len(self.clients[1].list_for_tenant(self.principal)), 1)

    def test_database_archive_restores_credentials_sessions_and_graph(self):
        from iskra.storage.postgres import PostgresGraphStore

        stage = PostgresGraphStore(self.logins["graph"], self.principal)
        stage.save({"neurons":{"sample":{"label":"pilot", "created":1, "weight":1}}, "synapses":[]})
        session, csrf, _ = self.create_session()
        restored_db = "restore_" + uuid4().hex[:12]
        self.create_empty_database(restored_db)
        options = conninfo_to_dict(self.admin)
        cli_env = {**os.environ, **{"PG" + key.upper(): val for key, val in options.items() if key != "dbname"}}
        with tempfile.TemporaryDirectory() as private:
            archive = str(Path(private) / "pilot.dump")
            subprocess.run(["pg_dump", "--dbname", self.database, "-Fc", "-f", archive],
                           env=cli_env, check=True, timeout=60)
            subprocess.run(["pg_restore", "--single-transaction", "--exit-on-error", "-d", restored_db, archive],
                           env=cli_env, check=True, timeout=60)
        restored = PostgresCredentialStore(make_conninfo(self.logins["runtime"], dbname=restored_db), self.secret)
        self.addCleanup(restored.close)
        self.assertEqual(restored.authenticate_browser_session(session).csrf_token, csrf)
        self.assertEqual(restored.authenticate(self.key.token), self.principal)
        recovered = PostgresGraphStore(make_conninfo(self.logins["graph"], dbname=restored_db), self.principal)
        self.assertEqual(recovered.load(), stage.load())

    def test_https_staging_restart_and_database_outage(self):
        import socket
        import requests

        # Only fixture credentials reach Gunicorn. Never inherit the CI admin DSN.
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory)
            cert, tls_key = private / "cert.pem", private / "key.pem"
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                            "-keyout", str(tls_key), "-out", str(cert), "-days", "1",
                            "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            admin_token = secrets.token_urlsafe(48)
            env = {
                "PATH": os.environ["PATH"], "DATA_DIR": directory,
                "API_TOKEN": admin_token, "ISKRA_CREDENTIAL_STORE_BACKEND": "postgres",
                "ISKRA_CREDENTIAL_POSTGRES_DSN": self.logins["runtime"], "ISKRA_CSRF_HMAC_SECRET": self.secret,
                "ISKRA_TENANT_STORAGE_BACKEND": "postgres", "ISKRA_DOCUMENT_STORAGE_BACKEND": "postgres",
                "ISKRA_POSTGRES_DSN": self.logins["graph"], "ISKRA_RATE_LIMIT_ENABLED":"true",
                "ENABLE_AUTONOMOUS_LOOP":"false", "ISKRA_ENABLE_DOCUMENT_INGESTION":"false",
                "LLM_ALLOWED_PROVIDERS":"", "ISKRA_TENANT_PROVIDER_ALLOWLIST_JSON":"{}",
            }
            browser = self.enterContext(requests.Session())
            browser.trust_env = False
            browser.verify = str(cert)

            @contextmanager
            def deployment():
                with socket.socket() as listener:
                    listener.bind(("127.0.0.1", 0))
                    listener.listen()
                    address = f"https://127.0.0.1:{listener.getsockname()[1]}"
                    proc = subprocess.Popen(
                        [sys.executable, "-m", "gunicorn", "wsgi:app", "--workers", "1", "--threads", "4",
                         "--bind", f"fd://{listener.fileno()}", "--certfile", str(cert), "--keyfile", str(tls_key)],
                        cwd=ROOT, env=env, pass_fds=(listener.fileno(),), stderr=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL)
                try:
                    for _ in range(80):
                        if proc.poll() is not None:
                            self.fail("Gunicorn exited before readiness")
                        try:
                            if browser.get(address + "/health", timeout=.5).status_code == 200:
                                break
                        except requests.RequestException:
                            pass
                        time.sleep(.05)
                    else:
                        self.fail("Gunicorn HTTPS readiness timed out")
                    yield address
                finally:
                    proc.terminate()
                    try:
                        proc.wait(timeout=12)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()

            def status(method, path, code, **kwargs):
                response = browser.request(method, address + path, timeout=12, **kwargs)
                self.assertEqual(response.status_code, code, f"{method} {path}")
                return response

            def login():
                return status("POST", "/api/browser/session", 201, json={},
                              headers={"Authorization": "Bearer " + self.key.token})

            with deployment() as address:
                status("GET", "/assistant", 200)
                status("GET", "/api/tenant/session", 401)
                status("POST", "/api/browser/session", 403, json={}, headers={"Authorization":"Bearer " + admin_token})
                response = login()
                for flag in ("__Host-iskra_session=", "HttpOnly", "Secure", "SameSite=Strict", "Path=/"):
                    self.assertIn(flag, response.headers["Set-Cookie"])
                csrf = response.json()["csrf_token"]
                with deployment() as peer:
                    shared = browser.get(peer + "/api/browser/session", timeout=4)
                    self.assertEqual(shared.status_code, 200)
                    self.assertEqual(shared.json()["csrf_token"], csrf)
                graph = status("GET", "/api/tenant/network", 200).json()
                graph["neurons"]["pilot_fixture"] = {"label":"test", "weight":0.8, "created":123}
                status("PUT", "/api/tenant/network", 403, json=graph)
                status("PUT", "/api/tenant/network", 403, json=graph, headers={"X-CSRF-Token":"incorrect"})
                status("PUT", "/api/tenant/network", 403, json=graph,
                       headers={"X-CSRF-Token":csrf, "Origin":"https://other.invalid"})
                status("PUT", "/api/tenant/network", 200, json=graph, headers={"X-CSRF-Token":csrf, "Origin":address})
            with deployment() as address:
                self.assertEqual(status("GET", "/api/browser/session", 200).json()["csrf_token"], csrf)
                self.assertIn("pilot_fixture", status("GET", "/api/tenant/network", 200).json()["neurons"])
                status("POST", "/api/browser/session/logout", 200, headers={"X-CSRF-Token":csrf, "Origin":address})
                status("GET", "/api/tenant/session", 401)
                login()
                self.operator.revoke(self.key.credential_id)
                status("GET", "/api/tenant/session", 401)
                # This is a newly created disposable test DB; keep the control connection in another database.
                alter = sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS ").format(sql.Identifier(self.database))
                self.control.execute(alter + sql.SQL("false"))
                try:
                    self.control.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s",
                                         (self.database,))
                    status("GET", "/api/tenant/session", 503, headers={"Authorization":"Bearer " + admin_token})
                finally:
                    self.control.execute(alter + sql.SQL("true"))
                status("GET", "/api/network", 200, headers={"Authorization":"Bearer " + admin_token})
