import json
import unittest

from iskra.llm.router import RouterProvider


class RouterPayloadValidationTests(unittest.TestCase):
    def test_extracts_first_complete_json_object_from_surrounding_text(self):
        router = RouterProvider()
        raw = 'Model says: {"neurons": {}, "synapses": []} trailing {"ignored": true}'
        self.assertEqual(
            json.loads(router.clean_json(raw)),
            {"neurons": {}, "synapses": []},
        )

    def test_non_object_provider_response_falls_through_to_next_provider(self):
        router = RouterProvider()
        calls = []
        router.primary = "deepseek"
        router.fallbacks = ["openai"]
        router.providers = {
            "deepseek": lambda _: calls.append("deepseek") or "[]",
            "openai": lambda _: calls.append("openai") or '{"neurons": {}, "synapses": []}',
        }
        result = router.generate("test")
        self.assertEqual(json.loads(result), {"neurons": {}, "synapses": []})
        self.assertEqual(calls, ["deepseek", "openai"])

    def test_invalid_json_provider_response_is_rejected(self):
        router = RouterProvider()
        router.primary = "deepseek"
        router.fallbacks = []
        router.providers = {"deepseek": lambda _: "not json"}
        self.assertIsNone(router.generate("test"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
