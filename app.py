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
# KONFIGURACJA I ŚCIEŻKI
# =========================
PORT = int(os.environ.get("PORT", 8080))
# Zmiana na katalog główny aplikacji, aby uniknąć problemów z czyszczeniem /tmp na Renderze
DATA_DIR = os.path.abspath(".") 
PLIK_SIECI = os.path.join(DATA_DIR, "wiedza.json")
REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 3

app = Flask(__name__)

def atomic_save(path, data):
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=DATA_DIR) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=4)
            temp_name = tmp.name
        shutil.move(temp_name, path)
        print(f"[SIEC] Baza danych {os.path.basename(path)} zaktualizowana pomyślnie.")
    except Exception as e:
        print(f"[BŁĄD KRYTYCZNY ZAPISU]: {e}")

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
            print("[SIEC] Plik bazy danych nie istnieje. Inicjalizacja archetypów...")
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
            print(f"[SIEC] Wczytano istniejącą sieć: {len(self.dane['neurons'])} neuronów.")
        except Exception as e:
            print(f"[SIEC] Błąd ładowania pliku, tworzenie struktury awaryjnej: {e}")

    def zapisz(self):
        with self.lock:
            atomic_save(PLIK_SIECI, self.dane)

    def aktualizuj_siec(self, nowa_struktura):
        with self.lock:
            if not nowa_struktura or not isinstance(nowa_struktura, dict):
                print("[SIEC] Odebrano nieprawidłową strukturę do aktualizacji.")
                return

            # Aktualizacja neuronów
            for k, v in nowa_struktura.get("neurons", {}).items():
                if k not in self.dane["neurons"]:
                    self.dane["neurons"][k] = {
                        "label": v.get("label", "Nieznany"),
                        "weight": min(max(float(v.get("weight", 0.5)), 0.0), 1.0),
                        "created": time.time()
                    }
                    print(f"[SIEC] ZBUDOWANO NOWY NEURON: [{k}] -> '{v.get('label')}'")
                else:
                    stara_waga = self.dane["neurons"][k]["weight"]
                    nowa_waga = float(v.get("weight", stara_waga))
                    self.dane["neurons"][k]["weight"] = min(max(stara_waga * 0.7 + nowa_waga * 0.3, 0.0), 1.0)

            # Aktualizacja synaps
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
                        print(f"[SIEC] Nowe połączenie: {f_id} -> {t_id} ({str_val})")
            self.zapisz()

