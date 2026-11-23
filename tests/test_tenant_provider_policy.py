import json
import os
import unittest
from unittest.mock import patch

from iskra.llm.tenant_policy import TenantProviderPolicy, ENVIRONMENT_VARIABLE
from iskra.security.principal import Principal


class TenantProviderPolicyTests(unittest.TestCase):
    def setUp(self):
        self.alpha = Principal("member-a", "tenant-alpha", frozenset({"member"}))
        self.beta = Principal("member-b", "tenant-beta", frozenset({"member"}))

    def test_tenant_policy_must_intersect_deployment_allowlist(self):
        policy = TenantProviderPolicy({
            "tenant-alpha": ["deepseek", "openai"],
        })
        self.assertEqual(
            policy.allowed_for(self.alpha, {"deepseek", "gemini"}),
            frozenset({"deepseek"}),
        )

    def test_unlisted_tenant_is_denied_by_default(self):
        policy = TenantProviderPolicy({
            "tenant-alpha": ["deepseek"],
        })
        self.assertEqual(policy.allowed_for(self.beta, {"deepseek"}), frozenset())

    def test_global_allowlist_cannot_be_overridden_by_tenant_policy(self):
        policy = TenantProviderPolicy({
            "tenant-alpha": ["deepseek", "openai", "gemini"],
        })
        self.assertEqual(
            policy.allowed_for(self.alpha, {"deepseek"}),
            frozenset({"deepseek"}),
        )

    def test_non_principal_identity_is_denied(self):
        policy = TenantProviderPolicy({"tenant-alpha": ["deepseek"]})
        self.assertEqual(policy.allowed_for({"tenant_id": "tenant-alpha"}, {"deepseek"}), frozenset())

    def test_environment_absence_denies_all_tenants(self):
        with patch.dict(os.environ, {}, clear=True):
            policy = TenantProviderPolicy.from_environment()
        self.assertEqual(policy.allowed_for(self.alpha, {"deepseek"}), frozenset())

    def test_environment_loads_explicit_tenant_allowlists(self):
        payload = json.dumps({"tenant-alpha": ["deepseek"]})
        with patch.dict(os.environ, {ENVIRONMENT_VARIABLE: payload}, clear=True):
            policy = TenantProviderPolicy.from_environment()
        self.assertEqual(policy.allowed_for(self.alpha, {"deepseek", "openai"}), frozenset({"deepseek"}))

    def test_invalid_environment_json_fails_closed_at_startup(self):
        with patch.dict(os.environ, {ENVIRONMENT_VARIABLE: "{bad"}, clear=True):
            with self.assertRaises(ValueError):
                TenantProviderPolicy.from_environment()

    def test_unknown_provider_rejected_in_configuration(self):
        with self.assertRaises(ValueError):
            TenantProviderPolicy({"tenant-alpha": ["unknown-provider"]})

    def test_invalid_policy_shape_rejected(self):
        with self.assertRaises(ValueError):
            TenantProviderPolicy(["tenant-alpha", ["deepseek"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
