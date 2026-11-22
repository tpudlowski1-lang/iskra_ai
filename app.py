#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import threading

from flask import Flask, jsonify, render_template_string

# =========================
# KONFIGURACJA
# =========================
from iskra.config import load_settings
from iskra.security.headers import install_security_headers

settings = load_settings()
PORT = settings.port
DATA_DIR = settings.data_dir
os.makedirs(DATA_DIR, exist_ok=True)
PLIK_SIECI = os.path.join(DATA_DIR, "wiedza.json")

app = install_security_headers(Flask(__name__))

# =========================
# MODULAR DOMAIN IMPORTS
# =========================
import iskra.knowledge.graph as _graph_store
from iskra.llm.router import RouterProvider

class SiecNeuronowa(_graph_store.SiecNeuronowa):
    """Compatibility façade honoring legacy app.DATA_DIR overrides in tests/deployments."""
    def __init__(self):
        _graph_store.DATA_DIR = DATA_DIR
        _graph_store.PLIK_SIECI = PLIK_SIECI
        super().__init__()

# =========================
# AUTONOMICZNY SILNIK
# =========================
class IskraAutonomiczna:
    def __init__(self, siec):
        self.siec = siec
        self.router = RouterProvider()
        self.running = True
        self.thread = None
        # Gunicorn uruchamia wiele workerów. Pętla w tle przy imporcie modułu
        # mnożyłaby procesy i koszty; włączamy ją wyłącznie świadomą zmienną ENV.
        enabled = os.environ.get("ENABLE_AUTONOMOUS_LOOP", "false").strip().lower() in ("1", "true", "yes", "on")
        if enabled:
            self.thread = threading.Thread(target=self.petla_aktywnosci, daemon=True)
            self.thread.start()
            print("=== AUTONOMICZNA ISKRA: PĘTLA WŁĄCZONA ===")
        else:
            print("=== ISKRA: Pętla autonomiczna wyłączona (ENABLE_AUTONOMOUS_LOOP=false) ===")

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

# Inicjalizacja obiektów globalnych
siec = SiecNeuronowa()
bot = IskraAutonomiczna(siec)

# =========================
# DASHBOARD WEB
# =========================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ISKRA AI — Rdzeń Wiedzy</title>
    <style>
        body { margin:0; background:#040712; color:#e2e8f0; font-family:sans-serif; padding: 20px; }
        .container { max-width: 1100px; margin: 0 auto; }
        h1 { color: #0ea5e9; font-weight: 300; border-bottom: 1px solid #334155; padding-bottom: 10px; font-size: 24px; letter-spacing: 0.5px; }
        .stats { display: flex; gap: 20px; margin-bottom: 30px; }
        .card { background: #0f172a; padding: 20px; border-radius: 12px; flex: 1; border: 1px solid #1e293b; }
        .card h3 { margin: 0 0 10px 0; color: #64748b; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; }
        .card p { margin: 0; font-size: 28px; font-weight: bold; color: #f1f5f9; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .box { background: #0f172a; border-radius: 12px; padding: 20px; height: 450px; overflow-y: auto; border: 1px solid #1e293b; }
        h2 { font-size: 15px; margin-top: 0; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.5px; }
        ul { list-style: none; padding: 0; margin: 0; }
        li { background: #1e293b; padding: 12px; margin-bottom: 8px; border-radius: 6px; font-size: 14px; display: flex; justify-content: space-between; align-items: center; border-left: 3px solid #38bdf8; }
        .badge { background: #0369a1; color: #f0f9ff; padding: 4px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; }
    </style>
</head>
<body>
    <div class="container">
        <h1>ISKRA AI — System Mapowania Wiedzy i Metapoznania</h1>
        <div class="stats">
            <div class="card"><h3>Węzły (Kategorie)</h3><p id="count-n">-</p></div>
            <div class="card"><h3>Korelacje (Synapsy)</h3><p id="count-s">-</p></div>
            <div class="card"><h3>Status Układu</h3><p style="color: #38bdf8; font-size: 18px; margin-top:8px; font-weight: 500;">12 Filarów / Stabilny RAM</p></div>
        </div>
        <div class="grid">
            <div class="box"><h2>Struktura Pojęciowa</h2><ul id="neurons-list"></ul></div>
            <div class="box"><h2>Powiązania i Korelacie</h2><ul id="synapses-list"></ul></div>
        </div>
    </div>
    <script>
        async function updateData() {
            try {
                const r = await fetch('/api/network');
                const d = await r.json();
                document.getElementById('count-n').textContent = Object.keys(d.neurons).length;
                document.getElementById('count-s').textContent = d.synapses.length;
                
                const nList = document.getElementById('neurons-list');
                nList.replaceChildren();
                Object.entries(d.neurons || {}).forEach(([id, neuron]) => {
                    const item = document.createElement('li');
                    const label = document.createElement('span');
                    label.textContent = String(neuron.label ?? id);
                    const badge = document.createElement('span');
                    badge.className = 'badge';
                    const weight = Number(neuron.weight);
                    badge.textContent = `Waga: ${Number.isFinite(weight) ? weight.toFixed(2) : '—'}`;
                    item.append(label, badge);
                    nList.append(item);
                });

                const sList = document.getElementById('synapses-list');
                sList.replaceChildren();
                [...(Array.isArray(d.synapses) ? d.synapses : [])]
                    .sort((a, b) => Number(b.strength) - Number(a.strength))
                    .slice(0, 25)
                    .forEach(synapse => {
                        const item = document.createElement('li');
                        const relation = document.createElement('span');
                        const source = d.neurons?.[synapse.from]?.label ?? synapse.from;
                        const target = d.neurons?.[synapse.to]?.label ?? synapse.to;
                        relation.textContent = `${source} → ${target}`;
                        const badge = document.createElement('span');
                        badge.className = 'badge';
                        badge.style.backgroundColor = '#0284c7';
                        const strength = Number(synapse.strength);
                        badge.textContent = `Moc: ${Number.isFinite(strength) ? strength.toFixed(2) : '—'}`;
                        item.append(relation, badge);
                        sList.append(item);
                    });
            } catch(e) {}
        }
        // Odświeżanie raz na 15 sekund, żeby darmowy serwer działał stabilnie
        setInterval(updateData, 15000);
        updateData();
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/network')
def get_network():
    with siec.lock:
        return jsonify(siec.dane)

@app.route('/health')
def health():
    with siec.lock:
        return jsonify({"status": "ok", "neurons": len(siec.dane["neurons"])})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
