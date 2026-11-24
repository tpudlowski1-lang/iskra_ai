# Instalacja pilota Iskra AI

Pakiet źródłowy dla Linux z Pythonem 3.11 lub 3.12 wymaga modułu venv i dostępu do indeksu pakietów. Rozpakuj archiwum w katalogu użytkownika usługi i uruchom `./install.sh`. Instalacja tworzy lokalne środowisko `.venv`. Nową wersję rozpakuj do osobnego katalogu. Dane i sekrety przechowuj poza nim. Do pilota używaj danych syntetycznych.

## Pierwsze uruchomienie na jednym komputerze

Poniższe polecenia wykonaj w katalogu wydania w Bash. Klucz CSRF wygeneruj raz i zachowaj między restartami. Polecenie wydania poświadczenia pokazuje nowy token tylko raz.

```bash
umask 077
export DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/iskra-pilot"
install -d -m 700 "$DATA_DIR" "$DATA_DIR/auth"
export ISKRA_CREDENTIAL_DB_PATH="$DATA_DIR/auth/credentials.sqlite3"
if [ ! -f "$DATA_DIR/auth/csrf.key" ]; then
  (set -C; .venv/bin/python -c 'import secrets; print(secrets.token_hex(32))' > "$DATA_DIR/auth/csrf.key") || exit 1
fi
export ISKRA_CSRF_HMAC_SECRET="$(cat "$DATA_DIR/auth/csrf.key")"
export ENABLE_AUTONOMOUS_LOOP=false ISKRA_ENABLE_DOCUMENT_INGESTION=false
export LLM_ALLOWED_PROVIDERS='' ISKRA_TENANT_PROVIDER_ALLOWLIST_JSON='{}'
.venv/bin/python -m scripts.manage_credentials issue --subject operator-pilota \
  --tenant-id pilot --roles admin --allow-admin --confirm
.venv/bin/gunicorn wsgi:app --bind 127.0.0.1:8000 --workers 1 --threads 4 --timeout 120
```

Serwer deweloperski uruchamiany poleceniem `python app.py` domyślnie nasłuchuje na `127.0.0.1`. Jawne ustawienie `ISKRA_DEV_BIND` pozwala wybrać inny adres. W hostowanym pilocie użyj Gunicorna i wejścia `wsgi:app`.

Sprawdź `GET /health`. Chronione API akceptuje token Bearer. Interfejs `/assistant` korzysta z ciasteczka Secure. Do testu przeglądarkowego i hostowanego stagingu używaj HTTPS z zaufanym certyfikatem. Sekrety do hostingu wprowadź w menedżerze sekretów.

## PostgreSQL w stagingu

Zachowaj jeden proces Gunicorn i prywatny trwały katalog `DATA_DIR` dla globalnego grafu JSON. Ustaw `ISKRA_TENANT_STORAGE_BACKEND=postgres`, `ISKRA_DOCUMENT_STORAGE_BACKEND=postgres` i `ISKRA_POSTGRES_DSN` roli danych tenantów zgodnie z [procedurą migracji grafu](POSTGRES_STAGING_RUNBOOK.md). Dla rejestru poświadczeń użyj osobnego schematu i loginów. Na pustej testowej bazie administrator tworzy trzy role grupowe i schemat:

```sql
CREATE ROLE iskra_auth_owner NOLOGIN;
CREATE ROLE iskra_auth_operator NOLOGIN;
CREATE ROLE iskra_auth_runtime NOLOGIN;
CREATE SCHEMA iskra_auth AUTHORIZATION iskra_auth_owner;
```

Nadaj rolę właściciela wyłącznie operatorowi migracji. W jego sesji wykonaj `psql -X -1 -v ON_ERROR_STOP=1 -f migrations/0003_credential_store.sql` **raz**. Transakcja wycofa całość w razie błędu. Migracja zachowuje sekundy epoki z istniejącego kontraktu SQLite. Wydaje dwie funkcje wyszukiwania po skrócie. Po dokonaniu migracji rola aplikacji nie wykonuje DDL.

| Proces | Konfiguracja |
|---|---|
| Serwer WSGI | `ISKRA_CREDENTIAL_STORE_BACKEND=postgres`, `ISKRA_CREDENTIAL_POSTGRES_DSN` loginu należącego do `iskra_auth_runtime` i `ISKRA_CSRF_HMAC_SECRET` (wspólny sekret minimum 32 bajty) |
| Lokalny operator CLI | `ISKRA_CREDENTIAL_STORE_BACKEND=postgres`, `ISKRA_CREDENTIAL_OPERATOR_DSN` osobnego loginu należącego wyłącznie do `iskra_auth_operator` |
| Administrator bazy | Migruje schemat, zarządza rolami i wykonuje zaszyfrowane kopie zapasowe |

Oba loginy aplikacyjne muszą mieć NOSUPERUSER i NOBYPASSRLS, bez członkostwa w roli właściciela, praw do DDL lub zarządzania rolami. W zdalnych DSN używaj weryfikacji TLS i zaufanego CA. Nie przekazuj loginu migracji ani operatora do serwera WWW. Rejestr startuje pusty. To procedura dla nowego stagingu. Istniejący rejestr SQLite pozostaje odrębny. Zmiana backendu wymaga planu przeniesienia lub ponownego wydania poświadczeń i kontrolowanego wylogowania sesji.

## Odbiór pilota

Na dwóch syntetycznych tenantach sprawdź logowanie w `/assistant`, zapis i odczyt grafu po restarcie, rotację oraz wylogowanie. Odtwórz kopię do osobnej bazy. Ingestia dokumentów, zewnętrzni dostawcy i pętla autonomiczna pozostają wyłączone w tej konfiguracji. Dane klientów, płatności i publiczna sprzedaż wymagają spełnienia [kryteriów komercyjnych projektu](COMMERCIAL_READINESS.md).

Manifest `render.staging.yaml` definiuje oddzielną usługę Render z jednym procesem, dyskiem dla grafu globalnego i dwoma DSN dla istniejącego PostgreSQL. Uruchomienie wymaga konta hostingowego, przygotowanych ról i płatnego planu z dyskiem. Utrzymuj sekrety poza repozytorium. Wskaż w panelu dokładnie zbadany commit i zweryfikuj domenę HTTPS, logowanie, zapis, restart i odtworzenie kopii z hostowanego środowiska. Sam manifest ani pomyślny workflow nie potwierdzają działania tego wdrożenia.

Zakres oferty do rozmów pilotażowych i kalkulacja kosztów znajdują się w [karcie pilota](PILOT_COMMERCIAL_PL.md).

Do próby odtworzenia użyj narzędzi `pg_dump` i `pg_restore` w tej samej wersji głównej co serwer PostgreSQL. Przy odtwarzaniu starszego punktu w czasie uwzględnij unieważnienia poświadczeń po wykonaniu kopii. Przed ponownym otwarciem ruchu uzgodnij stan unieważnień i w razie potrzeby wymień klucz sesji.
