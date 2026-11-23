"""Explicit deny-by-default external LLM provider policy per tenant."""
import json
import os

from iskra.security.principal import Principal


SUPPORTED_PROVIDERS = frozenset({"openai", "deepseek", "gemini"})
ENVIRONMENT_VARIABLE = "ISKRA_TENANT_PROVIDER_ALLOWLIST_JSON"


class TenantProviderPolicy:
    """Resolve an operator-configured provider allowlist for a trusted tenant."""

    def __init__(self, tenant_allowlists):
        if not isinstance(tenant_allowlists, dict):
            raise ValueError("Polityka providerów musi być obiektem JSON")
        if len(tenant_allowlists) > 10000:
            raise ValueError("Polityka zawiera zbyt wiele tenantów")
        normalized = {}
        for tenant_id, providers in tenant_allowlists.items():
            if (not isinstance(tenant_id, str) or not tenant_id.strip()
                    or tenant_id != tenant_id.strip() or len(tenant_id) > 255):
                raise ValueError("Nieprawidłowy identyfikator tenant w polityce providerów")
            if not isinstance(providers, list) or len(providers) > len(SUPPORTED_PROVIDERS):
                raise ValueError("Lista providerów dla tenant musi być tablicą")
            selected = set()
            for provider in providers:
                if not isinstance(provider, str) or provider.strip().lower() not in SUPPORTED_PROVIDERS:
                    raise ValueError("Polityka zawiera nieobsługiwany provider")
                selected.add(provider.strip().lower())
            normalized[tenant_id] = frozenset(selected)
        self._tenant_allowlists = normalized

    @classmethod
    def from_environment(cls):
        raw = os.environ.get(ENVIRONMENT_VARIABLE, "").strip()
        if not raw:
            return cls({})
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Nieprawidłowy JSON w {ENVIRONMENT_VARIABLE}") from exc
        return cls(payload)

    def allowed_for(self, principal, globally_allowed):
        """Intersect tenant approval with deployment-wide provider approval."""
        if not isinstance(principal, Principal):
            return frozenset()
        tenant_approved = self._tenant_allowlists.get(principal.tenant_id, frozenset())
        deployment_approved = {
            item.strip().lower()
            for item in globally_allowed
            if isinstance(item, str) and item.strip().lower() in SUPPORTED_PROVIDERS
        }
        return frozenset(tenant_approved.intersection(deployment_approved))
