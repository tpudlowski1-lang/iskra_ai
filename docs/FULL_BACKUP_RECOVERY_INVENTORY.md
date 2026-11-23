# Iskra AI — pełny inwentarz danych i kontrakt odzyskiwania

Status: audyt kodu gałęzi `refactor/modular-core`; dokument nie oznacza, że backup produkcyjny został wykonany ani że hosting ma trwały dysk.

## Cel i granice

Pojedyncza kopia `iskra_tenants.sqlite3` nie jest pełnym backupem Iskry. Aplikacja utrzymuje kilka niezależnych zasobów, a część z nich jest aktywowana warunkowo. Backup musi najpierw rozpoznać rzeczywistą konfigurację wdrożenia, a następnie albo objąć wszystkie wymagane zasoby, albo przerwać pracę z raportem brakujących danych. Nie wolno po cichu pomijać magazynu.

## Inwentarz zasobów

| Zasób | Lokalizacja / konfiguracja | Status i wymagania |
|---|---|---|
| Główny graf wiedzy | `DATA_DIR/wiedza.json`; blokada `wiedza.json.lock` | Aktywny legacy store. Zapis używa pliku tymczasowego, `fsync` i `os.replace`; operacje synchronizowane blokadą plikową. Kopię należy pobrać przy zatrzymanych zapisach lub z użyciem tego samego mechanizmu blokady. |
| Grafy tenantów SQLite | `ISKRA_TENANT_DB_PATH` albo `DATA_DIR/iskra_tenants.sqlite3` | Aktywny tylko przy `ISKRA_TENANT_STORAGE_BACKEND=sqlite`. Używać SQLite online backup API, nigdy kopiowania samego pliku DB podczas pracy. PR #54 zapewnia weryfikację i bezpieczne odtworzenie pojedynczego backupu tej bazy. |
| Dokumenty SQLite | `DATA_DIR/private_documents/documents.sqlite3` | Magazyn warunkowy, wybierany przez `DocumentRepositoryFactory`. Przed włączeniem do backupu trzeba potwierdzić, że fabryka jest rzeczywiście tworzona w działającej ścieżce aplikacji i że wybrany backend to SQLite. W obecnej bazowej wersji fabryka odczytuje niewłaściwe pole ustawień; poprawka jest w osobnym PR #55 i nie jest jeszcze scalona. |
| Rejestr poświadczeń SQLite | `ISKRA_CREDENTIAL_DB_PATH` | Warunkowy. `wsgi.py` tworzy `SQLiteCredentialStore` tylko wtedy, gdy zmienna jest ustawiona. Zawiera skróty tokenów, tożsamości, tenantów i zdarzenia audytowe; musi być traktowany jako dane wrażliwe i objęty prywatnym backupem, jeżeli jest aktywny. |
| PostgreSQL | `ISKRA_POSTGRES_DSN`, osobno backend tenantów i dokumentów | Gdy którykolwiek backend jest ustawiony na PostgreSQL, lokalny backup plikowy nie obejmuje tego zasobu. Wymagany osobny, natywny backup PostgreSQL i kontrola jego odtwarzalności. Nie kopiować DSN ani sekretów do manifestu. |
| Sekrety i konfiguracja hostingu | Zmienne środowiskowe / panel dostawcy | Nie umieszczać wartości sekretów w archiwum ani logach. Odtwarzanie wymaga osobnej procedury odtworzenia sekretów z bezpiecznego menedżera hostingu. |
| Surowe pliki przesłane przez klientów | Nie potwierdzono osobnego trwałego katalogu w przejrzanych modułach repozytorium dokumentów | Repozytorium dokumentów przechowuje metadane i chunki tekstu w SQLite. Przed deklaracją kompletności trzeba przeszukać pełny kod ścieżki upload/parser i hosting pod kątem osobnych plików, bucketów lub wolumenów. |

## Wymagany kontrakt backupu

1. Odczytaj i zwaliduj ustawienia backendów oraz ścieżki z aktywnego procesu wdrożenia. Nie wypisuj wartości sekretów.
2. Ustal listę zasobów wymaganych i warunkowych. Jeśli zasób wymagany jest skonfigurowany, ale nieosiągalny, zakończ backup błędem.
3. Wstrzymaj wszystkie zapisy aplikacji i workerów na czas tworzenia wspólnego punktu w czasie. Osobne kopie online SQLite nie gwarantują spójności między różnymi bazami.
4. Dla każdej aktywnej bazy SQLite użyj `Connection.backup()`; wykonaj `PRAGMA integrity_check` i `PRAGMA foreign_key_check` na kopii.
5. Dla JSON uzyskaj blokadę zapisu, skopiuj kompletny plik i zweryfikuj parsowanie oraz wymagany schemat.
6. Zapisz manifest zawierający wyłącznie ścieżkę logiczną, typ zasobu, wersję schematu/aplikacji, rozmiar, SHA-256, tryb pliku i czas UTC. Bez sekretów, DSN, tokenów ani danych dostępowych.
7. Archiwum i katalogi tymczasowe twórz z uprawnieniami prywatnymi (docelowo katalog 0700, pliki 0600). Nie podążaj za dowiązaniami symbolicznymi.
8. Weryfikuj wszystkie sumy i schematy przed odtworzeniem. Odtwarzaj wyłącznie do nowego katalogu staging; nigdy nie nadpisuj istniejących plików.
9. Po odtworzeniu uruchom testy integralności, liczności rekordów, relacji tenantów i smoke testy tylko do odczytu.
10. Udokumentuj, które zasoby były pominięte jako nieaktywne, a które są zewnętrzne (PostgreSQL, object storage, sekrety hostingu).

## Warunki uznania backupu za kompletny

- Zapis aplikacji i workerów był wstrzymany, a moment snapshotu udokumentowany.
- Każdy aktywny magazyn trwałych danych został objęty backupem albo jawnie wykazany jako zewnętrzny z potwierdzonym backupem dostawcy.
- Wszystkie kopie SQLite przeszły integrity i foreign-key checks.
- JSON przeszedł walidację schematu i parsowania.
- Manifest i sumy SHA-256 są poprawne; archiwum nie zawiera sekretów.
- Odtworzenie do pustego katalogu staging przeszło bez nadpisywania i testy odczytowe potwierdziły dane.
- Trwałość wolumenu na hostingu została potwierdzona oddzielnie. Samo istnienie pliku w kontenerze nie dowodzi trwałości po redeploy/restart.

## Otwarte ryzyka / czego ten audyt jeszcze nie dowodzi

- Nie odczytano konfiguracji środowiska produkcyjnego ani zawartości dysku hostingu.
- Nie potwierdzono, czy credential registry i dokumentowy backend są faktycznie aktywne.
- Nie potwierdzono osobnego object storage dla oryginalnych uploadów.
- Nie przeprowadzono backupu ani restore danych produkcyjnych.
- PR #54 obejmuje tylko graf tenantów SQLite, a PR #55 naprawia wybór backendu dokumentów; oba pozostają draft i nie są scalone.

## Plan walidacji implementacji

Przed dodaniem automatycznego archiwizatora należy przygotować testy dla: zasobu wymaganego, zasobu warunkowego nieaktywnego, brakującego zasobu aktywnego, snapshotu SQLite w trybie WAL, JSON w trakcie zapisu, uszkodzonego pliku, niezgodnego manifestu, zmienionej sumy, dowiązania symbolicznego, próby nadpisania celu restore oraz wycieku sekretów. Test integracyjny powinien tworzyć wszystkie aktywne zasoby w katalogu tymczasowym, wykonać snapshot i odtworzyć je do nowego katalogu staging.
