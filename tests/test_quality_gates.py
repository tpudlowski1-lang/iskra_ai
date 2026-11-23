import json
import os
import tempfile
import unittest

os.environ["ENABLE_AUTONOMOUS_LOOP"] = "false"
import app as iskra
from flask import request
from iskra.security.principal import PRINCIPAL_ENV_KEY, SYSTEM_ADMIN


def _attach_test_admin_principal(flask_app):
    @flask_app.before_request
    def attach_test_admin():
        request.environ[PRINCIPAL_ENV_KEY] = SYSTEM_ADMIN


_attach_test_admin_principal(iskra.app)


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

    def test_partial_legacy_graph_restores_all_twelve_pillars(self):
        with open(iskra.PLIK_SIECI, "w", encoding="utf-8") as handle:
            json.dump({
                "neurons": {"n_logika": {"label": "Logika", "weight": 1.0}},
                "synapses": [],
            }, handle)
        network = iskra.SiecNeuronowa()
        self.assertEqual(len(network.dane["neurons"]), 12)
        self.assertGreaterEqual(len(network.dane["synapses"]), 10)

    def test_stale_compatibility_save_does_not_overwrite_newer_process_data(self):
        network = iskra.SiecNeuronowa()
        stale = iskra.SiecNeuronowa()
        network.aktualizuj_siec({
            "neurons": {"n_newer": {"label": "Nowszy zapis", "weight": 0.9}},
            "synapses": [{"from": "n_logika", "to": "n_newer", "strength": 0.8}],
        })
        stale.dane["neurons"]["n_local"] = {
            "label": "Lokalny dodatek", "weight": 0.7, "created": 1
        }
        stale.zapisz()
        restored = iskra.SiecNeuronowa()
        self.assertIn("n_newer", restored.dane["neurons"])
        self.assertIn("n_local", restored.dane["neurons"])
        self.assertTrue(any(edge["to"] == "n_newer" for edge in restored.dane["synapses"]))

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

    def test_partial_neuron_update_preserves_existing_weight(self):
        network = iskra.SiecNeuronowa()
        network.aktualizuj_siec({
            "neurons": {"n_logika": {"label": "Logika", "weight": 0.95}},
            "synapses": [],
        })
        expected = network.dane["neurons"]["n_logika"]["weight"]
        network.aktualizuj_siec({
            "neurons": {"n_logika": {"label": "Logika — aktualizacja częściowa"}},
            "synapses": [],
        })
        self.assertEqual(network.dane["neurons"]["n_logika"]["weight"], expected)

    def test_weights_are_clamped_to_unit_interval(self):
        network = iskra.SiecNeuronowa()
        network.aktualizuj_siec({
            "neurons": {"n_low": {"label": "Low", "weight": -50}},
            "synapses": [{"from": "n_logika", "to": "n_low", "strength": 50}],
        })
        self.assertEqual(network.dane["neurons"]["n_low"]["weight"], 0.0)
        self.assertEqual(network.dane["synapses"][-1]["strength"], 1.0)

    def test_malformed_synapse_endpoints_are_ignored_without_corrupting_graph(self):
        network = iskra.SiecNeuronowa()
        network.aktualizuj_siec({
            "neurons": {},
            "synapses": [
                {"from": ["not", "hashable"], "to": "n_logika", "strength": 0.5},
                {"from": "n_logika", "to": {"bad": "target"}, "strength": 0.5},
            ],
        })
        restored = iskra.SiecNeuronowa()
        self.assertEqual(len(restored.dane["neurons"]), 12)
        self.assertEqual(len(restored.dane["synapses"]), 10)

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
        router.allowed_providers = {"deepseek", "openai", "gemini"}
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
        router.allowed_providers = {"deepseek"}
        router.providers = {"deepseek": lambda _: calls.append("deepseek") or '{"ok":true}'}
        self.assertEqual(json.loads(router.generate("test")), {"ok": True})
        self.assertEqual(calls, ["deepseek"])

    def test_json_extractor_handles_markdown_fence(self):
        router = iskra.RouterProvider()
        raw = '~~~json\n{"ok": true, "count": 2}\n~~~'
        self.assertEqual(json.loads(router.clean_json(raw)), {"ok": True, "count": 2})


class IskraApiContractTests(unittest.TestCase):

    def test_api_reads_latest_graph_written_by_another_worker(self):
        from flask import Flask
        from iskra.api.routes import create_api_blueprint

        reader = iskra.SiecNeuronowa()
        writer = iskra.SiecNeuronowa()
        writer.aktualizuj_siec({
            "neurons": {"n_external_worker": {
                "label": "Dane z innego workera", "weight": 0.8
            }},
            "synapses": [{
                "from": "n_logika", "to": "n_external_worker",
                "strength": 0.75
            }],
        })
        self.assertNotIn("n_external_worker", reader.dane["neurons"])
        test_app = Flask("graph-refresh-test")
        test_app.register_blueprint(create_api_blueprint(reader))
        _attach_test_admin_principal(test_app)
        response = test_app.test_client().get("/api/network")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "n_external_worker",
            response.get_json()["neurons"],
            "API musi odświeżać snapshot po zapisie z innego procesu",
        )

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
