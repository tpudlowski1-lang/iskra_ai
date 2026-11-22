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

    def test_worker_does_not_start_for_unrecognized_truthy_text(self):
        graph = type("GraphStub", (), {"lock": None, "dane": {"neurons": {}, "synapses": []}})()
        with patch.dict(os.environ, {"ENABLE_AUTONOMOUS_LOOP": "enabled"}, clear=False):
            worker = IskraAutonomiczna(graph)
        self.assertIsNone(worker.thread)


if __name__ == "__main__":
    unittest.main(verbosity=2)
