# Iskra AI — karta kwalifikacji pilota

**Przedmiot rozmowy:** prywatny pilotaż polskojęzycznego systemu wiedzy. Klient i operator sprawdzają, czy odrębne grafy wiedzy, dwanaście filarów Iskry oraz kontrolowany dostęp dają wartość w jednym konkretnym procesie pracy. Segment, cena, warunki wsparcia i decyzja o sprzedaży pozostają do potwierdzenia.

| Scenariusz odbioru na danych demonstracyjnych | Mierzalny wynik |
|---|---|
| Administrator wydaje użytkownikowi poświadczenie i loguje się do `/assistant` | Użytkownik widzi własny tenant, a rotacja poświadczenia unieważnia dotychczasową sesję |
| Dwa zespoły zapisują własne grafy przez API | Po restarcie każdy widzi swój zapis i komplet filarów |
| Operator odtwarza kopię do osobnej bazy | Odczytane grafy odpowiadają źródłu, ważne sesje zachowują swój stan. Operator osobno zabezpiecza klucz CSRF i mierzy czas odtworzenia |

W tej wersji demonstracyjnej operator przygotowuje tenant i poświadczenia. Ingestia dokumentów, dostawcy LLM i automatyczne działania są wyłączone. Zakres oferty obejmuje instalację, przejście przez scenariusze z klientem oraz protokół odbioru. Uruchomienie na danych klienta wymaga odrębnego odbioru bezpieczeństwa i zasad przetwarzania.

## Koszt jednego pilota

Wpisz rzeczywiste stawki w PLN netto i wspólny okres rozliczeniowy. Rozdziel koszt pierwszej instalacji od utrzymania.

| Pozycja | Dane do zebrania | Obliczenie |
|---|---|---|
| Wdrożenie | czas konfiguracji, importu i szkolenia, koszt roboczogodziny | suma godzin × stawka |
| Infrastruktura | aplikacja, PostgreSQL, trwały dysk, kopie, monitoring | suma faktur przypisana do pilota |
| Obsługa | zmierzony czas wsparcia i odtworzeń za okres | godziny × stawka |
| Model | koszt wywołań przy obu pustych listach dostawców | 0 za inferencję w tym wariancie |
| Wycena | koszt dostarczenia i docelowa marża brutto jako ułamek z przedziału [0, 1) | cena netto = koszt / (1 − marża) |

W rozmowie zapisz zadanie klienta, częstotliwość, czas i koszt dzisiejszego rozwiązania, właściciela budżetu oraz kryterium akceptacji. Po demonstracji zanotuj rzeczywistą deklarację udziału i proponowaną cenę. Zgodnie z [bramką komercyjną](COMMERCIAL_READINESS.md) uzasadnij wybór grupy docelowej co najmniej pięcioma rozmowami. Przed sprzedażą uzupełnij warunki licencji i dystrybucji, prywatności, płatności, wsparcia i odpowiedzialności operacyjnej.
