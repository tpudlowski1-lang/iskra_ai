#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import uuid
import threading
import tempfile
import shutil
from collections import defaultdict

import requests

from flask import (
    Flask,
    request,
    jsonify,
    render_template_string
)

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# =========================
# KONFIGURACJA
# =========================

PORT = int(os.environ.get("PORT", 8080))
DATA_DIR = "/tmp/iskra_data"
os.makedirs(DATA_DIR, exist_ok=True)

PLIK_WIEDZY = os.path.join(DATA_DIR, "wiedza.json")

MAX_HISTORIA = 10
MAX_INPUT = 3000
MAX_SESSIONS = 1000

REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 3

# =========================
# DIAGNOSTYKA STARTU
# =========================
print("=== START ISKRY (CLOUD - DEEPSEEK VIA ANTHROPIC ENDPOINT) ===")
print(f"PORT: {PORT}")
print(f"Katalog danych: {DATA_DIR}")
print(f"DEEPSEEK_API_KEY: {'✔️' if os.environ.get('DEEPSEEK_API_KEY') else '❌'}")

# =========================
# FLASK
# =========================

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["60 per minute"]
)

# =========================
# ATOMOWY ZAPIS JSON
# =========================

def atomic_save(path, data):
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        encoding="utf-8"
    ) as tmp:
        json.dump(
            data,
            tmp,
            ensure_ascii=False,
            indent=4
        )
        temp_name = tmp.name

    shutil.move(temp_name, path)

# =========================
# PAMIĘĆ LOKALNA
# =========================

class Pamiec:
    def __init__(self):
        self.lock = threading.RLock()
        self.dane = {}
        self.laduj()

    def laduj(self):
        if not os.path.exists(PLIK_WIEDZY):
            return
        try:
            with open(PLIK_WIEDZY, "r", encoding="utf-8") as f:
                self.dane = json.load(f)
        except Exception:
            self.dane = {}

    def zapisz(self):
        with self.lock:
            atomic_save(PLIK_WIEDZY, self.dane)

    def dodaj(self, pytanie, odpowiedz):
        with self.lock:
            uid = str(uuid.uuid4())
            self.dane[uid] = {
                "czas": time.time(),
                "pytanie": pytanie,
                "odpowiedz": odpowiedz
            }
            self.zapisz()

    def szukaj_fallback(self, pytanie):
        """Proste wyszukiwanie w lokalnej pamięci w razie awarii API"""
        with self.lock:
            if not self.dane:
                return None
            p_lower = pytanie.lower()
            for uid, wpis in self.dane.items():
                if wpis.get("pytanie", "").lower() in p_lower or p_lower in wpis.get("pytanie", "").lower():
                    return wpis.get("odpowiedz")
            # Jeśli brak idealnego dopasowania, zwróć ostatnią zapisaną odpowiedź
            ostatni_id = max(self.dane.keys(), key=lambda k: self.dane[k]["czas"])
            return self.dane[ostatni_id].get("odpowiedz")

    def rozmiar(self):
        return len(self.dane)

# =========================
# PROVIDER DEEPSEEK (ANTHROPIC-COMPATIBLE)
# =========================


class DeepSeekProvider:
    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        # Najpierw spróbujemy standardowego API (nie anthropic)
        self.url = "https://api.deepseek.com/v1/chat/completions"
        self.model = "deepseek-chat"

    def generate(self, prompt):
        if not self.api_key:
            raise Exception("Brak DEEPSEEK_API_KEY")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5,
            "stream": False
        }

        print(f"[DeepSeek] Wywołanie URL: {self.url}")
        print(f"[DeepSeek] Model: {self.model}")
        print(f"[DeepSeek] Prompt: {prompt[:100]}...")

        try:
            r = requests.post(self.url, headers=headers, json=data, timeout=30)
            print(f"[DeepSeek] Status: {r.status_code}")
            print(f"[DeepSeek] Response: {r.text[:200]}")

            if r.status_code != 200:
                raise Exception(f"HTTP {r.status_code}: {r.text}")

            response = r.json()
            return response["choices"][0]["message"]["content"]

        except Exception as e:
            print(f"[DeepSeek] Błąd: {e}")
            raise
