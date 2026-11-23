"""Static contract checks for the Render deployment manifest.

These tests prevent deployment settings from contradicting documented runtime
constraints. They do not contact Render or prove a live deployment.
"""
from pathlib import Path
import unittest


class RenderDeploymentContractTests(unittest.TestCase):
    def test_render_uses_authenticated_wsgi_entrypoint(self):
        manifest = (Path(__file__).resolve().parents[1] / "render.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("gunicorn wsgi:app", manifest)
        self.assertNotIn("gunicorn app:app", manifest)

    def test_render_uses_single_worker_for_legacy_global_graph(self):
        manifest = (Path(__file__).resolve().parents[1] / "render.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("gunicorn wsgi:app --workers 1 --threads 4 --timeout 120", manifest)

    def test_render_health_and_autonomous_worker_defaults_are_safe(self):
        manifest = (Path(__file__).resolve().parents[1] / "render.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("healthCheckPath: /health", manifest)
        self.assertIn("key: ENABLE_AUTONOMOUS_LOOP\n        value: false", manifest)



    def test_render_keeps_external_providers_disabled_until_approved_and_declares_secrets(self):
        manifest = (Path(__file__).resolve().parents[1] / "render.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn('key: LLM_ALLOWED_PROVIDERS\n        value: ""', manifest)
        self.assertIn("key: LLM_FALLBACK_PROVIDERS\n        value: deepseek", manifest)
        self.assertIn("key: OPENAI_API_KEY\n        sync: false", manifest)
        self.assertIn("key: DEEPSEEK_API_KEY\n        sync: false", manifest)
        self.assertNotIn("GEMINI_API_KEY", manifest)
        self.assertIn("autoDeploy: false", manifest)

if __name__ == "__main__":
    unittest.main(verbosity=2)
