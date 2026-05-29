#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import threading
import tempfile
import shutil
import requests
import re
from flask import Flask, jsonify, render_template_string

# =========================
# KONFIGURACJA
# =========================
PORT = int(os.environ.get("PORT", 10000))
DATA_DIR = os.path.abspath(os.path.dirname(__file__))
PLIK_SIECI = os.path.join(DATA_DIR, "wiedza.json")

REQUEST_TIMEOUT = 45
REQUEST_RETRIES = 2

app = Flask(__name__)

# =========================
# SIECIOWA PAMIĘĆ GRAFOWA
# =========================
class SiecNeuronowa:
    def __init__(self):
        self.lock = threading.RLock()
        # Domyślny, niezmienny fundament 12 filarów w pamięci RAM
        self.fundament = {
            "neurons": {
                "n_logika": {"label": "1. Logika i Rozumowanie", "weight": 1.0, "created": time.time()},
                "n_epistemologia": {"label": "2. Epistemologia", "weight": 1.0, "created": time.time()},
                "n_etyka": {"label": "3. Etyka i Wartości", "weight": 1.0, "created": time.time()},
                "n_ontologia": {"label": "4. Ontologia i Metafizyka", "weight": 1.0, "created": time.time()},
                "n_przyrodnicze": {"label": "5. Nauki Przyrodnicze", "weight": 1.0, "created": time.time()},
                "n_spoleczne": {"label": "6. Nauki Społeczne i Psychologia", "weight": 1.0, "created": time.time()},
                "n_jezyk": {"label": "7. Język i Komunikacja", "weight": 1.0, "created": time.time()},
                "n_historia": {"label": "8. Historia i Kultura", "weight": 1.0, "created": time.time()},
                "n_technologia": {"label": "9. Technologia i Sztuczna Inteligencja", "weight": 1.0, "created": time.time()},
                "n_sztuka": {"label": "10. Sztuka i Kreatywność", "weight": 1.0, "created": time.time()},
                "n_zdrowie": {"label": "11. Zdrowie i Rozwój Osobisty", "weight": 1.0, "created": time.time()},
                "n_metapoznanie": {"label": "12. Metapoznanie", "weight": 1.0, "created": time.time()}
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
                {"from": "n_zdrowie", "to": "n_metapoznanie", "strength": 0.80}
            ]
        }
        self.dane = json.loads(json.dumps(self.fundament))
        self.laduj()

    def laduj(self):
        with self.lock:
            if not os.path.exists(PLIK_SIECI) or os.path.getsize(PLIK_SIECI) == 0:
                print("Sieć: Plik bazy nie istnieje. Uruchamianie czystej matrycy z pamięci RAM.")
                self.dane = json.loads(json.dumps(self.fundament))
                self.zapisz()
                return

            try:
                with open(PLIK_SIECI, "r", encoding="utf-8") as f:
                    wczytane = json.load(f)
                
                # Walidacja: Jeśli w pliku nie ma kluczowych węzłów, nadpisujemy strukturą 12 filarów
                if "n_logika" not in wczytane.get("neurons", {}):
                    print("Sieć: Nieprawidłowa struktura pliku. Wymuszam reset do 12 filarów.")
                    self.dane = json.loads(json.dumps(self.fundament))
                    self.zapisz()
                else:
                    self.dane = wczytane
            except Exception as e:
                print(f"Sieć: Błąd odczytu pliku ({e}). Pozostaję przy bezpiecznej strukturze z pamięci RAM.")
                self.dane = json.loads(json.dumps(self.fundament))

    def zapisz(self):
        with self.lock:
            try:
                # Bezpieczny zapis atomowy z łapaniem błędów uniemożliwiający wysypanie programu
                with tempfile.NamedTemporaryFile("w", delete=False, dir=DATA_DIR, encoding="utf-8") as tmp:
                    json.dump(self.dane, tmp, ensure_ascii=False, indent=4)
                    temp_name = tmp.name
                shutil.move(temp_name, PLIK_SIECI)
            except Exception as e:
                print(f"Sieć: [Ignorowany błąd we/wy] Nie udało się zapisać stanu na dysk: {e}")

    def aktualizuj_siec(self, nowa_struktura):
        with self.lock:
            for k, v in nowa_struktura.get("neurons", {}).items():
                if k not in self.dane["neurons"]:
                    self.dane["neurons"][k] = {
                        "label": v.get("label", "Nieznany"),
                        "weight": min(max(float(v.get("weight", 0.5)), 0.0), 1.0),
                        "created": time.time()
                    }
                else:
                    stara_waga = self.dane["neurons"][k]["weight"]
                    nowa_waga = float(v.get("weight", stara_waga))
                    self.dane["neurons"][k]["weight"] = min(max(stara_waga * 0.7 + nowa_waga * 0.3, 0.0), 1.0)

            for s in nowa_struktura.get("synapses", []):
                f_id = s.get("from")
                t_id = s.get("to")
                str_val = min(max(float(s.get("strength", 0.5)), 0.0), 1.0)
                
                if f_id in self.dane["neurons"] and t_id in self.dane["neurons"]:
                    istnieje = False
                    for ist_s in self.dane["synapses"]:
                        if ist_s["from"] == f_id and ist_s["to"] == t_id:
                            ist_s["strength"] = min(max(ist_s["strength"] * 0.5 + str_val * 0.5, 0.0), 1.0)
                            istnieje = True
                            break
                    if not istnieje:
                        self.dane["synapses"].append({"from": f_id, "to": t_id, "strength": str_val})
            self.zapisz()

