# Iskra Unified Core — projekt integracji i napraw

**Data:** 2026-11-23  
**Status:** projekt do zatwierdzenia przed zmianami produkcyjnymi

## Cel

Połączyć istniejące prace jakościowe i wielowątkowe w jeden kontrolowany tor rozwoju Iskra AI oraz naprawić rzeczywiste błędy rdzenia bez utraty 12 filarów, grafu wiedzy, polskiej tożsamości Iskry i zasad Dekalogu. Rezultatem tego etapu ma być stabilniejszy rdzeń Flask, wiarygodne testy i bezpieczna ścieżka dalszej rozbudowy — nie deklaracja, że system ma już pełne RAG, agentów lub pamięć wielodostępną.

## Stan obecny — ustalenia z repozytorium

- `commercial-mvp/app.py` zawiera 12 filarów, graf neuronów/synaps, zapis JSON przez plik tymczasowy + `os.replace`, blokadę procesu `RLock` i blokadę międzyprocesową POSIX `fcntl.flock`.
- Blokada plikowa chroni cykl odczyt-modyfikacja-zapis na systemach POSIX, ale każdy worker Gunicorn nadal trzyma własną kopię `siec.dane`. Endpointy odczytu `/api/network` i `/health` nie odświeżają kopii po zmianach wykonanych przez inny worker. To jest konkretna niespójność odczytu między procesami.
- Jeśli `fcntl` nie jest dostępny, kod przechodzi na blokadę pustą; wieloprocesowa ochrona nie jest wtedy zapewniona.
- `IskraAutonomiczna` uruchamia wątek przy imporcie modułu, gdy `ENABLE_AUTONOMOUS_LOOP=true`. Wiele workerów może więc uruchomić wiele niezależnych pętli.
- Router providerów obsługuje OpenAI-compatible, DeepSeek i Gemini; ma powtórzenia żądań i fallback, ale opiera się na wspólnym długim timeout, loguje statusy bez ustrukturyzowanego wyniku diagnostycznego i nie waliduje kompletnego kontraktu odpowiedzi JSON przed uznaniem dostawcy za sukces.
- Gałąź `iskra-full-quality-gates` łączy testy wielowątkowe, testy jakości i dokumentację. Gałąź `iskra-unified-core` zawiera dodatkowo test wieloprocesowych zapisów. PR #1 i #2 pozostają otwarte/draft; nie są scalone do `commercial-mvp`.

## Cele etapu

1. Ustalić jedną gałąź integracyjną i jeden zestaw CI obejmujący testy kontraktowe, trwałości, wielowątkowe i wieloprocesowe.
2. Naprawić widoczność danych między workerami: odczyty muszą widzieć najnowszy zapis współdzielonego pliku, bez utraty obecnego formatu JSON.
3. Zabezpieczyć tryb blokad: nie udawać ochrony międzyprocesowej, gdy mechanizm blokady nie jest dostępny.
4. Oddzielić proces web od pętli autonomicznej, tak aby import aplikacji przez Gunicorn nie uruchamiał niekontrolowanych kopii pętli.
5. Utwardzić router: walidacja odpowiedzi, ograniczone timeouty/powtórzenia, bezpieczne logi, jednoznaczna informacja o dostawcy i testy mockujące HTTP.
6. Zachować kompatybilność Render i obecnych zmiennych środowiskowych, a dokumentację aktualizować zgodnie z rzeczywistym kodem.

## Poza zakresem

- Nie scalać automatycznie PR do `commercial-mvp` ani `main`.
- Nie wprowadzać bez potrzeby migracji JSON do SQLite/PostgreSQL w tym etapie.
- Nie dodawać pozornych endpointów czatu, tenantów, RAG, agentów, pluginów ani systemu uprawnień bez osobnych specyfikacji i testów.
- Nie uruchamiać testów obciążeniowych na publicznej produkcji.
- Nie umieszczać kluczy API, tokenów ani danych prywatnych w repozytorium lub logach.

## Rozważone podejścia

### A. Szybkie scalenie gałęzi testowych
Zaleta: najmniejszy zakres i szybkie uzyskanie CI. Wada: pozostawia niespójność kopii danych między workerami, ryzyko wielu pętli autonomicznych i słabą diagnostykę routera. Nie realizuje celu naprawy rdzenia.

