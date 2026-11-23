# Iskra AI — status integracji Unified Core

Data kontroli: 2026-11-23

## Punkt bazowy

Gałąź robocza `iskra-integration-hardening` została utworzona z `iskra-unified-integrated`. Nie scalano automatycznie rozbieżnych historii z `iskra-full-quality-gates`.

Porównanie `iskra-full-quality-gates...iskra-unified-integrated` wykazało rozbieżność historii: 3 commity wyłącznie po stronie `iskra-unified-integrated` i 5 wyłącznie po stronie `iskra-full-quality-gates`. Występują zmiany w `app.py`, konfiguracji Render, testach i workflow CI. Wymagają świadomego przeniesienia, nie ślepego merge.

## Zachowane elementy

- rdzeń grafu wiedzy i 12 filarów;
- router providerów LLM;
- trwałość SQLite z kopią zgodności JSON;
- wejście WSGI z fail-closed API token;
- testy persystencji, bezpieczeństwa i współbieżności;
- wyłączona domyślnie pętla autonomiczna.

## Zmiana wykonana w tym etapie

Poprawiono wyzwalacze GitHub Actions:
- testy jakości uruchamiają się przy push do `iskra-integration-hardening` i `iskra-unified-integrated`;
- testy stresowe uruchamiają się przy push do tych gałęzi;
- pull requesty kierowane do `iskra-integration-hardening` uruchamiają odpowiednie kontrole.

## Znane braki — blokery komercyjnego SaaS

- brak pełnego uwierzytelniania użytkowników i ról firmowych;
- brak izolacji tenantów egzekwowanej po stronie serwera;
- brak prywatnego magazynu dokumentów i bezpiecznego uploadu;
- brak kompletnego pipeline'u RAG z cytowaniem fragmentów i testami izolacji;
- brak rejestru użycia, limitów planów i rozliczeń;
- brak pełnego audytu RODO, retencji i eksportu/usuwania danych;
- brak potwierdzenia wdrożenia produkcyjnego na Render.

## Kryteria następnego etapu

1. Uruchomić CI na nowej gałęzi i naprawić wszystkie błędy.
2. Dodać testy routera LLM: brak klucza, timeout, błędny JSON, limity retry i kolejność fallback.
3. Zakończyć przegląd XSS i walidacji danych grafu.
4. Zaprojektować PostgreSQL jako bazę dla kont, organizacji, ról i tenantów.
5. Zbudować dokumenty/RAG z kontrolą dostępu na poziomie zapytania i testami prób dostępu między firmami.
6. Dopiero po testach stagingowych rozpocząć pilotaż.

## Zasada bezpieczeństwa

Do czasu ukończenia izolacji tenantów, kontroli dostępu i testów nie używać tej wersji do przechowywania poufnych dokumentów klientów ani nie oferować jej jako płatnej usługi.
