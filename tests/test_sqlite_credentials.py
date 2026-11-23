import os
import tempfile
import unittest

from iskra.security.principal import Principal
from iskra.security.sqlite_credentials import (
    CredentialStoreUnavailable,
    SQLiteCredentialStore,
)


class SQLiteCredentialStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp_dir.name, "secrets", "credentials.sqlite3")
        self.store = SQLiteCredentialStore(self.path)
        self.principal = Principal("member-17", "tenant-blue", frozenset({"member"}))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_issue_and_authenticate_round_trip(self):
        issued = self.store.issue(self.principal)
        self.assertEqual(self.store.authenticate(issued.token), self.principal)
        self.assertNotEqual(issued.token, issued.credential_id)

    def test_database_never_contains_plaintext_token(self):
        issued = self.store.issue(self.principal)
        with open(self.path, "rb") as handle:
            database = handle.read()
        self.assertNotIn(issued.token.encode(), database)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_unknown_malformed_and_oversized_tokens_fail_closed(self):
        self.assertIsNone(self.store.authenticate("unknown"))
        self.assertIsNone(self.store.authenticate(""))
        self.assertIsNone(self.store.authenticate(None))
        self.assertIsNone(self.store.authenticate("x" * 513))

    def test_expiry_is_enforced(self):
        issued = self.store.issue(self.principal, expires_at=4_000_000_000)
        self.assertEqual(self.store.authenticate(issued.token, now=3_999_999_999), self.principal)
        self.assertIsNone(self.store.authenticate(issued.token, now=4_000_000_000))

    def test_expired_credentials_cannot_be_issued(self):
        with self.assertRaises(ValueError):
            self.store.issue(self.principal, expires_at=1)

    def test_revocation_is_immediate_and_idempotent(self):
        issued = self.store.issue(self.principal)
        self.assertTrue(self.store.revoke(issued.credential_id))
        self.assertIsNone(self.store.authenticate(issued.token))
        self.assertFalse(self.store.revoke(issued.credential_id))

    def test_non_principal_cannot_be_issued_a_credential(self):
        with self.assertRaises(TypeError):
            self.store.issue({"subject": "member", "tenant_id": "tenant-blue"})

    def test_invalid_database_path_is_rejected(self):
        with self.assertRaises(ValueError):
            SQLiteCredentialStore(":memory:")

    def test_symbolic_link_database_path_is_rejected(self):
        target = os.path.join(self.temp_dir.name, "target.sqlite3")
        with open(target, "wb") as handle:
            handle.write(b"not a database")
        link = os.path.join(self.temp_dir.name, "linked.sqlite3")
        try:
            os.symlink(target, link)
        except (AttributeError, NotImplementedError, OSError):
            self.skipTest("Symlinks are unavailable on this platform")
        with self.assertRaises(CredentialStoreUnavailable):
            SQLiteCredentialStore(link)


if __name__ == "__main__":
    unittest.main()
