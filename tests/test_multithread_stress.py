import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

os.environ["ENABLE_AUTONOMOUS_LOOP"] = "false"
os.environ["LLM_PROVIDER"] = "deepseek"
os.environ["LLM_FALLBACK_PROVIDERS"] = "openai,gemini"

import app as iskra


class IskraConcurrencyTests(unittest.TestCase):
    def test_parallel_graph_updates_are_not_lost(self):
        old_path, old_dir = iskra.PLIK_SIECI, iskra.DATA_DIR
        with tempfile.TemporaryDirectory() as tmp:
            iskra.DATA_DIR = tmp
            iskra.PLIK_SIECI = os.path.join(tmp, "wiedza.json")
            network = iskra.SiecNeuronowa()
            workers, updates_each = 10, 20
            barrier = threading.Barrier(workers)

            def writer(worker_id):
                barrier.wait()
                for index in range(updates_each):
                    node_id = f"worker_{worker_id}_{index}"
                    network.aktualizuj_siec({
                        "neurons": {node_id: {"label": node_id, "weight": 0.7}},
                        "synapses": [{"from": "n_logika", "to": node_id, "strength": 0.6}],
                    })

            try:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    list(pool.map(writer, range(workers)))
                expected = 12 + workers * updates_each
                self.assertEqual(len(network.dane["neurons"]), expected)
                with open(iskra.PLIK_SIECI, encoding="utf-8") as handle:
                    saved = json.load(handle)
                self.assertEqual(len(saved["neurons"]), expected)
                self.assertEqual(len(saved["synapses"]), 10 + workers * updates_each)
                for synapse in saved["synapses"]:
                    self.assertIn(synapse["from"], saved["neurons"])
                    self.assertIn(synapse["to"], saved["neurons"])
            finally:
                iskra.PLIK_SIECI, iskra.DATA_DIR = old_path, old_dir

    def test_parallel_dashboard_reads(self):
        client_app = iskra.app
        workers, reads_each = 16, 40
        barrier = threading.Barrier(workers)

        def reader(_):
            client = client_app.test_client()
            barrier.wait()
            for __ in range(reads_each):
                response = client.get("/api/network")
                if response.status_code != 200:
                    return response.status_code
                payload = response.get_json()
                if not isinstance(payload.get("neurons"), dict):
                    return "invalid-neurons"
                if not isinstance(payload.get("synapses"), list):
                    return "invalid-synapses"
            return "ok"

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(reader, range(workers)))
        self.assertEqual(results, ["ok"] * workers)

    def test_parallel_health_requests(self):
        workers, calls_each = 12, 30
        barrier = threading.Barrier(workers)

        def check(_):
            client = iskra.app.test_client()
            barrier.wait()
            return [client.get("/health").status_code for __ in range(calls_each)]

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(check, range(workers)))
        self.assertTrue(all(code == 200 for group in results for code in group))

    def test_provider_fallback_order_without_network(self):
        router = iskra.RouterProvider()
        calls = []
        router.primary = "deepseek"
        router.fallbacks = ["openai", "gemini"]
        router.providers = {
            "deepseek": lambda prompt: calls.append("deepseek") or None,
            "openai": lambda prompt: calls.append("openai") or None,
            "gemini": lambda prompt: calls.append("gemini") or '{"ok": true}',
        }
        result = router.generate("test")
        self.assertEqual(calls, ["deepseek", "openai", "gemini"])
        self.assertEqual(json.loads(result), {"ok": True})


if __name__ == "__main__":
    unittest.main(verbosity=2)
