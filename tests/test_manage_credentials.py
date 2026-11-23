import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from iskra.security.principal import Principal
from iskra.security.sqlite_credentials import SQLiteCredentialStore
from scripts.manage_credentials import main


class ManageCredentialsCliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "credentials.sqlite3")
        self.store = SQLiteCredentialStore(self.database_path)
        self.environment = {
            "ISKRA_CREDENTIAL_DB_PATH": self.database_path,
            "ISKRA_OPERATOR_ID": "cli-operator",
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_cli(self, args):
        output = io.StringIO()
        with patch.dict(os.environ, self.environment, clear=False):
            with redirect_stdout(output):
                result = main(args)
        return result, output.getvalue()

    def test_issue_requires_explicit_confirmation(self):
        errors = io.StringIO()
        with patch.dict(os.environ, self.environment, clear=False):
            with redirect_stderr(errors):
                with self.assertRaises(SystemExit):
                    main([
                        "issue", "--subject", "member-1",
                        "--tenant-id", "tenant-blue",
                    ])
        self.assertIn("--confirm", errors.getvalue())
        self.assertEqual(self.store.list_audit_events(), [])

    def test_issue_returns_one_time_token_and_audits_actor(self):
        result, output = self.run_cli([
            "issue", "--subject", "member-1",
            "--tenant-id", "tenant-blue", "--confirm",
        ])
        payload = json.loads(output)
        self.assertEqual(result, 0)
        principal = self.store.authenticate(payload["token"])
        self.assertEqual(
            principal,
            Principal("member-1", "tenant-blue", frozenset({"member"})),
        )
        self.assertEqual(self.store.list_audit_events()[0]["actor"], "cli-operator")

    def test_admin_role_requires_second_confirmation(self):
        errors = io.StringIO()
        with patch.dict(os.environ, self.environment, clear=False):
            with redirect_stderr(errors):
                with self.assertRaises(SystemExit):
                    main([
                        "issue", "--subject", "tenant-admin",
                        "--tenant-id", "tenant-blue", "--roles", "admin,member",
                        "--confirm",
                    ])
        self.assertIn("--allow-admin", errors.getvalue())
        self.assertEqual(self.store.list_audit_events(), [])

    def test_rotate_replaces_token_and_reports_preserved_expiry(self):
        old = self.store.issue(
            Principal("member-2", "tenant-green", frozenset({"member"})),
            expires_at=4_000_000_000,
        )
        result, output = self.run_cli([
            "rotate", "--credential-id", old.credential_id, "--confirm",
        ])
        payload = json.loads(output)
        self.assertEqual(result, 0)
        self.assertEqual(payload["expires_at"], "2096-10-02T07:06:40+00:00")
        self.assertIsNone(self.store.authenticate(old.token))
        self.assertEqual(
            self.store.authenticate(payload["token"]),
            Principal("member-2", "tenant-green", frozenset({"member"})),
        )

    def test_revoke_and_audit_commands(self):
        issued = self.store.issue(
            Principal("member-3", "tenant-red", frozenset({"member"}))
        )
        result, output = self.run_cli([
            "revoke", "--credential-id", issued.credential_id, "--confirm",
        ])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output)["status"], "revoked")
        result, output = self.run_cli(["audit", "--limit", "10"])
        self.assertEqual(result, 0)
        events = json.loads(output)
        self.assertEqual(events[0]["event_type"], "credential_revoked")
        self.assertTrue(all("token" not in event for event in events))


if __name__ == "__main__":
    unittest.main()
