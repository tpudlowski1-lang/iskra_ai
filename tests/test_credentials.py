import os
import tempfile
import unittest

from iskra.security.credentials import SQLiteCredentialStore
from iskra.security.principal import Principal


class TrackingSQLiteCredentialStore(SQLiteCredentialStore):
    def __init__(self, database_path):
        self.opened_connections = []
        super().__init__(database_path)
        self.opened_connections.clear()

    def _connect(self):
        connection = super()._connect()
        self.opened_connections.append(connection)
        return connection


class SQLiteCredentialStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "credentials.sqlite3")
        self.store = SQLiteCredentialStore(self.database_path)
        self.principal = Principal(
            subject="user-123",
            tenant_id="tenant-alpha",
            roles=frozenset({"member"}),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_issue_authenticate_and_revoke_close_every_sqlite_connection(self):
        store = TrackingSQLiteCredentialStore(
            os.path.join(self.temp_dir.name, "tracked-credentials.sqlite3")
        )
        issued = store.issue(self.principal)
        self.assertEqual(store.authenticate(issued.token), self.principal)
        self.assertTrue(store.revoke(issued.credential_id))
        self.assertGreaterEqual(len(store.opened_connections), 3)

        for connection in store.opened_connections:
            with self.assertRaises(Exception):
                connection.execute("SELECT 1")

    def test_issue_and_authenticate_returns_server_bound_principal(self):
        issued = self.store.issue(self.principal)
        authenticated = self.store.authenticate(issued.token)
        self.assertEqual(authenticated, self.principal)
        self.assertNotEqual(issued.token, issued.credential_id)

    def test_raw_token_is_not_persisted(self):
        issued = self.store.issue(self.principal)
        with open(self.database_path, "rb") as database:
            contents = database.read()
        self.assertNotIn(issued.token.encode("utf-8"), contents)
        self.assertEqual(os.stat(self.database_path).st_mode & 0o777, 0o600)

    def test_tenant_and_roles_are_taken_from_registry_record(self):
        issued = self.store.issue(self.principal)
        authenticated = self.store.authenticate(issued.token)
        self.assertEqual(authenticated.tenant_id, "tenant-alpha")
        self.assertEqual(authenticated.roles, frozenset({"member"}))

    def test_unknown_and_malformed_tokens_fail_closed(self):
        self.assertIsNone(self.store.authenticate("not-a-real-token"))
        self.assertIsNone(self.store.authenticate(""))
        self.assertIsNone(self.store.authenticate(None))
        self.assertIsNone(self.store.authenticate("x" * 513))

    def test_expired_token_is_rejected(self):
        issued = self.store.issue(self.principal, expires_at=4_000_000_000)
        self.assertEqual(
            self.store.authenticate(issued.token, now=3_999_999_999),
            self.principal,
        )
        self.assertIsNone(self.store.authenticate(issued.token, now=4_000_000_000))

    def test_already_expired_token_cannot_be_issued(self):
        with self.assertRaises(ValueError):
            self.store.issue(self.principal, expires_at=1)

    def test_revoked_token_is_rejected_and_revocation_is_idempotent(self):
        issued = self.store.issue(self.principal)
        self.assertTrue(self.store.revoke(issued.credential_id))
        self.assertIsNone(self.store.authenticate(issued.token))
        self.assertFalse(self.store.revoke(issued.credential_id))

    def test_revocation_of_unknown_credential_returns_false(self):
        self.assertFalse(self.store.revoke("missing"))

    def test_non_principal_cannot_receive_a_credential(self):
        with self.assertRaises(TypeError):
            self.store.issue({"subject": "user", "tenant_id": "tenant-alpha"})


if __name__ == "__main__":
    unittest.main()