# =========================
# PROVIDER DEEPSEEK
# =========================
class DeepSeekProvider:
    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.url = "https://api.deepseek.com/v1/chat/completions"
        self.model = "deepseek-chat"

    def generate(self, prompt):
        if not self.api_key:
            print("BŁĄD: Brak klucza DEEPSEEK_API_KEY!")
            return None
        
        headers = {
            "Authorization": f"Bearer {self.api_key}", 
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.4,
            "response_format": {"type": "json_object"}
        }
        
        for _ in range(REQUEST_RETRIES):
            try:
                r = requests.post(self.url, headers=headers, json=data, timeout=REQUEST_TIMEOUT)
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
                else:
                    print(f"DeepSeek API Error: {r.status_code}")
            except Exception as e:
                print(f"Błąd połączenia API: {e}")
                time.sleep(3)
        return None

class RouterProvider:
    def __init__(self):
        self.deepseek = DeepSeekProvider()

    def clean_json(self, text):
        if not text:
            return None
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return match.group(0)
        return text

    def generate(self, prompt):
        raw_res = self.deepseek.generate(prompt)
        return self.clean_json(raw_res)

# =========================
# AUTONOMICZNY SILNIK
# =========================
class IskraAutonomiczna:
    def __init__(self, siec):
        self.siec = siec
        self.router = RouterProvider()
        self.running = True
        self.thread = threading.Thread(target=self.petla_aktywnosci, daemon=True)
        self.thread.start()
        print("=== AUTONOMICZNA ISKRA URUCHOMIONA (MATRYCA 12 FILARÓW) ===")

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
                nList.innerHTML = '';
                Object.entries(d.neurons).forEach(([id, n]) => {
                    nList.innerHTML += `<li><span>${n.label}</span><span class="badge">Waga: ${n.weight.toFixed(2)}</span></li>`;
                });

                const sList = document.getElementById('synapses-list');
                sList.innerHTML = '';
                d.synapses.sort((a,b) => b.strength - a.strength).slice(0, 25).forEach(s => {
                    const od = d.neurons[s.from]?.label || s.from;
                    const do_ = d.neurons[s.to]?.label || s.to;
                    sList.innerHTML += `<li><span>${od} → ${do_}</span><span class="badge" style="background:#0284c7">Moc: ${s.strength.toFixed(2)}</span></li>`;
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
    return jsonify({"status": "ok", "neurons": len(siec.dane["neurons"])})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
