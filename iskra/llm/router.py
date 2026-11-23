"""LLM provider routing with configurable primary and fallback order."""
import contextvars
import json
import os
import time
import requests

REQUEST_TIMEOUT = (3, 12)  # bounded connect/read timeout in seconds
REQUEST_RETRIES = 2
MAX_GENERATION_SECONDS = 100  # leave headroom under the 120s Render/Gunicorn timeout
_ACTIVE_DEADLINE = contextvars.ContextVar("iskra_llm_deadline", default=None)
_DEFAULT_SYSTEM_PROMPT = "Return only a valid JSON object."
_ACTIVE_SYSTEM_PROMPT = contextvars.ContextVar("iskra_llm_system_prompt", default=_DEFAULT_SYSTEM_PROMPT)

class RouterProvider:
    """Jednolity router modeli z kolejnością primary + fallback z ENV."""

    def __init__(self):
        self.primary = os.environ.get("LLM_PROVIDER", "deepseek").strip().lower()
        fallback = os.environ.get("LLM_FALLBACK_PROVIDERS", "openai,gemini")
        self.fallbacks = [x.strip().lower() for x in fallback.split(",") if x.strip()]
        self.providers = {
            "openai": self._openai,
            "deepseek": self._deepseek,
            "gemini": self._gemini,
        }
        # External network providers are deny-by-default. A deployment must
        # explicitly approve each provider through LLM_ALLOWED_PROVIDERS.
        allowed = os.environ.get("LLM_ALLOWED_PROVIDERS", "")
        configured = {item.strip().lower() for item in allowed.split(",") if item.strip()}
        self.allowed_providers = configured.intersection(self.providers)

    def clean_json(self, text):
        """Extract the first complete JSON object; reject arrays and malformed text."""
        if not isinstance(text, str) or not text.strip():
            return None
        decoder = json.JSONDecoder()
        for index, character in enumerate(text):
            if character != "{":
                continue
            try:
                value, _ = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return json.dumps(value, ensure_ascii=False)
        return None

    @staticmethod
    def _request_timeout(deadline):
        """Return connect/read timeouts bounded by the shared generation deadline."""
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        connect_timeout = min(REQUEST_TIMEOUT[0], remaining / 3)
        read_timeout = min(REQUEST_TIMEOUT[1], remaining - connect_timeout)
        if connect_timeout <= 0 or read_timeout <= 0:
            return None
        return (connect_timeout, read_timeout)

    def _chat_completion(self, provider, prompt, deadline=None):
        deadline = deadline or _ACTIVE_DEADLINE.get() or (time.monotonic() + MAX_GENERATION_SECONDS)
        configs = {
            "openai": {
                "key": os.environ.get("OPENAI_API_KEY", ""),
                "url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions"),
                "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            },
            "deepseek": {
                "key": os.environ.get("DEEPSEEK_API_KEY", ""),
                "url": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1/chat/completions"),
                "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            },
        }
        cfg = configs[provider]
        if not cfg["key"]:
            print(f"LLM {provider}: brak wymaganego klucza API — pomijam.")
            return None
        headers = {
            "Authorization": f"Bearer {cfg['key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": _ACTIVE_SYSTEM_PROMPT.get()},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }
        for attempt in range(REQUEST_RETRIES):
            timeout = self._request_timeout(deadline)
            if timeout is None:
                print(f"LLM {provider}: przekroczono wspólny limit czasu — przechodzę do fallback.")
                return None
            try:
                response = requests.post(cfg["url"], headers=headers, json=payload, timeout=timeout)
                if response.ok:
                    return response.json()["choices"][0]["message"]["content"]
                print(f"LLM {provider}: HTTP {response.status_code}")
            except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
                print(f"LLM {provider}: błąd żądania ({type(exc).__name__}).")
            if attempt + 1 < REQUEST_RETRIES:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                time.sleep(min(1, remaining))
        return None

    def _openai(self, prompt):
        return self._chat_completion("openai", prompt)

    def _deepseek(self, prompt):
        return self._chat_completion("deepseek", prompt)

    def _gemini(self, prompt):
        deadline = _ACTIVE_DEADLINE.get() or (time.monotonic() + MAX_GENERATION_SECONDS)
        api_key = os.environ.get("GEMINI_API_KEY", "")
        model = os.environ.get("GEMINI_MODEL", "").strip()
        if not api_key or not model:
            print("LLM gemini: ustaw GEMINI_API_KEY oraz GEMINI_MODEL — pomijam.")
            return None
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "responseMimeType": "application/json",
            },
        }
        for attempt in range(REQUEST_RETRIES):
            timeout = self._request_timeout(deadline)
            if timeout is None:
                print("LLM gemini: przekroczono wspólny limit czasu — kończę fallback.")
                return None
            try:
                response = requests.post(
                    url,
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=timeout,
                )
                if response.ok:
                    data = response.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                print(f"LLM gemini: HTTP {response.status_code}")
            except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
                print(f"LLM gemini: błąd żądania ({type(exc).__name__}).")
            if attempt + 1 < REQUEST_RETRIES:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                time.sleep(min(1, remaining))
        return None

    def generate(self, prompt, system_prompt=None):
        deadline = time.monotonic() + MAX_GENERATION_SECONDS
        context_token = _ACTIVE_DEADLINE.set(deadline)
        system_token = _ACTIVE_SYSTEM_PROMPT.set(
            system_prompt if isinstance(system_prompt, str) and system_prompt.strip()
            else _DEFAULT_SYSTEM_PROMPT
        )
        try:
            if not self.allowed_providers:
                print("LLM: zewnętrzne providery wyłączone — ustaw LLM_ALLOWED_PROVIDERS, aby jawnie je dopuścić.")
                return None
            order = [self.primary] + [p for p in self.fallbacks if p != self.primary]
            for name in order:
                if self._request_timeout(deadline) is None:
                    print("LLM: wyczerpano wspólny limit czasu — przerywam łańcuch providerów.")
                    break
                provider = self.providers.get(name)
                if provider is None:
                    print(f"LLM: nieznany provider '{name}' — pomijam.")
                    continue
                if name not in self.allowed_providers:
                    print(f"LLM {name}: provider nie znajduje się na LLM_ALLOWED_PROVIDERS — pomijam.")
                    continue
                try:
                    # Keep the long-standing provider(prompt) extension contract.
                    result = provider(prompt)
                except Exception as exc:
                    print(f"LLM {name}: provider zgłosił {type(exc).__name__} — uruchamiam fallback.")
                    continue
                cleaned = self.clean_json(result)
                if cleaned is None:
                    if result:
                        print(f"LLM {name}: odpowiedź nie zawiera poprawnego obiektu JSON — pomijam.")
                    continue
                print(f"LLM: odpowiedź uzyskana przez {name}.")
                return cleaned
            print("LLM: wszystkie skonfigurowane providery zawiodły.")
            return None
        finally:
            _ACTIVE_SYSTEM_PROMPT.reset(system_token)
            _ACTIVE_DEADLINE.reset(context_token)
