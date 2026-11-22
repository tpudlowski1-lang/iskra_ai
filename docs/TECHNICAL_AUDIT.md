# Iskra AI — audyt stanu repozytorium

Audyt statyczny plików dostępnych w repozytorium na gałęzi main. Nie jest to potwierdzenie działania aplikacji na Render.

## Repozytorium

- Repo: https://github.com/tpudlowski1-lang/iskra_ai
- Główny plik: app.py
- Zależności: requirements.txt
- Konfiguracja Render: render.yaml

## Co już istnieje

- Flask API i panel HTML.
- Graf wiedzy z 12 filarami, węzłami i połączeniami.
- Atomowy zapis pliku wiedza.json.
- Generator zmian grafu oparty o DeepSeek.
- Endpointy /, /api/network i /health.
- Konfiguracja Gunicorn i Render.

## Blokery przed produktem komercyjnym

1. **Router LLM — poprawka w gałęzi commercial-mvp.** Dodano obsługę OpenAI, DeepSeek i Gemini, kolejność primary/fallback z ENV oraz jawne pomijanie providerów bez kluczy. Konfiguracja nie została jeszcze zweryfikowana na żywym Renderze.
2. **Brak obsługi klienta.** Nie ma logowania, użytkowników, organizacji/tenantów ani ról.
3. **Brak dokumentów/RAG dla klienta.** Obecny graf pojęciowy nie jest bazą wiedzy firmy i nie obsługuje uploadu dokumentów.
4. **Brak izolacji danych.** Jedna globalna sieć i jeden plik wiedza.json; nie wolno używać tego modelu do danych wielu firm.
5. **Proces w tle — zabezpieczenie w gałęzi commercial-mvp.** Pętla autonomiczna jest teraz domyślnie wyłączona i wymaga ENABLE_AUTONOMOUS_LOOP=true. Przy wielu workerach nadal nie wolno jej włączać, bo każdy worker utworzy własny wątek.
6. **Trwałość danych.** DATA_DIR wskazuje katalog repozytorium. Na hostingu katalog aplikacji może być efemeryczny lub tylko do odczytu; potrzebny trwały storage/baza.
7. **XSS w dashboardzie.** Etykiety grafu są interpolowane do innerHTML. Dane pochodzące z modelu nie mogą być bezpiecznie traktowane jako HTML.
8. **Walidacja grafu.** Wagi i synapsy są częściowo ograniczane, ale struktura odpowiedzi modelu wymaga ścisłej walidacji przed zapisem.
9. **Zależności.** flask-limiter jest zainstalowany, ale w widocznym kodzie nie jest skonfigurowany ani użyty.
10. **Brak testów i dokumentacji API.** Nie znaleziono README ani zestawu testów w ścieżkach sprawdzonych podczas audytu.

## Wniosek

Nie należy dodawać płatności ani udostępniać obecnego dashboardu klientom. Gałąź commercial-mvp usuwa dwa wczesne problemy (konfiguracja providerów i automatyczne uruchamianie pętli), ale nadal trzeba rozdzielić eksperymentalny graf wiedzy od komercyjnego API i wdrożyć wielodostępność, trwałą bazę, bezpieczne dokumenty oraz testy.

Graf 12 filarów można zachować jako wewnętrzny moduł badawczy Iskry, ale nie może być podstawą wyszukiwania poufnej wiedzy klientów.
