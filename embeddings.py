"""Optional OpenAI embedding adapter. Disabled by default to avoid surprise API costs."""
import os
import requests


class EmbeddingProvider:
    def __init__(self):
        enabled = os.environ.get("ENABLE_SEMANTIC_SEARCH", "false").strip().lower() in ("1", "true", "yes", "on")
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.model = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self.url = os.environ.get("OPENAI_EMBEDDINGS_BASE_URL", "https://api.openai.com/v1/embeddings")
        self.enabled = bool(enabled and self.api_key)

    def embed_many(self, texts):
        if not self.enabled or not texts:
            return None
        vectors = []
        for start in range(0, len(texts), 64):
            batch = texts[start:start + 64]
            try:
                response = requests.post(
                    self.url,
                    headers={"Authorization": f"Bearer {self.api_key}",
                             "Content-Type": "application/json"},
                    json={"model": self.model, "input": batch},
                    timeout=60,
                )
                if not response.ok:
                    return None
                data = response.json().get("data", [])
                ordered = sorted(data, key=lambda item: item.get("index", 0))
                if len(ordered) != len(batch):
                    return None
                vectors.extend(item.get("embedding") for item in ordered)
            except (requests.RequestException, ValueError, TypeError, KeyError):
                return None
        return vectors if len(vectors) == len(texts) else None

    def embed_one(self, text):
        vectors = self.embed_many([text])
        return vectors[0] if vectors else None
