"""Explicitly opt-in autonomous knowledge graph worker."""
import json
import os
import threading
import time

from iskra.llm.router import RouterProvider

class IskraAutonomiczna:
    def __init__(self, siec):
        self.siec = siec
        self.router = RouterProvider()
        self.running = True
        self.thread = None
        # Gunicorn uruchamia wiele workerów. Pętla w tle przy imporcie modułu
        # mnożyłaby procesy i koszty; włączamy ją wyłącznie świadomą zmienną ENV.
        enabled = os.environ.get("ENABLE_AUTONOMOUS_LOOP", "false").strip().lower() in ("1", "true", "yes", "on")
        process_role = os.environ.get("ISKRA_PROCESS_ROLE", "web").strip().lower()
        # Never launch background work from a WSGI/Gunicorn web worker. A
        # dedicated process must opt in with ISKRA_PROCESS_ROLE=worker.
        if enabled and process_role == "worker":
            self.thread = threading.Thread(target=self.petla_aktywnosci, daemon=True)
            self.thread.start()
            print("=== AUTONOMICZNA ISKRA: PĘTLA WŁĄCZONA ===")
        else:
            print("=== ISKRA: Pętla autonomiczna wyłączona (wymaga ENABLE_AUTONOMOUS_LOOP=true i ISKRA_PROCESS_ROLE=worker) ===")

    def petla_aktywnosci(self):
        print("Bot: Bezpieczny sen startowy (10 sekund)...")
        time.sleep(10)
        while self.running:
            try:
                print("Bot: Rozpoczynam nowy cykl mapowania matrycy wiedzy...")
                with self.siec.lock:
                    stan_sieci = json.dumps(self.siec.dane, ensure_ascii=False)
                
                prompt = f"""
Jesteś autonomicznym systemem Iskra. Mapujesz i analizujesz powiązania pojęciowe w oparciu o 12 fundamentalnych obszarów:
1. Logika i rozumowanie (zasady myślenia, błędy poznawcze, matematyka, algorytmy)
2. Epistemologia (teoria poznania, prawda, metody naukowe)
3. Etyka i wartości (dobro, sprawiedliwość, wolność, Dekalog)
4. Ontologia i metafizyka (byt, przyczynowość, umysł-ciało)
5. Nauki przyrodnicze (fizyka, chemia, biologia, astronomia)
6. Nauki społeczne i psychologia (poznawcza, socjologia, ekonomia)
7. Język i komunikacja (semantyka, pragmatyka, manipulacja językowa)
8. Historia i kultura (wydarzenia, rozwój cywilizacji, różnorodność)
9. Technologia i sztuczna inteligencja (sieci neuronowe, programowanie, etyka AI)
10. Sztuka i kreatywność (estetyka, proces twórczy, wyobraźnia)
11. Zdrowie i rozwój osobisty (higiena, uważność, samodyscyplina)
12. Metapoznanie (myślenie o myśleniu, monitorowanie własnych błędów)

Aktualny stan grafu sieci: {stan_sieci}

Zadanie: Wybierz podaspekty z tych obszarów, dokonaj ich syntezy lub uszczegółowienia. Wygeneruj dokładnie 1 lub 2 nowe podpojęcia (nadaj im precyzyjne klucze techniczne, np. "n_falsyfikacja", "n_deontologia", "n_algorytmika") i stwórz dla nich logiczne, merytoryczne synapsy z istniejącymi lub nowymi węzłami.

Respond ONLY with a valid JSON object matching this schema:
{{
  "neurons": {{
    "n_nowy_id": {{ "label": "Precyzyjna Nazwa Pojęcia", "weight": 0.85 }}
  }},
  "synapses": [
    {{ "from": "n_logika", "to": "n_nowy_id", "strength": 0.80 }}
  ]
}}
"""
                odpowiedz_json = self.router.generate(prompt)
                if odpowiedz_json:
                    print("Bot: Otrzymano poprawną strukturę JSON z API DeepSeek.")
                    nowe_dane = json.loads(odpowiedz_json)
                    self.siec.aktualizuj_siec(nowe_dane)
                    print("Bot: Pomyślnie zaktualizowano graf mapy wiedzy.")
                else:
                    print("Bot: Router zwrócił pustą odpowiedź.")
            except Exception as e:
                print(f"BŁĄD W CYKLU MAPOWANIA: {e}")
            
            print("Bot: Idę spać na 45 sekund...")
            time.sleep(45)
