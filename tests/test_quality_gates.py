import json
import os
import tempfile
import unittest

os.environ["ENABLE_AUTONOMOUS_LOOP"] = "false"
import app as iskra


class IskraPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_data_dir = iskra.DATA_DIR
        self.old_network_path = iskra.PLIK_SIECI
        iskra.DATA_DIR = self.tmp.name
        iskra.PLIK_SIECI = os.path.join(self.tmp.name, "wiedza.json")

    def tearDown(self):
        iskra.DATA_DIR = self.old_data_dir
        iskra.PLIK_SIECI = self.old_network_path
        self.tmp.cleanup()

    def test_fresh_store_initializes_twelve_pillars(self):
        network = iskra.SiecNeuronowa()
        self.assertEqual(len(network.dane["neurons"]), 12)
        self.assertTrue(os.path.isfile(iskra.PLIK_SIECI))

    def test_graph_survives_save_and_reload(self):
        network = iskra.SiecNeuronowa()
        network.aktualizuj_siec({
            "neurons": {"n_test": {"label": "Test", "weight": 0.8}},
            "synapses": [{"from": "n_logika", "to": "n_test", "strength": 0.9}],
        })
        restored = iskra.SiecNeuronowa()
        self.assertEqual(restored.dane["neurons"]["n_test"]["label"], "Test")
        self.assertEqual(next(s for s in restored.dane["synapses"] if s["to"] == "n_test")["strength"], 0.9)

    def test_corrupt_json_recovers_to_safe_fundament(self):
        with open(iskra.PLIK_SIECI, "w", encoding="utf-8") as handle:
            handle.write("{not-valid-json")
        network = iskra.SiecNeuronowa()
        self.assertEqual(len(network.dane["neurons"]), 12)
        self.assertIn("n_logika", network.dane["neurons"])

    def test_weights_are_clamped_to_unit_interval(self):
        network = iskra.SiecNeuronowa()
        network.aktualizuj_siec({
            "neurons": {"n_low": {"label": "Low", "weight": -50}},
            "synapses": [{"from": "n_logika", "to": "n_low", "strength": 50}],
        })
        self.assertEqual(network.dane["neurons"]["n_low"]["weight"], 0.0)
        self.assertEqual(network.dane["synapses"][-1]["strength"], 1.0)

    def test_synapses_with_unknown_endpoints_are_ignored(self):
        network = iskra.SiecNeuronowa()
        before = len(network.dane["synapses"])
        network.aktualizuj_siec({
            "neurons": {},
            "synapses": [{"from": "missing", "to": "n_logika", "strength": 0.5}],
        })
        self.assertEqual(len(network.dane["synapses"]), before)


class IskraProviderTests(unittest.TestCase):
    def test_router_stops_after_first_success(self):
        router = iskra.RouterProvider()
        calls = []
        router.primary = "deepseek"
        router.fallbacks = ["openai", "gemini"]
        router.providers = {
            "deepseek": lambda _: calls.append("deepseek") or None,
            "openai": lambda _: calls.append("openai") or '{"source":"openai"}',
            "gemini": lambda _: calls.append("gemini") or '{"source":"gemini"}',
        }
        self.assertEqual(json.loads(router.generate("test")), {"source": "openai"})
        self.assertEqual(calls, ["deepseek", "openai"])

    def test_unknown_provider_is_skipped(self):
        router = iskra.RouterProvider()
        calls = []
        router.primary = "not-a-provider"
        router.fallbacks = ["deepseek"]
        router.providers = {"deepseek": lambda _: calls.append("deepseek") or '{"ok":true}'}
        self.assertEqual(json.loads(router.generate("test")), {"ok": True})
        self.assertEqual(calls, ["deepseek"])

    def test_json_extractor_handles_markdown_fence(self):
        router = iskra.RouterProvider()
        raw = '~~~json\n{"ok": true, "count": 2}\n~~~'
        self.assertEqual(json.loads(router.clean_json(raw)), {"ok": True, "count": 2})


class IskraApiContractTests(unittest.TestCase):
    def test_health_endpoint_contract(self):
        response = iskra.app.test_client().get("/health")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ok")
        self.assertIsInstance(payload["neurons"], int)

    def test_network_endpoint_contract(self):
        response = iskra.app.test_client().get("/api/network")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsInstance(payload["neurons"], dict)
        self.assertIsInstance(payload["synapses"], list)

    def test_dashboard_is_served(self):
        response = iskra.app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"ISKRA AI", response.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
