import json
import os
import unittest
from unittest.mock import patch

from iskra.llm.router import RouterProvider


class RouterPayloadValidationTests(unittest.TestCase):
    def test_extracts_first_complete_json_object_from_surrounding_text(self):
        router = RouterProvider()
        raw = 'Model says: {"neurons": {}, "synapses": []} trailing {"ignored": true}'
        self.assertEqual(json.loads(router.clean_json(raw)), {"neurons": {}, "synapses": []})

    def test_external_processing_is_denied_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            router = RouterProvider()
        calls = []
        router.providers = {"deepseek": lambda _: calls.append("deepseek") or '{"ok": true}'}
        self.assertIsNone(router.generate("sensitive prompt"))
        self.assertEqual(calls, [])

    def test_primary_and_fallback_are_blocked_when_not_allowlisted(self):
        env = {"LLM_ALLOW_EXTERNAL_PROCESSING": "true",
               "LLM_ALLOWED_EXTERNAL_PROVIDERS": "deepseek",
               "LLM_PROVIDER": "openai", "LLM_FALLBACK_PROVIDERS": "gemini"}
        with patch.dict(os.environ, env, clear=True):
            router = RouterProvider()
        calls = []
        router.providers = {name: (lambda _, n=name: calls.append(n) or '{"ok": true}')
                            for name in ("openai", "gemini", "deepseek")}
        self.assertIsNone(router.generate("sensitive prompt"))
        self.assertEqual(calls, [])

    def test_fallback_cannot_bypass_allowlist(self):
        env = {"LLM_ALLOW_EXTERNAL_PROCESSING": "true",
               "LLM_ALLOWED_EXTERNAL_PROVIDERS": "deepseek",
               "LLM_PROVIDER": "deepseek", "LLM_FALLBACK_PROVIDERS": "openai,gemini"}
        with patch.dict(os.environ, env, clear=True):
            router = RouterProvider()
        calls = []
        router.providers = {
            "deepseek": lambda _: calls.append("deepseek") or None,
            "openai": lambda _: calls.append("openai") or '{"ok": true}',
            "gemini": lambda _: calls.append("gemini") or '{"ok": true}',
        }
        self.assertIsNone(router.generate("sensitive prompt"))
        self.assertEqual(calls, ["deepseek"])

    def test_only_allowlisted_provider_can_succeed(self):
        env = {"LLM_ALLOW_EXTERNAL_PROCESSING": "true",
               "LLM_ALLOWED_EXTERNAL_PROVIDERS": "openai",
               "LLM_PROVIDER": "deepseek", "LLM_FALLBACK_PROVIDERS": "openai"}
        with patch.dict(os.environ, env, clear=True):
            router = RouterProvider()
        calls = []
        router.providers = {
            "deepseek": lambda _: calls.append("deepseek") or '{"blocked": true}',
            "openai": lambda _: calls.append("openai") or '{"ok": true}',
        }
        self.assertEqual(json.loads(router.generate("test")), {"ok": True})
        self.assertEqual(calls, ["openai"])

    def test_invalid_json_is_rejected(self):
        env = {"LLM_ALLOW_EXTERNAL_PROCESSING": "true",
               "LLM_ALLOWED_EXTERNAL_PROVIDERS": "deepseek",
               "LLM_PROVIDER": "deepseek", "LLM_FALLBACK_PROVIDERS": ""}
        with patch.dict(os.environ, env, clear=True):
            router = RouterProvider()
        router.providers = {"deepseek": lambda _: "not json"}
        self.assertIsNone(router.generate("test"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
