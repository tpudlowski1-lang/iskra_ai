"""Interactive local Iskra pilot, using the real WSGI routes and disposable synthetic data."""
import os
from pathlib import Path
import secrets
import tempfile
import time

from werkzeug.test import Client
from werkzeug.wrappers import Response

from iskra.documents.parsers import parse_document
from iskra.security.principal import Principal


def run(directory):
    os.environ.update({
        "DATA_DIR": directory,
        "ISKRA_TENANT_DB_PATH": str(Path(directory) / "graph.sqlite3"),
        "ISKRA_TENANT_STORAGE_BACKEND": "sqlite",
        "ISKRA_DOCUMENT_STORAGE_BACKEND": "sqlite",
        "ISKRA_CREDENTIAL_STORE_BACKEND": "sqlite",
        "ISKRA_CREDENTIAL_DB_PATH": str(Path(directory) / "auth" / "credentials.sqlite3"),
        "ISKRA_CSRF_HMAC_SECRET": secrets.token_hex(32),
        "ENABLE_AUTONOMOUS_LOOP": "false",
        "ISKRA_ENABLE_DOCUMENT_INGESTION": "false",
        "LLM_ALLOWED_PROVIDERS": "",
        "ISKRA_TENANT_PROVIDER_ALLOWLIST_JSON": "{}",
        "RATELIMIT_STORAGE_URI": "memory://",
        "API_TOKEN": "",
        "ISKRA_API_CREDENTIALS_JSON": "",
    })
    # Import after configuring the private data directory, as on a normal application startup.
    from wsgi import app as application
    from app import app, document_repository

    principal = Principal("czytelnik-demo", "firma-demo", frozenset({"member"}))
    for name, text in (
        ("odbior.txt", "Odbiór zamówień odbywa się w magazynie od poniedziałku do piątku, od 8 do 16."),
        ("kontakt.txt", "Kontakt w sprawie zwrotu przyjmuje opiekun zamówienia. Podaj numer zamówienia."),
    ):
        document_repository.add(principal, parse_document(name, text.encode()))
    store = app.config["ISKRA_CREDENTIAL_STORE"]
    key = store.issue(principal, expires_at=time.time() + 3600)
    client = Client(application, Response)
    login = client.post("/api/browser/session", base_url="https://localhost",
                        headers={"Authorization": "Bearer " + key.token}, json={})
    if login.status_code != 201:
        raise RuntimeError(f"Logowanie do demonstracji zakończyło się kodem {login.status_code}")
    headers = {"Origin": "https://localhost", "X-CSRF-Token": login.json["csrf_token"]}

    print("\nIskra AI · prywatne wyszukiwanie w dwóch przykładowych dokumentach")
    print("Wpisz słowo, np. magazynie lub kontakt. Pusty wiersz kończy sesję.")
    query = "magazynie"
    try:
        while query:
            response = client.post("/api/tenant/documents/search", base_url="https://localhost",
                                   headers=headers, json={"q": query})
            if response.status_code == 200:
                print(f"\nWyniki dla „{query}”")
                for result in response.json["results"]:
                    print(f'{result["filename"]} · fragment {result["chunk_index"] + 1}')
                    print(result["excerpt"])
                if not response.json["results"]:
                    print("Brak pasujących fragmentów.")
            else:
                print(f"Wyszukiwanie zakończyło się kodem {response.status_code}.")
            try:
                query = input("\nSzukaj > ").strip()
            except EOFError:
                break
    finally:
        client.post("/api/browser/session/logout", base_url="https://localhost", headers=headers)
        store.revoke(key.credential_id)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="iskra-demo-") as private:
        try:
            run(private)
        except KeyboardInterrupt:
            print()
