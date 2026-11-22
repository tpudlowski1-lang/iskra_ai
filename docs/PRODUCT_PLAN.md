# Iskra AI — plan produktu komercyjnego

## Decyzja produktowa

Budujemy Iskra AI jako asystenta wiedzy i obsługi klienta dla małych polskich firm. Pierwszym segmentem testowym są małe firmy usługowe, które regularnie odpowiadają na podobne pytania i przygotowują oferty na podstawie własnych dokumentów.

Nie budujemy na start ogólnego chatbota ani autonomicznego agenta wysyłającego wiadomości bez kontroli człowieka.

## Problem klienta

Właściciel małej firmy traci czas na:
- powtarzalne pytania klientów;
- szukanie informacji w PDF-ach, cennikach, regulaminach i notatkach;
- przygotowywanie podobnych ofert i odpowiedzi;
- przekazywanie wiedzy pracownikom.

## MVP — płatna wartość

1. Konto firmy i izolacja danych każdego klienta.
2. Dodawanie dokumentów PDF, DOCX i TXT.
3. Wyszukiwanie odpowiedzi w dokumentach firmy (RAG).
4. Odpowiedź z odnośnikami do źródeł/fragmentów dokumentów.
5. Generator szkiców odpowiedzi i ofert do zatwierdzenia przez człowieka.
6. Historia zapytań, limity użycia i panel właściciela.
7. Możliwość usunięcia dokumentu i danych firmy.

## Czego nie robimy w pierwszej wersji

- automatycznej wysyłki e-maili lub wiadomości do klientów;
- autonomicznego podejmowania decyzji biznesowych;
- trenowania modelu na poufnych dokumentach klientów;
- obietnic stuprocentowej poprawności;
- rozbudowanego marketplace pluginów;
- aplikacji mobilnej — najpierw responsywny panel WWW.

## Architektura docelowa

- Flask jako API, z podziałem na moduły: auth, tenants, documents, retrieval, chat, billing, audit.
- PostgreSQL jako źródło prawdy: użytkownicy, firmy, role, dokumenty, limity i historia.
- Wyszukiwanie wektorowe z filtrowaniem po tenant_id; na MVP można użyć pgvector albo sprawdzonego adaptera wektorowego.
- Warstwa LLM z jednolitym interfejsem providerów, timeoutami, retry, fallbackiem i kontrolą kosztów.
- Pliki w prywatnym storage, nie w efemerycznym katalogu instancji serwera.
- Logi bez treści poufnych dokumentów i sekretów.
- Gunicorn bez uruchamiania autonomicznych pętli w każdym workerze.

## Bezpieczeństwo i zaufanie

- Każde zapytanie do danych musi być ograniczone do tenant_id z uwierzytelnionej sesji.
- Brak możliwości podania tenant_id przez klienta jako źródła uprawnień.
- Szyfrowanie transmisji, sekrety tylko w zmiennych środowiskowych.
- Ochrona przed prompt injection z dokumentów i jawne oddzielenie instrukcji od treści źródłowych.
- Odpowiedź ma wskazywać źródła; gdy brak podstaw w dokumentach, asystent ma powiedzieć, że nie wie.
- Usuwanie danych, retencja i dokumentacja prywatności zgodne z wymaganiami RODO przed sprzedażą.

## Model przychodów — hipoteza do walidacji

- Starter: 49–99 zł/mies. — mały limit dokumentów i zapytań.
- Pro: 149–299 zł/mies. — większe limity, kilku użytkowników, szablony ofert.
- Wdrożenie indywidualne: wycena po rozmowie.

To są ceny testowe, nie potwierdzony popyt. Najpierw trzeba zdobyć 3–5 firm pilotażowych i sprawdzić, czy oszczędność czasu uzasadnia abonament.

## Kolejność realizacji

1. Naprawić niespójność providerów i uruchamianie procesu.
2. Wydzielić czysty rdzeń API i testy.
3. Dodać logowanie, firmy i izolację tenantów.
4. Dodać bezpieczny upload i indeksowanie dokumentów.
5. Dodać RAG z cytowaniem źródeł.
6. Dodać limity, rejestr zużycia i panel.
7. Przeprowadzić testy izolacji danych, bezpieczeństwa i kosztów.
8. Uruchomić pilotaż z 3–5 firmami; dopiero potem płatności i automatyzacje.

## Kryterium sukcesu MVP

Użytkownik firmy może wgrać własne dokumenty, zadać pytanie i otrzymać użyteczną odpowiedź opartą na wskazanych fragmentach tych dokumentów — bez dostępu do danych innych firm. To jest pierwsza rzecz, za którą klient może realnie zapłacić.
