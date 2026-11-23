# Iskra AI — audyt stanu repozytorium

Audyt statyczny gałęzi commercial-mvp po PR #6 i zmianach przygotowanych w PR #7. Testy CI nie są potwierdzeniem działania aplikacji na żywym Render.

## Repozytorium

- Repo: https://github.com/tpudlowski1-lang/iskra_ai
- Główny plik: app.py
- Zależności: requirements.txt
- Konfiguracja Render: render.yaml

## Co już istnieje

- Flask API i panel HTML.
- Graf wiedzy z 12 filarami, węzłami i połączeniami, przechowywany oddzielnie od danych firm.
- SQLite jako źródło prawdy grafu oraz atomowy JSON mirror.
- Osobna baza `iskra_knowledge.sqlite3` dla tenantów, dokumentów, fragmentów i indeksu FTS5.
- Admin API do tworzenia firm, rotacji kluczy i usuwania danych.
- Tenant API do uploadu PDF/DOCX/TXT, listowania/usuwania dokumentów i wyszukiwania źródłowych fragmentów.
- Generator zmian grafu oparty o DeepSeek.
- Endpointy /, /api/network i /health.
- Konfiguracja Gunicorn i Render.

## Blokery przed produktem komercyjnym

1. **Router LLM — poprawka w gałęzi commercial-mvp.** Dodano obsługę OpenAI, DeepSeek i Gemini, kolejność primary/fallback z ENV oraz jawne pomijanie providerów bez kluczy. Konfiguracja nie została jeszcze zweryfikowana na żywym Renderze.
2. **Tożsamość użytkowników — nadal brak.** Są przestrzenie firmowe i klucze API tenantów, ale nie ma nazwanych kont użytkowników, sesji ani ról.
3. **RAG — etap podstawowy.** Upload PDF/DOCX/TXT i tenant-scoped FTS5 retrieval są dostępne w PR #7. Nie ma jeszcze embeddingów/wektorowego wyszukiwania ani generowania odpowiedzi z cytowaniami.
4. **Izolacja danych — pilot.** Klucze tenantów wyznaczają tenant_id po stronie serwera, a zapytania SQL filtrują dokumenty i fragmenty po tenant_id. Potrzebne są niezależne testy penetracyjne i audyt uprawnień przed produkcją.
5. **Proces w tle — zabezpieczenie w gałęzi commercial-mvp.** Pętla autonomiczna jest teraz domyślnie wyłączona i wymaga ENABLE_AUTONOMOUS_LOOP=true. Przy wielu workerach nadal nie wolno jej włączać, bo każdy worker utworzy własny wątek.
6. **Trwałość danych.** DATA_DIR wskazuje katalog repozytorium. Na hostingu katalog aplikacji może być efemeryczny lub tylko do odczytu; potrzebny trwały storage/baza.
7. **XSS w dashboardzie.** Etykiety grafu są interpolowane do innerHTML. Dane pochodzące z modelu nie mogą być bezpiecznie traktowane jako HTML.
8. **Walidacja grafu.** Wagi i synapsy są częściowo ograniczane, ale struktura odpowiedzi modelu wymaga ścisłej walidacji przed zapisem.
9. **Zależności.** flask-limiter jest zainstalowany, ale w widocznym kodzie nie jest skonfigurowany ani użyty.
10. **Operacje i compliance — nieukończone.** Brak formalnej retencji, eksportu danych, polityki kopii zapasowych dla obu baz, monitoringu, limitów kosztowych i procedur incydentowych. CI obejmuje obecnie testy grafu, middleware, tenant isolation, dokumentów i stresu współbieżności.

## Wniosek

Nie należy jeszcze dodawać płatności ani sprzedawać usługi. Gałąź commercial-mvp ma już osobny pilotowy moduł dokumentów z izolacją tenantów i testami, ale przed produkcją trzeba dodać nazwane konta/role, semantyczny retrieval, odpowiedzi RAG z kontrolą prompt injection, prywatny storage, retencję i audyt bezpieczeństwa.

Graf 12 filarów można zachować jako wewnętrzny moduł badawczy Iskry, ale nie może być podstawą wyszukiwania poufnej wiedzy klientów.
