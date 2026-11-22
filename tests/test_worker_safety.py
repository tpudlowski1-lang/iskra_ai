import os
import unittest
from unittest.mock import patch

from iskra.workers.autonomous import IskraAutonomiczna


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