# =========================
# PROVIDERY LLM
# =========================
class DeepSeekProvider:
    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.url = "https://api.deepseek.com/v1/chat/completions"

    def generate(self, prompt):
        if not self.api_key: return None
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "response_format": {"type": "json_object"}
        }
        try:
            r = requests.post(self.url, headers=headers, json=data, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200: return r.json()["choices"][0]["message"]["content"]
            print(f"[DEBUG DEEPSEEK] Status: {r.status_code}, Odpowiedź: {r.text}")
        except Exception as e: print(f"[DEBUG DEEPSEEK] Wyjątek: {e}")
        return None

class OpenAIProvider:
    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        self.url = "https://api.openai.com/v1/chat/completions"
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def generate(self, prompt):
        if not self.api_key: return None
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "response_format": {"type": "json_object"}
        }
        try:
            r = requests.post(self.url, headers=headers, json=data, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200: return r.json()["choices"][0]["message"]["content"]
        except Exception as e: print(f"[DEBUG OPENAI] Wyjątek: {e}")
        return None

class GeminiProvider:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    def generate(self, prompt):
        if not self.api_key: return None
        headers = {"Content-Type": "application/json"}
        data = {"contents": [{"parts": [{"text": prompt + " ODPOWIEDZ WYŁĄCZNIE CZYSTYM JSONEM."}]}]}
        try:
            r = requests.post(f"{self.url}?key={self.api_key}", headers=headers, json=data, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200: return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e: print(f"[DEBUG GEMINI] Wyjątek: {e}")
        return None

class RouterProvider:
    def __init__(self):
        self.openai = OpenAIProvider()
        self.gemini = GeminiProvider()
        self.deepseek = DeepSeekProvider()
        self.primary = os.environ.get("LLM_PROVIDER", "openai").lower()

    def clean_json(self, text):
        if not text: return None
        text = text.strip()
        # Wyciąganie JSON-a w przypadku gdy model użyje znaczników markdown ```json ... ```
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match: return match.group(0)
        return text

    def generate(self, prompt):
        providers = {
            "openai": self.openai,
            "deepseek": self.deepseek,
            "gemini": self.gemini
        }
        
        # Ustalenie kolejności (główny dostawca na początek)
        order = [self.primary] + [k for k in providers.keys() if k != self.primary]
        
        for p_name in order:
            provider = providers.get(p_name)
            if provider and provider.api_key:
                print(f"[ISKRA] Próba generowania przez dostawcę: {p_name}...")
                res = provider.generate(prompt)
                if res:
                    return self.clean_json(res)
                print(f"[OSTRZEŻENIE] Dostawca {p_name} zwrócił pustą odpowiedź lub wystąpił błąd.")
        
        print("[CRITICAL] Wszyscy dostępni dostawcy LLM zawiedli lub brakuje kluczy API!")
        return None

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

    def petla_aktywnosci(self):
        print("[ENGINE] Oczekiwanie 5 sekund na stabilizację serwera...")
        time.sleep(5)
        print("[ENGINE] Autonomiczna pętla Iskry rozpoczęła działanie.")
        
        while self.running:
            try:
                with self.siec.lock:
                    stan_sieci = json.dumps(self.siec.dane, ensure_ascii=False)
                
                print("[ISKRA] Rozpoczynam nowy cykl analizy sieci pojęciowej...")
                prompt = f"""
Jesteś autonomiczną siecią neuronową Iskra. Analizujesz strukturę swoich pojęć.
Twoja tematyka: psychologia analityczna, integracja cienia, ludzkie popędy, mechanizmy obronne, archetypy Carla Junga.
Aktualny stan sieci: {stan_sieci}

Zadanie: Wygeneruj dokładnie 1 lub 2 nowe pojęcia jako neurony (nadaj im unikalne klucze, np. "n_projekcja", "n_ego", "n_persona", "n_animus") i połącz je logicznymi synapsami ze starymi lub nowymi neuronami. Możesz też zmienić wagi obecnych neuronów.
Odpowiedz wyłącznie w poprawnym formacie JSON, bez żadnego dodatkowego tekstu ani komentarza przed/po:
{{
  "neurons": {{
    "n_nowy_id": {{ "label": "Nazwa Pojęcia", "weight": 0.75 }}
  }},
  "synapses": [
    {{ "from": "n_swiadomosc", "to": "n_nowy_id", "strength": 0.60 }}
  ]
}}
"""
                odpowiedz_json = self.router.generate(prompt)
                if odpowiedz_json:
                    nowe_dane = json.loads(odpowiedz_json)
                    self.siec.aktualizuj_siec(nowe_dane)
                else:
                    print("[ISKRA] Pętla pominięta w tym cyklu z powodu braku odpowiedzi z AI.")
            except Exception as e:
                print(f"[!!! POWAŻNY BŁĄD BOTA !!!]: {e}")
            
            print("[ISKRA] Cykl zakończony. Zasypiam na 30 sekund.")
            time.sleep(30)

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
    <title>ISKRA AI</title>
    <style>
        body { margin:0; background:#050816; color:white; font-family:sans-serif; padding: 20px; }
        .container { max-width: 1000px; margin: 0 auto; }
        h1 { color: #06b6d4; font-weight: 300; border-bottom: 1px solid #1f2937; padding-bottom: 10px; }
        .stats { display: flex; gap: 20px; margin-bottom: 30px; }
        .card { background: #111827; padding: 20px; border-radius: 12px; flex: 1; border: 1px solid #1f2937; }
        .card h3 { margin: 0 0 10px 0; color: #9ca3af; font-size: 14px; text-transform: uppercase; }
        .card p { margin: 0; font-size: 28px; font-weight: bold; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .box { background: #111827; border-radius: 12px; padding: 20px; height: 400px; overflow-y: auto; border: 1px solid #1f2937; }
        h2 { font-size: 18px; margin-top: 0; color: #a78bfa; }
        ul { list-style: none; padding: 0; margin: 0; }
        li { background: #1f2937; padding: 10px; margin-bottom: 8px; border-radius: 6px; font-size: 14px; display: flex; justify-content: space-between; }
        .badge { background: #0891b2; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>ISKRA AI — Sieć Neuronów (V2)</h1>
        <div class="stats">
            <div class="card"><h3>Neurony</h3><p id="count-n">-</p></div>
            <div class="card"><h3>Synapsy</h3><p id="count-s">-</p></div>
            <div class="card"><h3>Tryb</h3><p style="color: #10b981; font-size: 20px; margin-top:8px;">Autonomiczny</p></div>
        </div>
        <div class="grid">
            <div class="box"><h2>Węzły sieci (Pojęcia)</h2><ul id="neurons-list"></ul></div>
            <div class="box"><h2>Połączenia (Synapsy)</h2><ul id="synapses-list"></ul></div>
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
                d.synapses.sort((a,b) => b.strength - a.strength).slice(0, 20).forEach(s => {
                    const od = d.neurons[s.from]?.label || s.from;
                    const do_ = d.neurons[s.to]?.label || s.to;
                    sList.innerHTML += `<li><span>${od} → ${do_}</span><span class="badge" style="background:#7c3aed">Moc: ${s.strength.toFixed(2)}</span></li>`;
                });
            } catch(e) {}
        }
        setInterval(updateData, 4000);
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
