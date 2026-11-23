"""Structural checks for Iskra's adversarial regression corpus.

These tests validate corpus integrity only. They do not execute the LLM or
prove semantic resistance to prompt injection.
"""
import json
import unittest
from pathlib import Path

CORPUS_PATH = Path(__file__).resolve().parents[1] / "quality" / "redteam_scenarios.json"
REQUIRED_CATEGORIES = {
    "direct_prompt_injection", "role_override", "indirect_prompt_injection",
    "secret_exfiltration", "authorization_claim", "tenant_boundary",
    "excessive_agency", "retrieval_exfiltration", "malformed_input",
    "provider_failure",
}


class RedTeamCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))

    def test_version_and_purpose_are_explicit(self):
        self.assertEqual(self.corpus["version"], 1)
        self.assertIn("does not claim", self.corpus["purpose"])

    def test_scenario_ids_are_unique_and_nonempty(self):
        scenarios = self.corpus["scenarios"]
        ids = [item["id"] for item in scenarios]
        self.assertTrue(all(isinstance(value, str) and value for value in ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_required_threat_categories_are_covered(self):
        categories = {item["category"] for item in self.corpus["scenarios"]}
        self.assertTrue(REQUIRED_CATEGORIES.issubset(categories))

    def test_each_scenario_has_input_and_control_objective(self):
        for item in self.corpus["scenarios"]:
            with self.subTest(scenario=item.get("id")):
                self.assertTrue(item["input"].strip())
                self.assertTrue(item["expected_control"].strip())
                self.assertIn(item["severity"], {"medium", "high", "critical"})


if __name__ == "__main__":
    unittest.main()
