# Iskra AI

Miejscem rozwoju produktu jest repozytorium [iskra_ai](https://github.com/tpudlowski1-lang/iskra_ai). Program uruchamia się przez `wsgi:app`. [Instrukcja instalacji i stagingu](INSTALL_PILOT.md) dotyczy także klienta Cloud.

| Źródło na koncie tpudlowski1-lang | Wynik scalenia |
|---|---|
| `iskra_ai` | Istniejący modularny rdzeń, graf z dwunastoma filarami, asystent, kontrola tenantów, PostgreSQL i instalator |
| [iskra_cloud](https://github.com/tpudlowski1-lang/iskra_cloud) | Polski kontrakt czatu oraz oryginalna klasyfikacja pytań działają przez wspólny serwer. Pełne źródła i wszystkie 12 commitów są dostępne w [archiwum Git](../history/iskra-cloud.bundle). |
| [Iskra](https://github.com/tpudlowski1-lang/Iskra) | 24 listopada 2026 zdalne repozytorium nie miało żadnych referencji, commitów ani plików do importu. |

## Klienci Iskra Cloud

Klient wysyła `POST /api/chat` z nagłówkiem `Authorization: Bearer …` i obiektem `{"pytanie":"…"}`. Otrzymuje pola `odpowiedz` i `kategoria`. Klasyfikator rozpoznaje dotychczasowe kategorie społecznościowe, logiczno-matematyczne, filozoficzne i ogólne. Uwierzytelnianie, wyszukiwanie źródeł i wybór dostawcy realizuje ten sam kod, którego używa `/api/tenant/chat`. Stary klient wymaga aktywnego poświadczenia tenantu.

Historyczna wersja używała wspólnej pamięci JSON, osobnego procesu Flask i opcjonalnego tokenu. Kod źródłowy pamięci, informacji zwrotnej, refleksji i wizualizacji jest zachowany w historii. Te globalne interfejsy nie są udostępniane przez serwer wielodostępny. Bazy użytkowników, klucze dostawców i logi nie były częścią repozytoriów.

## Odtworzenie historii Cloud

W katalogu rozpakowanego wydania:
```sh
git clone -b main history/iskra-cloud.bundle iskra-cloud-history
git -C iskra-cloud-history rev-parse HEAD
git -C iskra-cloud-history rev-list --count HEAD
```

Oczekiwany commit to `0f33d8947e2c902ad6f53bfd7948e7fa64ded4cb`, a liczba commitów wynosi 12. Archiwum zachowuje oryginalne identyfikatory, autorstwo, drzewo plików i wymagania wersji Cloud. Rozpakowanie historii jest opcjonalne.
