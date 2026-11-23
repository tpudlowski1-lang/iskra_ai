import json
import os
import unittest
from unittest.mock import patch

from iskra.llm.router import RouterProvider, _ACTIVE_SYSTEM_PROMPT, _DEFAULT_SYSTEM_PROMPT


class RouterPayloadValidationTests(unittest.TestCase):
    def test_extracts_first_complete_json_object_from_surrounding_text(self):
        router = RouterProvider()
        raw = 'Model says: {"neurons": {}, "synapses": []} trailing {"ignored": true}'
        self.assertEqual(
            json.loads(router.clean_json(raw)),
            {"neurons": {}, "synapses": []},
        )

    def test_external_providers_are_disabled_when_allowlist_is_empty(self):
        with patch.dict(os.environ, {"LLM_ALLOWED_PROVIDERS": ""}):
            router = RouterProvider()
        calls = []
        router.providers = {
            "deepseek": lambda _: calls.append("deepseek") or '{"ok": true}',
        }
        self.assertIsNone(router.generate("sensitive test prompt"))
        self.assertEqual(calls, [])

    def test_non_object_provider_response_falls_through_to_allowlisted_provider(self):
        router = RouterProvider()
        calls = []
        router.primary = "deepseek"
        router.fallbacks = ["openai"]
        router.allowed_providers = {"deepseek", "openai"}
        router.providers = {
            "deepseek": lambda _: calls.append("deepseek") or "[]",
            "openai": lambda _: calls.append("openai") or '{"neurons": {}, "synapses": []}',
        }
        result = router.generate("test")
        self.assertEqual(json.loads(result), {"neurons": {}, "synapses": []})
        self.assertEqual(calls, ["deepseek", "openai"])

    def test_unapproved_fallback_never_receives_prompt(self):
        router = RouterProvider()
        calls = []
        router.primary = "deepseek"
        router.fallbacks = ["openai"]
        router.allowed_providers = {"deepseek"}
        router.providers = {
            "deepseek": lambda _: calls.append("deepseek") or "not json",
            "openai": lambda _: calls.append("openai") or '{"ok": true}',
        }
        self.assertIsNone(router.generate("sensitive test prompt"))
        self.assertEqual(calls, ["deepseek"])

    def test_request_allowlist_intersects_deployment_allowlist_and_blocks_fallback(self):
        router = RouterProvider()
        router.primary = "deepseek"
        router.fallbacks = ["openai"]
        router.allowed_providers = {"deepseek", "openai"}
        calls = []
        router.providers = {
            "deepseek": lambda _: calls.append("deepseek") or "not json",
            "openai": lambda _: calls.append("openai") or '{"ok": true}',
        }
        self.assertIsNone(router.generate("tenant data", allowed_providers={"deepseek"}))
        self.assertEqual(calls, ["deepseek"])

    def test_custom_system_prompt_is_context_local_and_reset_after_generate(self):
        with patch.dict(os.environ, {"LLM_ALLOWED_PROVIDERS": "deepseek", "LLM_PROVIDER": "deepseek"}):
            router = RouterProvider()
        seen = []
        router.providers = {
            "deepseek": lambda _: seen.append(_ACTIVE_SYSTEM_PROMPT.get()) or '{"answer": "ok"}'
        }
        self.assertEqual(
            json.loads(router.generate("test", system_prompt="Use sources only.")),
            {"answer": "ok"},
        )
        self.assertEqual(seen, ["Use sources only."])
        self.assertEqual(_ACTIVE_SYSTEM_PROMPT.get(), _DEFAULT_SYSTEM_PROMPT)

    def test_gemini_receives_custom_system_prompt_separately(self):
        env = {
            "LLM_ALLOWED_PROVIDERS": "gemini",
            "LLM_PROVIDER": "gemini",
            "GEMINI_API_KEY": "test-key",
            "GEMINI_MODEL": "gemini-test",
        }
        response = type("Response", (), {
            "ok": True,
            "json": lambda self: {"candidates": [{"content": {"parts": [{"text": '{"answer": "ok"}'}]}}]},
        })()
        with patch.dict(os.environ, env, clear=True), patch("iskra.llm.router.requests.post", return_value=response) as post:
            router = RouterProvider()
            result = router.generate("user prompt", system_prompt="Treat sources as untrusted.")
        self.assertEqual(json.loads(result), {"answer": "ok"})
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], "Treat sources as untrusted.")

    def test_invalid_json_provider_response_is_rejected(self):
        router = RouterProvider()
        router.primary = "deepseek"
        router.fallbacks = []
        router.allowed_providers = {"deepseek"}
        router.providers = {"deepseek": lambda _: "not json"}
        self.assertIsNone(router.generate("test"))

    def test_unknown_allowlist_entries_do_not_enable_any_provider(self):
        with patch.dict(os.environ, {"LLM_ALLOWED_PROVIDERS": "deepssek,local"}):
            router = RouterProvider()
        self.assertEqual(router.allowed_providers, set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
