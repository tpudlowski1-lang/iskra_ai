import os
import tempfile
import unittest

from iskra.security.principal import Principal, SYSTEM_ADMIN
from iskra.storage.tenant import TenantGraphStoreFactory
from iskra.storage.postgres import PostgresGraphStore


class TenantGraphStoreFactoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "tenant-graphs.sqlite3")
        self.factory = TenantGraphStoreFactory(self.database_path)
        self.alpha = Principal("alice", "tenant-alpha", frozenset({"member"}))
        self.beta = Principal("bob", "tenant-beta", frozenset({"member"}))
        self.alpha_store = self.factory.for_principal(self.alpha)
        self.beta_store = self.factory.for_principal(self.beta)

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def graph(label):
        return {
            "neurons": {
                "node-1": {"label": label, "weight": 0.7, "created": 100.0}
            },
            "synapses": [],
        }

    def test_factory_requires_verified_principal(self):
        with self.assertRaises(PermissionError):
            self.factory.for_principal(None)
        with self.assertRaises(PermissionError):
            self.factory.for_principal({
                "subject": "attacker", "tenant_id": "tenant-alpha",
                "roles": ["admin"],
            })

    def test_system_principal_cannot_be_mistaken_for_customer_tenant(self):
        with self.assertRaises(PermissionError):
            self.factory.for_principal(SYSTEM_ADMIN)

    def test_two_tenants_are_isolated_in_same_database(self):
        self.alpha_store.save(self.graph("alpha private data"))
        self.beta_store.save(self.graph("beta private data"))
        self.assertEqual(
            self.alpha_store.load()["neurons"]["node-1"]["label"],
            "alpha private data",
        )
        self.assertEqual(
            self.beta_store.load()["neurons"]["node-1"]["label"],
            "beta private data",
        )

    def test_write_by_one_tenant_does_not_modify_another_tenant(self):
        self.alpha_store.save(self.graph("alpha initial"))
        self.beta_store.save(self.graph("beta initial"))
        self.alpha_store.save(self.graph("alpha updated"))
        self.assertEqual(
            self.beta_store.load()["neurons"]["node-1"]["label"],
            "beta initial",
        )

    def test_factory_scope_is_derived_from_principal_not_external_input(self):
        store = self.factory.for_principal(self.alpha)
        store.save(self.graph("alpha only"))
        # A caller-supplied tenant header or query value is not accepted by this API.
        self.assertEqual(store.tenant_id, "tenant-alpha")
        self.assertNotEqual(store.tenant_id, "tenant-attacker")



    def test_postgres_factory_uses_verified_principal(self):
        factory = TenantGraphStoreFactory(
            backend="postgres",
            postgres_dsn="postgresql://app:secret@localhost/iskra",
        )
        store = factory.for_principal(self.alpha)
        self.assertIsInstance(store, PostgresGraphStore)
        self.assertEqual(store.tenant_id, "tenant-alpha")

    def test_postgres_factory_requires_dsn(self):
        with self.assertRaises(ValueError):
            TenantGraphStoreFactory(backend="postgres")

    def test_postgres_factory_rejects_system_principal(self):
        factory = TenantGraphStoreFactory(
            backend="postgres",
            postgres_dsn="postgresql://app:secret@localhost/iskra",
        )
        with self.assertRaises(PermissionError):
            factory.for_principal(SYSTEM_ADMIN)

if __name__ == "__main__":
    unittest.main()
