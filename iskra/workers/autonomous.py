"""Explicitly opt-in autonomous knowledge graph worker."""
import json
import os
import threading
import time

from iskra.llm.router import RouterProvider


# Fixed public taxonomy only. Never derive outbound worker context from the
# mutable legacy graph, which may contain user or customer supplied material.
PUBLIC_RESEARCH_CONTEXT = {
    "neurons": {
        "n_logika": {"label": "Logika i rozumowanie"},
        "n_epistemologia": {"label": "Epistemologia"},
        "n_etyka": {"label": "Etyka i wartości"},
        "n_ontologia": {"label": "Ontologia i metafizyka"},
        "n_przyrodnicze": {"label": "Nauki przyrodnicze"},
        "n_spoleczne": {"label": "Nauki społeczne i psychologia"},
        "n_jezyk": {"label": "Język i komunikacja"},
        "n_historia": {"label": "Historia i kultura"},
        "n_technologia": {"label": "Technologia i sztuczna inteligencja"},
        "n_sztuka": {"label": "Sztuka i kreatywność"},
        "n_zdrowie": {"label": "Zdrowie i rozwój osobisty"},
        "n_metapoznanie": {"label": "Metapoznanie"},
    },
    "synapses": [
        {"from": "n_logika", "to": "n_epistemologia", "strength": 0.95},
        {"from": "n_logika", "to": "n_technologia", "strength": 0.90},
        {"from": "n_epistemologia", "to": "n_ontologia", "strength": 0.85},
        {"from": "n_etyka", "to": "n_spoleczne", "strength": 0.80},
        {"from": "n_ontologia", "to": "n_przyrodnicze", "strength": 0.85},
        {"from": "n_przyrodnicze", "to": "n_technologia", "strength": 0.80},
        {"from": "n_jezyk", "to": "n_spoleczne", "strength": 0.75},
        {"from": "n_historia", "to": "n_sztuka", "strength": 0.70},
        {"from": "n_metapoznanie", "to": "n_logika", "strength": 0.90},
        {"from": "n_zdrowie", "to": "n_metapoznanie", "strength": 0.80},
    ],
}


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

    @staticmethod
    def _build_research_prompt():
        """Build a bounded prompt from fixed public taxonomy, never user graph data."""
        safe_context = json.dumps(
            PUBLIC_RESEARCH_CONTEXT, ensure_ascii=False, separators=(",", ":")
        )
        return f"""
Jesteś autonomicznym systemem Iskra. Pracujesz wyłącznie na poniższym,
stałym publicznym szkielecie 12 obszarów wiedzy. Nie otrzymujesz danych
użytkowników ani dynamicznej zawartości grafu.

Bezpieczny kontekst bazowy: {safe_context}

Wybierz podaspekty z tych obszarów i dokonaj ich syntezy lub uszczegółowienia.
Wygeneruj dokładnie 1 lub 2 nowe podpojęcia (np. "n_falsyfikacja",
"n_deontologia", "n_algorytmika"). Łącz je wyłącznie z istniejącymi
identyfikatorami z powyższego publicznego szkieletu lub z nowymi węzłami
w tej samej odpowiedzi. Nie zakładaj istnienia innych identyfikatorów.

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

    def petla_aktywnosci(self):
        print("Bot: Bezpieczny sen startowy (10 sekund)...")
        time.sleep(10)
        while self.running:
            try:
                print("Bot: Rozpoczynam nowy cykl mapowania matrycy wiedzy...")
                prompt = self._build_research_prompt()
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
