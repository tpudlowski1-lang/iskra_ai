import tempfile
import unittest

from flask import Flask

from iskra.api.routes import create_api_blueprint
from iskra.security.principal import Principal
from iskra.security.sqlite_credentials import SQLiteCredentialStore
from security import ApiTokenMiddleware


class TenantCredentialApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SQLiteCredentialStore(f"{self.tmp.name}/private/credentials.sqlite3")
        self.alpha_admin = Principal("alpha-admin", "tenant-alpha", frozenset({"admin"}))
        self.alpha_member = Principal("alpha-member", "tenant-alpha", frozenset({"member"}))
        self.beta_admin = Principal("beta-admin", "tenant-beta", frozenset({"admin"}))
        self.alpha_admin_token = self.store.issue(self.alpha_admin).token
        self.alpha_member_token = self.store.issue(self.alpha_member).token
        self.beta_admin_token = self.store.issue(self.beta_admin).token

        class Graph:
            fundament = {"neurons": {}, "synapses": []}
            dane = {"neurons": {}, "synapses": []}

        self.app = Flask(__name__)
        self.app.config["ISKRA_CREDENTIAL_STORE"] = self.store
        self.app.register_blueprint(create_api_blueprint(Graph()))
        self.app.wsgi_app = ApiTokenMiddleware(
            self.app.wsgi_app,
            token="system-admin-token",
            credentials_json="",
            credential_store=self.store,
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def auth(token):
        return {"Authorization": f"Bearer {token}"}

    def test_tenant_admin_can_issue_member_token_bound_to_their_tenant(self):
        response = self.client.post(
            "/api/tenant/credentials",
            headers=self.auth(self.alpha_admin_token),
            json={"subject": "new-user"},
        )
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertTrue(body["token"])
        self.assertEqual(body["tenant_id"], "tenant-alpha")
        self.assertEqual(body["roles"], ["member"])
        resolved = self.store.authenticate(body["token"])
        self.assertEqual(resolved, Principal("new-user", "tenant-alpha", frozenset({"member"})))

    def test_tenant_id_cannot_be_supplied_by_request(self):
        response = self.client.post(
            "/api/tenant/credentials",
            headers=self.auth(self.alpha_admin_token),
            json={"subject": "attacker", "tenant_id": "tenant-beta", "roles": ["admin"]},
        )
        self.assertEqual(response.status_code, 400)

    def test_member_cannot_manage_credentials(self):
        response = self.client.get(
            "/api/tenant/credentials",
            headers=self.auth(self.alpha_member_token),
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            "/api/tenant/credentials",
            headers=self.auth(self.alpha_member_token),
            json={"subject": "new-user"},
        )
        self.assertEqual(response.status_code, 403)

    def test_list_is_tenant_scoped_and_never_returns_token_material(self):
        self.store.issue(Principal("alpha-user", "tenant-alpha", frozenset({"member"})))
        self.store.issue(Principal("beta-user", "tenant-beta", frozenset({"member"})))
        response = self.client.get(
            "/api/tenant/credentials",
            headers=self.auth(self.alpha_admin_token),
        )
        self.assertEqual(response.status_code, 200)
        rows = response.get_json()["credentials"]
        self.assertTrue(rows)
        self.assertTrue(all(row["tenant_id"] == "tenant-alpha" for row in rows))
        for row in rows:
            self.assertNotIn("token", row)
            self.assertNotIn("token_digest", row)
            self.assertNotIn("token_sha256", row)

    def test_tenant_admin_cannot_revoke_another_tenants_credential(self):
        beta_credential = self.store.issue(
            Principal("beta-user", "tenant-beta", frozenset({"member"}))
        )
        response = self.client.delete(
            f"/api/tenant/credentials/{beta_credential.credential_id}",
            headers=self.auth(self.alpha_admin_token),
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self.store.authenticate(beta_credential.token),
            Principal("beta-user", "tenant-beta", frozenset({"member"})),
        )

    def test_tenant_admin_can_revoke_own_tenant_credential(self):
        target = self.store.issue(
            Principal("alpha-user", "tenant-alpha", frozenset({"member"}))
        )
        response = self.client.delete(
            f"/api/tenant/credentials/{target.credential_id}",
            headers=self.auth(self.alpha_admin_token),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.store.authenticate(target.token))

    def test_rotation_revokes_old_token_and_returns_new_token_once(self):
        target = self.store.issue(
            Principal("alpha-user", "tenant-alpha", frozenset({"admin"}))
        )
        response = self.client.post(
            f"/api/tenant/credentials/{target.credential_id}/rotate",
            headers=self.auth(self.alpha_admin_token),
            json={"roles": ["member"]},
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["token"])
        self.assertIsNone(self.store.authenticate(target.token))
        self.assertEqual(
            self.store.authenticate(body["token"]),
            Principal("alpha-user", "tenant-alpha", frozenset({"member"})),
        )

    def test_rotation_cannot_escalate_roles(self):
        target = self.store.issue(
            Principal("alpha-user", "tenant-alpha", frozenset({"member"}))
        )
        response = self.client.post(
            f"/api/tenant/credentials/{target.credential_id}/rotate",
            headers=self.auth(self.alpha_admin_token),
            json={"roles": ["admin"]},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self.store.authenticate(target.token),
            Principal("alpha-user", "tenant-alpha", frozenset({"member"})),
        )

    def test_tenant_admin_cannot_rotate_another_tenants_credential(self):
        target = self.store.issue(
            Principal("beta-user", "tenant-beta", frozenset({"member"}))
        )
        response = self.client.post(
            f"/api/tenant/credentials/{target.credential_id}/rotate",
            headers=self.auth(self.alpha_admin_token),
            json={},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self.store.authenticate(target.token),
            Principal("beta-user", "tenant-beta", frozenset({"member"})),
        )

    def test_missing_persistent_store_returns_503(self):
        del self.app.config["ISKRA_CREDENTIAL_STORE"]
        response = self.client.get(
            "/api/tenant/credentials",
            headers=self.auth(self.alpha_admin_token),
        )
        self.assertEqual(response.status_code, 503)

    def test_credential_audit_records_tenant_admin_actor(self):
        response = self.client.post(
            "/api/tenant/credentials",
            headers=self.auth(self.alpha_admin_token),
            json={"subject": "audit-user"},
        )
        self.assertEqual(response.status_code, 201)
        events = self.store.list_audit_events()
        issued = next(item for item in events if item["event_type"] == "credential_issued"
                      and item["subject"] == "audit-user")
        self.assertEqual(issued["actor"], "alpha-admin")
        self.assertEqual(issued["tenant_id"], "tenant-alpha")

    def test_reserved_system_admin_cannot_use_tenant_account_api(self):
        response = self.client.get(
            "/api/tenant/credentials",
            headers=self.auth("system-admin-token"),
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
