import os
import json
import unittest
from unittest.mock import patch

from iskra.workers.autonomous import IskraAutonomiczna, PUBLIC_RESEARCH_CONTEXT


class AutonomousWorkerSafetyTests(unittest.TestCase):
    def test_worker_is_disabled_without_explicit_opt_in(self):
        graph = type("GraphStub", (), {"lock": None, "dane": {"neurons": {}, "synapses": []}})()
        with patch.dict(os.environ, {"ENABLE_AUTONOMOUS_LOOP": "false"}, clear=False):
            worker = IskraAutonomiczna(graph)
        self.assertIsNone(worker.thread)

    def test_web_role_never_starts_autonomous_thread_even_when_opted_in(self):
        graph = type("GraphStub", (), {"lock": None, "dane": {"neurons": {}, "synapses": []}})()
        with patch.dict(os.environ, {
            "ENABLE_AUTONOMOUS_LOOP": "true",
            "ISKRA_PROCESS_ROLE": "web",
        }, clear=False), patch("iskra.workers.autonomous.threading.Thread") as thread:
            worker = IskraAutonomiczna(graph)
        self.assertIsNone(worker.thread)
        thread.assert_not_called()

    def test_worker_does_not_start_for_unrecognized_truthy_text(self):
        graph = type("GraphStub", (), {"lock": None, "dane": {"neurons": {}, "synapses": []}})()
        with patch.dict(os.environ, {"ENABLE_AUTONOMOUS_LOOP": "enabled"}, clear=False):
            worker = IskraAutonomiczna(graph)
        self.assertIsNone(worker.thread)

    def test_worker_prompt_excludes_mutable_global_graph_content(self):
        private_marker = "PRIVATE CUSTOMER RECORD SHOULD NEVER LEAVE"
        graph = type("GraphStub", (), {
            "lock": None,
            "dane": {"neurons": {"n_secret": {"label": private_marker}}, "synapses": []},
        })()
        with patch.dict(os.environ, {"ENABLE_AUTONOMOUS_LOOP": "false"}, clear=False):
            worker = IskraAutonomiczna(graph)
        prompt = worker._build_research_prompt()
        self.assertNotIn(private_marker, prompt)
        self.assertIn("n_logika", prompt)
        self.assertIn("n_metapoznanie", prompt)
        self.assertLess(len(prompt), 10000)

    def test_research_context_contains_only_fixed_public_taxonomy(self):
        expected_ids = {
            "n_logika", "n_epistemologia", "n_etyka", "n_ontologia",
            "n_przyrodnicze", "n_spoleczne", "n_jezyk", "n_historia",
            "n_technologia", "n_sztuka", "n_zdrowie", "n_metapoznanie",
        }
        self.assertEqual(set(PUBLIC_RESEARCH_CONTEXT["neurons"]), expected_ids)
        self.assertEqual(len(PUBLIC_RESEARCH_CONTEXT["synapses"]), 10)
        self.assertNotIn("created", json.dumps(PUBLIC_RESEARCH_CONTEXT))


if __name__ == "__main__":
    unittest.main(verbosity=2)