# =========================
# RDZEŃ REPREZENTACJI AI
# =========================

class IskraAI:
    def __init__(self):
        self.pamiec = Pamiec()
        self.historia = defaultdict(list)
        self.provider = DeepSeekProvider()
        print("=== ISKRA SFORMOWANA (tryb Anthropic-compatible) ===")

    def cleanup_sessions(self):
        while len(self.historia) > MAX_SESSIONS:
            oldest = next(iter(self.historia))
            del self.historia[oldest]

    def build_prompt(self, pytanie, context):
        return f"""SYSTEM:
Jesteś futurystyczną, suwerenną sztuczną inteligencją o nazwie Iskra.
Odpowiadaj po polsku, w sposób zwięzły, autentyczny, logiczny i bezpośredni.

====================
HISTORIA OSTATNIEJ ROZMOWY:
====================
{context}

====================
ZAPYTANIE UŻYTKOWNIKA:
====================
{pytanie}

====================
ODPOWIEDŹ ISKRY:
"""

    def chat(self, pytanie, session_id):
        self.cleanup_sessions()
        historia = self.historia[session_id]

        context = ""
        for p, o in historia[-MAX_HISTORIA:]:
            context += f"Użytkownik: {p}\nIskra: {o}\n\n"

        prompt = self.build_prompt(pytanie, context)

        try:
            odpowiedz = self.provider.generate(prompt)
            self.pamiec.dodaj(pytanie, odpowiedz)
        except Exception as e:
            print(f"[SYSTEM CRITICAL] Błąd zewnętrznego API: {e}")
            odpowiedz_lokalna = self.pamiec.szukaj_fallback(pytanie)
            if odpowiedz_lokalna:
                odpowiedz = f"(Tryb Offline - Awaria API. Odpowiedź z bazy autonomicznej):\n{odpowiedz_lokalna}"
            else:
                odpowiedz = (
                    "System AI offline. Brak połączenia z zewnętrznym dostawcą DeepSeek "
                    "oraz brak wystarczających danych w bazie neuronów do wygenerowania odpowiedzi autonomicznej.\n\n"
                    "Upewnij się, że dodałeś prawidłowy klucz DEEPSEEK_API_KEY na Renderze."
                )

        historia.append((pytanie, odpowiedz))
        return odpowiedz

    # =========================
    # AUTONOMICZNE UCZENIE SIĘ (WĄTEK TŁA)
    # =========================
    def autonomiczne_uczenie(self):
        """Co godzinę pobiera losową stronę z Wikipedii i zapamiętuje."""
        while True:
            try:
                url = "https://pl.wikipedia.org/api/rest_v1/page/random/summary"
                resp = requests.get(url, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    tytul = data.get('title', 'brak tytułu')
                    streszczenie = data.get('extract', 'brak treści')
                    prompt = f"""Oto nowa informacja z Wikipedii:
Tytuł: {tytul}
Treść: {streszczenie}

Przeczytaj i zapamiętaj najważniejsze fakty. Odpowiedz krótko: "Zapamiętałam: ..." (maksymalnie 2 zdania)."""
                    odpowiedz = self.provider.generate(prompt)
                    self.pamiec.dodaj(f"[AUTO] {tytul}", odpowiedz)
                    print(f"[AUTONOMIA] Zapamiętałam: {tytul}")
                else:
                    print("[AUTONOMIA] Błąd pobierania Wikipedii")
            except Exception as e:
                print(f"[AUTONOMIA] Błąd: {e}")
            time.sleep(3600)  # 1 godzina

# =========================
# INSTANCJA ISKRY I WĄTEK AUTONOMICZNY
# =========================

iskra = IskraAI()

thread_auto = threading.Thread(target=iskra.autonomiczne_uczenie, daemon=True)
thread_auto.start()
print("✅ Autonomiczne uczenie się uruchomione (co godzinę)")

# =========================
# INTERFEJS FRONT-END (DASHBOARD)
# =========================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ISKRA AI - NEURAL SYSTEM</title>
    <style>
        body {
            margin: 0;
            background: #050816;
            color: white;
            font-family: Arial, sans-serif;
            overflow: hidden;
        }
        .dashboard {
            display: flex;
            height: 100vh;
            padding: 20px;
            box-sizing: border-box;
            gap: 20px;
        }
        .panel-side {
            width: 250px;
            display: flex;
            flex-direction: column;
            gap: 15px;
        }
        .panel-main {
            flex: 1;
            display: flex;
            flex-direction: column;
            height: 100%;
        }
        .card {
            background: rgba(17, 24, 39, 0.8);
            border: 1px solid #14b8a6;
            border-radius: 15px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 0 15px rgba(20, 184, 166, 0.2);
        }
        .card h3 { margin: 0 0 10px 0; font-size: 14px; color: #14b8a6; text-transform: uppercase; letter-spacing: 1px;}
        .card .value { font-size: 28px; font-weight: bold; color: #fff; text-shadow: 0 0 10px rgba(255,255,255,0.3); }
        .logo-title {
            font-size: 24px;
            font-weight: bold;
            color: #ec4899;
            text-shadow: 0 0 10px rgba(236, 72, 153, 0.6);
            margin-bottom: 5px;
            text-transform: uppercase;
            letter-spacing: 2px;
        }
        .sub-title { font-size: 11px; color: #06b6d4; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 20px; }
        .chat-window {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: #0b0f19;
            border: 1px solid rgba(6, 182, 212, 0.3);
            border-radius: 20px;
            margin-bottom: 20px;
            box-shadow: inset 0 0 20px rgba(0,0,0,0.6);
        }
        .message-user {
            background: rgba(124, 58, 237, 0.3);
            border: 1px solid #7c3aed;
            padding: 12px 18px;
            border-radius: 15px 15px 0 15px;
            margin-bottom: 15px;
            margin-left: 60px;
            text-align: right;
            word-wrap: break-word;
        }
        .message-ai {
            background: rgba(8, 145, 178, 0.2);
            border: 1px solid #0891b2;
            padding: 12px 18px;
            border-radius: 15px 15px 15px 0;
            margin-bottom: 15px;
            margin-right: 60px;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .chat-input {
            display: flex;
            gap: 10px;
        }
        .chat-input input {
            flex: 1;
            padding: 15px;
            border: 1px solid rgba(6, 182, 212, 0.5);
            border-radius: 15px;
            font-size: 16px;
            background: #111827;
            color: white;
            outline: none;
            box-shadow: 0 0 10px rgba(6, 182, 212, 0.1);
        }
        .chat-input input:focus {
            border-color: #06b6d4;
            box-shadow: 0 0 15px rgba(6, 182, 212, 0.4);
        }
        .chat-input button {
            width: 70px;
            border: none;
            border-radius: 15px;
            background: linear-gradient(135deg, #06b6d4, #ec4899);
            color: white;
            font-size: 18px;
            cursor: pointer;
            box-shadow: 0 0 15px rgba(6, 182, 212, 0.3);
            transition: transform 0.1s;
        }
        .chat-input button:hover {
            transform: scale(1.03);
        }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: #050816; }
        ::-webkit-scrollbar-thumb { background: #1f2937; border-radius: 10px; }
        ::-webkit-scrollbar-thumb:hover { background: #06b6d4; }
        
        @media(max-width: 768px) {
            .dashboard { flex-direction: column; overflow: auto; }
            .panel-side { width: 100%; flex-direction: row; flex-wrap: wrap; }
            .card { flex: 1; min-width: 120px; padding: 10px; }
            .panel-main { height: calc(100vh - 180px); }
        }
    </style>
</head>
<body>

<div class="dashboard">
    <div class="panel-side">
        <div style="text-align: center; margin-top: 10px;">
            <div class="logo-title">Iskra</div>
            <div class="sub-title">Neural System</div>
        </div>
        <div class="card">
            <h3>Baza Neuronów</h3>
            <div class="value" id="valPamiec">{{ pamiec_size }}</div>
        </div>
        <div class="card">
            <h3>Silnik Główny</h3>
            <div class="value" style="font-size: 20px; color: #ec4899;">DEEPSEEK (Anthropic)</div>
        </div>
        <div class="card">
            <h3>Status</h3>
            <div class="value" style="font-size: 22px; color: #10b981;">ONLINE</div>
        </div>
    </div>

    <div class="panel-main">
        <div class="chat-window" id="chatWindow">
            <div class="message-ai">Witaj. Jestem Iskra AI. Rdzeń systemu używa kompatybilnego z Anthropic endpointu DeepSeek. Jakie masz wytyczne?</div>
        </div>

        <div class="chat-input">
            <input type="text" id="userInput" placeholder="Napisz wiadomość do systemu..." autofocus>
            <button onclick="sendMessage()">➤</button>
        </div>
    </div>
</div>

<script>
function getSessionId(){
    let sid = localStorage.getItem('iskra_session_id');
    if(!sid){
        sid = Date.now().toString(36) + Math.random().toString(36);
        localStorage.setItem('iskra_session_id', sid);
    }
    return sid;
}

async function sendMessage(){
    const input = document.getElementById("userInput");
    const text = input.value.trim();
    if(!text) return;

    const chat = document.getElementById("chatWindow");
    
    const userDiv = document.createElement("div");
    userDiv.className = "message-user";
    userDiv.textContent = text;
    chat.appendChild(userDiv);
    input.value = "";

    const aiDiv = document.createElement("div");
    aiDiv.className = "message-ai";
    aiDiv.textContent = "Analizuję strumień danych...";
    chat.appendChild(aiDiv);
    chat.scrollTop = chat.scrollHeight;

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-ID': getSessionId()
            },
            body: JSON.stringify({ pytanie: text })
        });
        const data = await response.json();
        aiDiv.textContent = data.odpowiedz;
        
        const statusRes = await fetch('/status');
        const statusData = await statusRes.json();
        document.getElementById("valPamiec").textContent = statusData.pamiec;

    } catch(e) {
        aiDiv.textContent = "System offline. Krytyczny błąd połączenia serwera.";
        aiDiv.style.borderColor = "#ef4444";
    }
    chat.scrollTop = chat.scrollHeight;
}

document.getElementById("userInput").addEventListener("keypress", function(e){
    if(e.key === "Enter") sendMessage();
});
</script>

</body>
</html>
"""

# =========================
# API ROUTES
# =========================

@app.route('/')
def index():
    return render_template_string(
        DASHBOARD_HTML,
        pamiec_size=iskra.pamiec.rozmiar()
    )

@app.route('/api/chat', methods=['POST'])
@limiter.limit("20/minute")
def api_chat():
    data = request.get_json()
    if not data:
        return jsonify({"odpowiedz": "Brak danych wejściowych."})

    pytanie = data.get("pytanie", "").strip()
    if not pytanie:
        return jsonify({"odpowiedz": "Puste zapytanie."})

    if len(pytanie) > MAX_INPUT:
        return jsonify({"odpowiedz": "Za długi ciąg wejściowy (maksymalnie 3000 znaków)."})

    session_id = request.headers.get(
        "X-Session-ID",
        str(uuid.uuid4())
    )

    odpowiedz = iskra.chat(pytanie, session_id)
    return jsonify({"odpowiedz": odpowiedz})

@app.route('/status')
def status():
    return jsonify({
        "pamiec": iskra.pamiec.rozmiar(),
        "users": len(iskra.historia),
        "provider": "deepseek-anthropic-endpoint"
    })

@app.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "provider": "deepseek-anthropic-endpoint"
    })

@app.route('/keep-alive')
def keep_alive():
    return "Iskra żyje", 200

# =========================
# START SERWERA
# =========================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=PORT,
        threaded=True
    )
