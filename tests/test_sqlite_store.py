import tempfile
import unittest
from pathlib import Path

from iskra.storage.sqlite import SQLiteGraphStore


class SQLiteGraphStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "iskra.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip_persists_graph_for_bound_tenant(self):
        store = SQLiteGraphStore(self.db_path, tenant_id="tenant-a")
        graph = {
            "neurons": {
                "n_logika": {"label": "Logika", "weight": 1.0, "created": 1.0},
                "n_test": {"label": "Test", "weight": 0.7, "created": 2.0},
            },
            "synapses": [{"from": "n_logika", "to": "n_test", "strength": 0.8}],
        }
        store.save(graph)
        self.assertEqual(store.load(), graph)

    def test_tenants_cannot_read_each_others_graphs(self):
        tenant_a = SQLiteGraphStore(self.db_path, tenant_id="tenant-a")
        tenant_b = SQLiteGraphStore(self.db_path, tenant_id="tenant-b")
        tenant_a.save({
            "neurons": {"private-a": {"label": "Poufne A", "weight": 0.9, "created": 1}},
            "synapses": [],
        })
        tenant_b.save({
            "neurons": {"private-b": {"label": "Poufne B", "weight": 0.8, "created": 2}},
            "synapses": [],
        })
        self.assertEqual(set(tenant_a.load()["neurons"]), {"private-a"})
        self.assertEqual(set(tenant_b.load()["neurons"]), {"private-b"})

    def test_invalid_graph_rolls_back_without_destroying_previous_snapshot(self):
        store = SQLiteGraphStore(self.db_path, tenant_id="tenant-a")
        original = {
            "neurons": {"n1": {"label": "Pierwotny", "weight": 0.5, "created": 1}},
            "synapses": [],
        }
        store.save(original)
        invalid = {
            "neurons": {"n2": {"label": "Nowy", "weight": 0.5, "created": 2}},
            "synapses": [{"from": "n2", "to": "missing", "strength": 0.5}],
        }
        with self.assertRaises(ValueError):
            store.save(invalid)
        self.assertEqual(store.load(), original)

    def test_empty_tenant_id_is_rejected(self):
        with self.assertRaises(ValueError):
            SQLiteGraphStore(self.db_path, tenant_id=" ")


if __name__ == "__main__":
    unittest.main(verbosity=2)
