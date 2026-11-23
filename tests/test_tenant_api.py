import hashlib
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask

from iskra.api.routes import create_api_blueprint
from iskra.storage.sqlite import SQLiteGraphStore
from security import ApiTokenMiddleware


PILLARS = [
    "n_logika", "n_epistemologia", "n_etyka", "n_ontologia",
    "n_przyrodnicze", "n_spoleczne", "n_jezyk", "n_historia",
    "n_technologia", "n_sztuka", "n_zdrowie", "n_metapoznanie",
]


def make_foundation():
    return {
        "neurons": {
            node_id: {"label": node_id, "weight": 1.0, "created": 1.0}
            for node_id in PILLARS
        },
        "synapses": [
            {"from": "n_logika", "to": "n_epistemologia", "strength": 0.95},
            {"from": "n_logika", "to": "n_technologia", "strength": 0.90},
        ],
    }


class TenantGraphApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.database = str(Path(self.tmp.name) / "tenant-graphs.sqlite3")
        self.token_a = "tenant-a-high-entropy-test-token"
        self.token_b = "tenant-b-high-entropy-test-token"
        records = []
        for token, subject, tenant_id in [
            (self.token_a, "member-a", "tenant-a"),
            (self.token_b, "member-b", "tenant-b"),
        ]:
            records.append({
                "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
                "subject": subject,
                "tenant_id": tenant_id,
                "roles": ["member"],
            })
        credentials = json.dumps(records)

        class Graph:
            fundament = make_foundation()

        graph = Graph()

        def store_factory(tenant_id):
            return SQLiteGraphStore(self.database, tenant_id=tenant_id)

        app = Flask(__name__)
        app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
        app.register_blueprint(create_api_blueprint(graph, tenant_store_factory=store_factory))
        app.wsgi_app = ApiTokenMiddleware(
            app.wsgi_app,
            token="system-admin-test-token",
            credentials_json=credentials,
        )
        self.client = app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    def test_load_or_initialize_preserves_an_existing_tenant_graph(self):
        store = SQLiteGraphStore(self.database, tenant_id="tenant-existing")
        existing = make_foundation()
        existing["neurons"]["tenant-private"] = {
            "label": "Istniejące dane", "weight": 0.7, "created": 4.0
        }
        store.save(existing)

        result = store.load_or_initialize(make_foundation())

        self.assertIn("tenant-private", result["neurons"])
        self.assertEqual(result, store.load())

    def test_concurrent_first_reads_initialize_tenant_exactly_once(self):
        tenant_id = "tenant-concurrent"
        stores = [
            SQLiteGraphStore(self.database, tenant_id=tenant_id)
            for _ in range(8)
        ]

        def initialize(index):
            graph = make_foundation()
            graph["neurons"][f"initializer-{index}"] = {
                "label": f"initializer-{index}", "weight": 0.5, "created": float(index)
            }
            return stores[index].load_or_initialize(graph)

        with ThreadPoolExecutor(max_workers=len(stores)) as executor:
            snapshots = list(executor.map(initialize, range(len(stores))))

        self.assertTrue(all(snapshot == snapshots[0] for snapshot in snapshots))
        markers = [
            node_id for node_id in snapshots[0]["neurons"]
            if node_id.startswith("initializer-")
        ]
        self.assertEqual(len(markers), 1)
        self.assertEqual(len(snapshots[0]["neurons"]), len(PILLARS) + 1)

    def test_tenant_get_starts_with_all_twelve_foundational_pillars(self):
        response = self.client.get("/api/tenant/network", headers=self.auth(self.token_a))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.get_json()["neurons"]), set(PILLARS))

    def test_write_is_bound_to_authenticated_tenant_not_body_or_header(self):
        graph = make_foundation()
        graph["neurons"]["private-a"] = {
            "label": "Poufne tenant A", "weight": 0.8, "created": 2.0
        }
        graph["tenant_id"] = "tenant-b"
        response = self.client.put(
            "/api/tenant/network?tenant_id=tenant-b",
            headers={**self.auth(self.token_a), "X-Tenant-ID": "tenant-b"},
            json=graph,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["tenant_id"], "tenant-a")

        tenant_a = self.client.get("/api/tenant/network", headers=self.auth(self.token_a))
        tenant_b = self.client.get("/api/tenant/network", headers=self.auth(self.token_b))
        self.assertIn("private-a", tenant_a.get_json()["neurons"])
        self.assertNotIn("private-a", tenant_b.get_json()["neurons"])

    def test_tenant_cannot_select_another_tenant_with_query_parameter(self):
        response = self.client.get(
            "/api/tenant/network?tenant_id=tenant-a",
            headers=self.auth(self.token_b),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.get_json()["neurons"]), set(PILLARS))
        self.assertNotIn("private-a", response.get_json()["neurons"])

    def test_tenant_write_cannot_remove_foundational_pillars(self):
        graph = make_foundation()
        del graph["neurons"]["n_logika"]
        response = self.client.put(
            "/api/tenant/network",
            headers=self.auth(self.token_a),
            json=graph,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "foundational_pillars_required")

    def test_tenant_write_cannot_remove_foundational_connections(self):
        graph = make_foundation()
        graph["synapses"] = []
        response = self.client.put(
            "/api/tenant/network",
            headers=self.auth(self.token_a),
            json=graph,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "foundational_connections_required")

    def test_invalid_graph_does_not_destroy_existing_tenant_snapshot(self):
        valid = make_foundation()
        valid["neurons"]["private-a"] = {
            "label": "Poufne", "weight": 0.7, "created": 3.0
        }
        saved = self.client.put(
            "/api/tenant/network",
            headers=self.auth(self.token_a),
            json=valid,
        )
        self.assertEqual(saved.status_code, 200)

        invalid = make_foundation()
        invalid["synapses"].append({
            "from": "n_logika", "to": "missing-node", "strength": 0.5
        })
        response = self.client.put(
            "/api/tenant/network",
            headers=self.auth(self.token_a),
            json=invalid,
        )
        self.assertEqual(response.status_code, 400)
        restored = self.client.get("/api/tenant/network", headers=self.auth(self.token_a))
        self.assertIn("private-a", restored.get_json()["neurons"])

    def test_tenant_endpoint_rejects_missing_credentials(self):
        response = self.client.get("/api/tenant/network")
        self.assertEqual(response.status_code, 401)

    def test_tenant_write_requires_json(self):
        response = self.client.put(
            "/api/tenant/network",
            headers=self.auth(self.token_a),
            data="not json",
            content_type="text/plain",
        )
        self.assertEqual(response.status_code, 415)


if __name__ == "__main__":
    unittest.main(verbosity=2)
