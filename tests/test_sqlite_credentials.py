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

    def test_credential_ids_have_cli_safe_prefix(self):
        issued = self.store.issue(self.principal)
        self.assertTrue(issued.credential_id.startswith("cred_"))

    def test_issue_writes_audit_event_without_token_material(self):
        issued = self.store.issue(self.principal, actor="operator-7")
        events = self.store.list_audit_events()
        self.assertEqual(events[0]["event_type"], "credential_issued")
        self.assertEqual(events[0]["credential_id"], issued.credential_id)
        self.assertEqual(events[0]["actor"], "operator-7")
        self.assertNotIn("token", events[0])
        self.assertNotIn("token_digest", events[0])

    def test_revoke_writes_audit_event(self):
        issued = self.store.issue(self.principal)
        self.assertTrue(self.store.revoke(issued.credential_id, actor="operator-8"))
        event = next(
            item for item in self.store.list_audit_events()
            if item["event_type"] == "credential_revoked"
        )
        self.assertEqual(event["credential_id"], issued.credential_id)
        self.assertEqual(event["actor"], "operator-8")

    def test_rotation_atomically_replaces_token_and_preserves_principal(self):
        issued = self.store.issue(self.principal, expires_at=4_000_000_000)
        rotated = self.store.rotate(issued.credential_id, actor="operator-9")
        self.assertIsNone(self.store.authenticate(issued.token))
        self.assertEqual(self.store.authenticate(rotated.token), self.principal)
        self.assertEqual(rotated.expires_at, 4_000_000_000)
        event = next(
            item for item in self.store.list_audit_events()
            if item["event_type"] == "credential_rotated"
        )
        self.assertEqual(event["credential_id"], issued.credential_id)
        self.assertEqual(event["related_credential_id"], rotated.credential_id)
        self.assertEqual(event["actor"], "operator-9")

    def test_rotation_can_reduce_but_never_escalate_roles(self):
        admin_principal = Principal(
            "tenant-admin", "tenant-blue", frozenset({"admin", "member"})
        )
        issued = self.store.issue(admin_principal)
        with self.assertRaises(ValueError):
            self.store.rotate(issued.credential_id, roles={"admin", "member", "owner"})
        self.assertEqual(self.store.authenticate(issued.token), admin_principal)
        rotated = self.store.rotate(issued.credential_id, roles={"member"})
        self.assertEqual(
            self.store.authenticate(rotated.token),
            Principal("tenant-admin", "tenant-blue", frozenset({"member"})),
        )

    def test_rotation_failure_does_not_revoke_old_credential(self):
        issued = self.store.issue(self.principal)
        with self.assertRaises(ValueError):
            self.store.rotate(issued.credential_id, roles={"admin"})
        self.assertEqual(self.store.authenticate(issued.token), self.principal)

    def test_rotation_rejects_revoked_credentials(self):
        issued = self.store.issue(self.principal, expires_at=4_000_000_000)
        self.store.revoke(issued.credential_id)
        with self.assertRaises(ValueError):
            self.store.rotate(issued.credential_id)

    def test_rotation_rejects_expired_credentials(self):
        issued = self.store.issue(self.principal)
        with self.store._connection() as connection:
            with connection:
                connection.execute(
                    "UPDATE api_credentials SET expires_at = 1 WHERE credential_id = ?",
                    (issued.credential_id,),
                )
        with self.assertRaises(ValueError):
            self.store.rotate(issued.credential_id)

    def test_audit_limit_is_bounded(self):
        with self.assertRaises(ValueError):
            self.store.list_audit_events(limit=0)
        with self.assertRaises(ValueError):
            self.store.list_audit_events(limit=501)

    def test_invalid_actor_is_rejected(self):
        with self.assertRaises(ValueError):
            self.store.issue(self.principal, actor="bad\x01operator")

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
