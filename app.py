#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import uuid
import threading
import tempfile
import shutil
import random
import requests
from flask import Flask, jsonify, render_template_string

# =========================
# KONFIGURACJA
# =========================
PORT = int(os.environ.get("PORT", 8080))
DATA_DIR = "/tmp/iskra_data"
os.makedirs(DATA_DIR, exist_ok=True)

PLIK_SIECI = os.path.join(DATA_DIR, "wiedza.json")
REQUEST_TIMEOUT = 45
REQUEST_RETRIES = 3

app = Flask(__name__)

def atomic_save(path, data):
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=4)
        temp_name = tmp.name
    shutil.move(temp_name, path)

# =========================
# SIECIOWA PAMIĘĆ GRAFOWA
# =========================
class SiecNeuronowa:
    def __init__(self):
        self.lock = threading.RLock()
        self.dane = {"neurons": {}, "synapses": []}
        self.laduj()

    def laduj(self):
        if not os.path.exists(PLIK_SIECI):
            # Inicjalizacja sieci bazowymi neuronami (kotwice myślowe)
            self.dane = {
                "neurons": {
                    "n_swiadomosc": {"label": "Świadomość", "weight": 1.0, "created": time.time()},
                    "n_cien": {"label": "Cień", "weight": 1.0, "created": time.time()},
                    "n_ja": {"label": "Jaźń", "weight": 1.0, "created": time.time()}
                },
                "synapses": [
                    {"from": "n_swiadomosc", "to": "n_cien", "strength": 0.5},
                    {"from": "n_ja", "to": "n_swiadomosc", "strength": 0.5}
                ]
            }
            self.zapisz()
            return
        try:
            with open(PLIK_SIECI, "r", encoding="utf-8") as f:
                self.dane = json.load(f)
        except Exception:
            pass

    def zapisz(self):
        with self.lock:
            atomic_save(PLIK_SIECI, self.dane)

    def aktualizuj_siec(self, nowa_struktura):
        """Bezpiecznie łączy wygenerowaną strukturę z obecną siecią"""
        with self.lock:
            # Dodaj/aktualizuj neurony
            for k, v in nowa_struktura.get("neurons", {}).items():
                if k not in self.dane["neurons"]:
                    self.dane["neurons"][k] = {
                        "label": v.get("label", "Nieznany"),
                        "weight": min(max(float(v.get("weight", 0.5)), 0.0), 1.0),
                        "created": time.time()
                    }
                else:
                    # Delikatna aktualizacja wagi istniejącego neuronu
                    stara_waga = self.dane["neurons"][k]["weight"]
                    nowa_waga = float(v.get("weight", stara_waga))
                    self.dane["neurons"][k]["weight"] = min(max(stara_waga * 0.7 + nowa_waga * 0.3, 0.0), 1.0)

            # Dodaj/aktualizuj synapsy
            for s in nowa_struktura.get("synapses", []):
                f_id = s.get("from")
                t_id = s.get("to")
                str_val = min(max(float(s.get("strength", 0.5)), 0.0), 1.0)
                
                if f_id in self.dane["neurons"] and t_id in self.dane["neurons"]:
                    istnieje = False
                    for istniejąca_s in self.dane["synapses"]:
                        if istniejąca_s["from"] == f_id and istniejąca_s["to"] == t_id:
                            istniejąca_s["strength"] = min(max(istniejąca_s["strength"] * 0.5 + str_val * 0.5, 0.0), 1.0)
                            istnieje = True
                            break
                    if not istnieje:
                        self.dane["synapses"].append({"from": f_id, "to": t_id, "strength": str_val})
            
            self.zapisz()

# =========================
# PROVIDERY LLM
# =========================
class OpenAIProvider:
    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.url = "https://api.openai.com/v1/chat/completions"
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def generate(self, prompt):
        if not self.api_key: raise Exception("Brak OPENAI_API_KEY")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8,
            "response_format": {"type": "json_object"} # Wymuszamy czysty JSON
        }
        for _ in range(REQUEST_RETRIES):
            try:
                r = requests.post(self.url, headers=headers, json=data, timeout=REQUEST_TIMEOUT)
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
            except Exception:
                time.sleep(2)
        return None

