"""LLM provider routing with configurable primary and fallback order."""
import os
import re
import time
import requests

REQUEST_TIMEOUT = 45
REQUEST_RETRIES = 2

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

    def clean_json(self, text):
        if not text:
            return None
        match = re.search(r'\{.*\}', text, re.DOTALL)
        return match.group(0) if match else text

    def _chat_completion(self, provider, prompt):
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
                {"role": "system", "content": "Return only a valid JSON object."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }
        for attempt in range(REQUEST_RETRIES):
            try:
                response = requests.post(cfg["url"], headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
                if response.ok:
                    return response.json()["choices"][0]["message"]["content"]
                print(f"LLM {provider}: HTTP {response.status_code}")
            except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
                print(f"LLM {provider}: błąd żądania ({type(exc).__name__}).")
            if attempt + 1 < REQUEST_RETRIES:
                time.sleep(2)
        return None

    def _openai(self, prompt):
        return self._chat_completion("openai", prompt)

    def _deepseek(self, prompt):
        return self._chat_completion("deepseek", prompt)

    def _gemini(self, prompt):
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
            try:
                response = requests.post(
                    url,
                    headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                    json=payload,
                    timeout=REQUEST_TIMEOUT,
                )
                if response.ok:
                    data = response.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                print(f"LLM gemini: HTTP {response.status_code}")
            except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
                print(f"LLM gemini: błąd żądania ({type(exc).__name__}).")
            if attempt + 1 < REQUEST_RETRIES:
                time.sleep(2)
        return None

    def generate(self, prompt):
        order = [self.primary] + [p for p in self.fallbacks if p != self.primary]
        for name in order:
            provider = self.providers.get(name)
            if provider is None:
                print(f"LLM: nieznany provider '{name}' — pomijam.")
                continue
            result = provider(prompt)
            if result:
                print(f"LLM: odpowiedź uzyskana przez {name}.")
                return self.clean_json(result)
        print("LLM: wszystkie skonfigurowane providery zawiodły.")
        return None
