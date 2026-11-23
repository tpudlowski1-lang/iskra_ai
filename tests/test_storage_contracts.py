import unittest

from iskra.storage.protocols import KnowledgeGraphService, KnowledgeGraphStore


class InMemoryGraphStore:
    def __init__(self):
        self.graph = {"neurons": {}, "synapses": []}

    def load(self):
        return self.graph

    def save(self, graph):
        self.graph = graph


class GraphService:
    def snapshot(self):
        return {"neurons": {}, "synapses": []}

    def update(self, graph_delta):
        return None


class StorageContractTests(unittest.TestCase):
    def test_store_protocol_is_runtime_checkable(self):
        self.assertIsInstance(InMemoryGraphStore(), KnowledgeGraphStore)

    def test_service_protocol_is_runtime_checkable(self):
        self.assertIsInstance(GraphService(), KnowledgeGraphService)


if __name__ == "__main__":
    unittest.main(verbosity=2)