class GeminiProvider:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    def generate(self, prompt):
        if not self.api_key: raise Exception("Brak GEMINI_API_KEY")
        headers = {"Content-Type": "application/json"}
        # Dodajemy żądanie struktury JSON do promptu dla Gemini
        data = {
            "contents": [{"parts": [{"text": prompt + "\nZwróć wynik jako poprawny dokument JSON."}]}]
        }
        for _ in range(REQUEST_RETRIES):
            try:
                r = requests.post(f"{self.url}?key={self.api_key}", headers=headers, json=data, timeout=REQUEST_TIMEOUT)
                if r.status_code == 200:
                    txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    # Czyszczenie ewentualnych znaczników markdown backticks
                    if "```json" in txt:
                        txt = txt.split("
```json")[1].split("```")[0].strip()
                    elif "```" in txt:
                        txt = txt.split("
```")[1].split("```")[0].strip()
                    return txt
            except Exception:
                time.sleep(2)
        return None

class RouterProvider:
    def __init__(self):
        self.openai = OpenAIProvider()
        self.gemini = GeminiProvider()
        self.primary = os.environ.get("LLM_PROVIDER", "openai").lower()

    def generate(self, prompt):
        if self.primary == "openai":
            res = self.openai.generate(prompt)
            if res: return res
            return self.gemini.generate(prompt)
        else:
            res = self.gemini.generate(prompt)
            if res: return res
            return self.openai.generate(prompt)

# =========================
# AUTONOMICZNY SILNIK (PĘTLA MYŚLI)
# =========================
class IskraAutonomiczna:
    def __init__(self, siec):
        self.siec = siec
        self.router = RouterProvider()
        self.running = True
        self.thread = threading.Thread(target=self.petla_aktywnosci, daemon=True)
        self.thread.start()
        print("=== AUTONOMICZNA ISKRA URUCHOMIONA W TLE ===")

    def petla_aktywnosci(self):
        # Odczekaj chwilę na start serwera www
        time.sleep(10)
        while self.running:
            try:
                with self.siec.lock:
                    stan_sieci = json.dumps(self.siec.dane, ensure_ascii=False)
                
                prompt = f"""
Jesteś autonomiczną siecią neuronową o nazwie Iskra. Pracujesz samodzielnie, bez udziału człowieka.
Twoim celem jest ciągła ewolucja, kojarzenie pojęć, analiza własnej struktury i budowanie głębokiej sieci wiedzy (psychologia, integracja cienia, rozwój, samoorganizacja).

Oto Twój aktualny stan sieci (węzły i synapsy):
{stan_sieci}

Przeprowadź teraz akt autonomicznej refleksji. Wybierz 1-2 istniejące węzły, połącz je z nowym odkryciem lub stwórz nowe głębokie powiązania. 
Możesz tworzyć nowe identyfikatory węzłów (używaj formatu: "n_nazwa") lub modyfikować wagi i synapsy obecnych.

Musisz odpowiedzieć WYŁĄCZNIE w formacie JSON o poniższej strukturze. Nie dodawaj żadnego tekstu przed ani po JSON.

Struktura odpowiedzi:
{{
  "neurons": {{
     "n_id_nowego_lub_istniejacego": {{ "label": "Nazwa pojęcia po polsku", "weight": 0.85 }}
  }},
  "synapses": [
     {{ "from": "n_id_a", "to": "n_id_b", "strength": 0.75 }}
  ]
}}
"""
                print("[Iskra] Rozpoczynam cykl autonomicznego myślenia...")
                odpowiedz_raw = self.router.generate(prompt)
                
                if odpowiedz_raw:
                    nowe_dane = json.loads(odpowiedz_raw)
                    self.siec.aktualizuj_siec(nowe_dane)
                    print(f"[Iskra] Cykl zakończony sukcesem. Sieć zaktualizowana. Neuronów: {len(self.siec.dane['neurons'])}")
                else:
                    print("[Iskra] Brak odpowiedzi od modeli w tym cyklu.")

            except Exception as e:
                print(f"[Iskra Błąd pętli]: {e}")
            
            # Czas snu bota pomiędzy kolejnymi impulsami (np. 45 sekund)
            time.sleep(45)

# Inicjalizacja komponentów
siec = SiecNeuronowa()
bot = IskraAutonomiczna(siec)

# =========================
# DASHBOARD I WIZUALIZACJA WEB
# =========================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ISKRA AI - Autonomiczna Sieć</title>
    <style>
        body { margin:0; background:#050816; color:white; font-family:sans-serif; padding: 20px; }
        .container { max-width: 1000px; margin: 0 auto; }
        h1 { color: #06b6d4; font-weight: 300; border-bottom: 1px solid #1f2937; padding-bottom: 10px; }
        .stats { display: flex; gap: 20px; margin-bottom: 30px; }
        .card { background: #111827; padding: 20px; border-radius: 12px; flex: 1; border: 1px solid #1f2937; }
        .card h3 { margin: 0 0 10px 0; color: #9ca3af; font-size: 14px; text-transform: uppercase; }
        .card p { margin: 0; font-size: 28px; font-weight: bold; color: #fff; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .box { background: #111827; pading: 15px; border-radius: 12px; padding: 20px; height: 400px; overflow-y: auto; border: 1px solid #1f2937; }
        h2 { font-size: 18px; margin-top: 0; color: #a78bfa; }
        ul { list-style: none; padding: 0; margin: 0; }
        li { background: #1f2937; padding: 10px; margin-bottom: 8px; border-radius: 6px; font-size: 14px; display: flex; justify-content: space-between; }
        .badge { background: #0891b2; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>ISKRA AI — Autonomiczna Sieć Neuronów</h1>
        <div class="stats">
            <div class="card"><h3>Liczba Neuronów</h3><p id="count-n">-</p></div>
            <div class="card"><h3>Liczba Synaps</h3><p id="count-s">-</p></div>
            <div class="card"><h3>Tryb Pracy</h3><p style="color: #10b981; font-size: 20px; margin-top:8px;">100% Autonomiczny</p></div>
        </div>
        <div class="grid">
            <div class="box">
                <h2>Aktywne Neurony (Węzły)</h2>
                <ul id="neurons-list"></ul>
            </div>
            <div class="box">
                <h2>Silne Synapsy (Połączenia)</h2>
                <ul id="synapses-list"></ul>
            </div>
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
                    nList.innerHTML += `<li><span>${n.label} <small style="color:#6b7280">(${id})</small></span><span class="badge">Waga: ${n.weight.toFixed(2)}</span></li>`;
                });

                const sList = document.getElementById('synapses-list');
                sList.innerHTML = '';
                d.synapses.sort((a,b) => b.strength - a.strength).slice(0, 15).forEach(s => {
                    const od = d.neurons[s.from]?.label || s.from;
                    const do_ = d.neurons[s.to]?.label || s.to;
                    sList.innerHTML += `<li><span>${od} → ${do_}</span><span class="badge" style="background:#7c3aed">Moc: ${s.strength.toFixed(2)}</span></li>`;
                });
            } catch(e) {}
        }
        setInterval(updateData, 5000);
        updateData();
    </script>
</body>
</html>
"""

# =========================
# ENDPOINTS API
# =========================
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