### B. Integracja + naprawy etapowe na jednej gałęzi — rekomendowane
Połączyć testy i dokumentację w jedną gałąź, dodać testy regresyjne wykrywające rzeczywiste błędy, następnie naprawiać je małymi zmianami. Zachować JSON i interfejsy API, a większe elementy (SQLite/PostgreSQL, RAG, agenci) pozostawić na osobne etapy. Najlepszy stosunek bezpieczeństwa, ryzyka i zgodności z obecnym wdrożeniem.

### C. Pełna przebudowa na platformę wielousługową
Od razu przejść na bazę danych, osobny scheduler, warstwę RAG, agentów i telemetrykę. Daje większy potencjał docelowy, ale jest zbyt szeroka względem aktualnego, małego rdzenia i zwiększa ryzyko migracji danych oraz koszt utrzymania.

**Wybrany kierunek:** B — zgodnie z potwierdzeniem użytkownika, z zachowaniem dotychczasowego rdzenia.

## Proponowana architektura po tym etapie

- **Rdzeń domenowy:** 12 filarów i graf pozostają źródłem prawdy dla istniejącej funkcji mapowania wiedzy.
- **Magazyn obecnego etapu:** JSON z atomowym zapisem i blokadą POSIX; wszystkie odczyty i zapisy współdzielonego stanu przechodzą przez wspólną, testowalną granicę synchronizacji. Na platformie bez blokady międzyprocesowej aplikacja zgłasza ograniczenie zamiast udawać bezpieczeństwo.
- **Web:** Flask/Gunicorn obsługuje wyłącznie żądania HTTP; nie uruchamia pętli autonomicznej.
- **Autonomia:** uruchamiana tylko w osobnym, jawnie wskazanym procesie/komendzie. Pojedynczy właściciel pętli i mechanizm dzierżawy będą osobnym testowanym elementem; bez gwarancji pojedynczego właściciela pętla pozostaje wyłączona.
- **Router:** stabilne API `generate`, per-provider konfiguracja timeoutów i retry, kontrola odpowiedzi, strukturalne statusy diagnostyczne bez sekretów i bez ujawniania promptów.
- **CI:** Python 3.11 i 3.12, kompilacja, pełne testy deterministyczne, testy wieloprocesowe na Linux, kontrola bezpieczeństwa zależności jako osobny gate.

## Kryteria akceptacji

- Wszystkie istniejące testy i nowe testy regresyjne przechodzą na Pythonie 3.11 i 3.12.
- Test międzyprocesowy potwierdza zarówno brak utraconych zapisów, jak i widoczność nowego stanu z procesu, który go nie zapisał.
- Tryb bez `fcntl` nie deklaruje wieloprocesowego bezpieczeństwa.
- Test potwierdza, że zwykły import aplikacji web nie uruchamia pętli autonomicznej.
- Testy routera obejmują brak klucza, timeout, HTTP 429/5xx, błędny JSON, pustą odpowiedź i kolejność fallback.
- Logi i odpowiedzi diagnostyczne nie zawierają kluczy API.
- `Procfile` pozostaje bezpieczny dla Render i używa jednego workera, dopóki współdzielony magazyn i wdrożenie nie zostaną osobno zweryfikowane.
- PR pozostaje do przeglądu; brak automatycznego wdrożenia produkcyjnego.

## Ryzyka i decyzje wykonawcze

- JSON + blokada plikowa jest akceptowalnym rozwiązaniem dla pojedynczej instancji na trwałym dysku POSIX; nie jest docelową bazą dla wielu instancji/tenantów.
- Jeśli Render nie zapewnia trwałego dysku dla ścieżki `DATA_DIR`, restart/ponowne wdrożenie może utracić dane. Wdrożenie musi jawnie ustawić trwały katalog albo zaakceptować efemeryczność.
- Testy wieloprocesowe używają mechanizmu `fork` i będą wykonywane na runnerze Linux.
- Zmiany będą dodawane do jednej gałęzi integracyjnej; merge do gałęzi wdrożeniowej pozostaje osobną decyzją po zielonym CI i review.
