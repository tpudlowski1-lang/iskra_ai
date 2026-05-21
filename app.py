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

from flask import Flask, request, jsonify, render_template_string
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# =========================
# KONFIG
# =========================

PORT = int(os.environ.get("PORT", 8080))

DATA_DIR = "/tmp/iskra_data"
os.makedirs(DATA_DIR, exist_ok=True)

PLIK_WIEDZY = os.path.join(DATA_DIR, "wiedza.json")

MAX_HISTORIA = 10
MAX_INPUT = 3000

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
# ZAPIS JSON
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
# PAMIĘĆ
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

            with open(
                PLIK_WIEDZY,
                "r",
                encoding="utf-8"
            ) as f:

                self.dane = json.load(f)

        except:
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

    def rozmiar(self):
        return len(self.dane)

# =========================
# ISKRA AI
# =========================

class IskraAI:

    def __init__(self):

        self.pamiec = Pamiec()

        self.historia = defaultdict(list)

        self.gemini_key = os.environ.get("GEMINI_API_KEY", "")

        print("=== ISKRA START ===")

        if self.gemini_key:
            print("✅ Gemini API aktywne")
        else:
            print("❌ Brak Gemini API")

    # =========================
    # GEMINI
    # =========================

    def pytaj_gemini(self, prompt):

        if not self.gemini_key:
            return "Brak aktywnego Gemini API."

        url = (
            "https://generativelanguage.googleapis.com/"
            "v1beta/models/gemini-1.5-flash:generateContent"
        )

        headers = {
            "Content-Type": "application/json"
        }

        data = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ]
        }

        try:

            r = requests.post(
                f"{url}?key={self.gemini_key}",
                headers=headers,
                json=data,
                timeout=30
            )

            if r.status_code != 200:

                print("Gemini error:", r.text)

                return "Błąd połączenia z Gemini."

            response = r.json()

            return (
                response["candidates"][0]
                ["content"]["parts"][0]["text"]
            )

        except Exception as e:

            print("Gemini wyjątek:", e)

            return "Błąd AI."

    # =========================
    # CHAT
    # =========================

    def chat(self, pytanie, session_id):

        historia = self.historia[session_id]

        context = ""

        for p, o in historia[-MAX_HISTORIA:]:

            context += f"""
Użytkownik:
{p}

Iskra:
{o}

"""

        prompt = f"""
Jesteś futurystyczną AI o nazwie Iskra.

Odpowiadaj po polsku.

Historia:
{context}

Nowe pytanie:
{pytanie}

Odpowiedź:
"""

        odpowiedz = self.pytaj_gemini(prompt)

        historia.append((pytanie, odpowiedz))

        self.pamiec.dodaj(
            pytanie,
            odpowiedz
        )

        return odpowiedz

# =========================
# INSTANCJA
# =========================

iskra = IskraAI()

# =========================
# HTML
# =========================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="pl">

<head>

<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>ISKRA AI</title>

<style>

@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&display=swap');

body{
    margin:0;
    background:#050816;
    color:white;
    font-family:'Orbitron',sans-serif;
    overflow:hidden;
}

.dashboard{
    display:grid;
    grid-template-columns:280px 1fr 320px;
    height:100vh;
    gap:20px;
    padding:20px;
    box-sizing:border-box;
}

.panel{
    background:rgba(10,15,35,0.8);
    border:1px solid rgba(0,255,255,0.2);
    border-radius:20px;
    box-shadow:
        0 0 20px rgba(0,255,255,0.15),
        inset 0 0 20px rgba(0,255,255,0.05);
    padding:20px;
    backdrop-filter:blur(10px);
}

.logo{
    text-align:center;
    font-size:42px;
    color:#ff4dff;
    text-shadow:
        0 0 10px #ff4dff,
        0 0 30px #ff4dff;
    margin-bottom:20px;
}

.subtitle{
    text-align:center;
    color:#00ffff;
    margin-bottom:25px;
}

.chat{
    display:flex;
    flex-direction:column;
    height:100%;
}

.chat-window{
    flex:1;
    overflow:auto;
    margin-bottom:20px;
}

.message-user{
    background:rgba(255,0,255,0.15);
    border:1px solid rgba(255,0,255,0.4);
    padding:15px;
    border-radius:15px;
    margin-bottom:20px;
    margin-left:80px;
}

.message-ai{
    background:rgba(0,255,255,0.08);
    border:1px solid rgba(0,255,255,0.3);
    padding:15px;
    border-radius:15px;
    margin-bottom:20px;
    margin-right:80px;
}

.chat-input{
    display:flex;
    gap:15px;
}

.chat-input input{
    flex:1;
    padding:18px;
    border:none;
    border-radius:15px;
    background:#0f172a;
    color:white;
    font-size:16px;
    outline:none;
}

.chat-input button{
    width:80px;
    border:none;
    border-radius:15px;
    background:linear-gradient(45deg,#00ffff,#ff00ff);
    color:white;
    font-size:20px;
    cursor:pointer;
}

.status-box{
    margin-bottom:20px;
    padding:20px;
    border-radius:20px;
    background:rgba(255,255,255,0.03);
    border:1px solid rgba(0,255,255,0.15);
    text-align:center;
}

.status-value{
    font-size:30px;
    color:#00ffff;
}

.status-label{
    color:#aaa;
}

</style>

</head>

<body>

<div class="dashboard">

    <div class="panel">

        <div class="logo">ISKRA</div>

        <div class="subtitle">
            NEURAL SYSTEM
        </div>

        <div class="status-box">
            <div class="status-value" id="ram">
                67%
            </div>

            <div class="status-label">
                PAMIĘĆ
            </div>
        </div>

        <div class="status-box">
            <div class="status-value" id="cpu">
                42%
            </div>

            <div class="status-label">
                CPU AI
            </div>
        </div>

        <div class="status-box">
            <div class="status-value">
                {{ wiedza }}
            </div>

            <div class="status-label">
                NEURONY
            </div>
        </div>

    </div>

    <div class="panel chat">

        <div class="chat-window" id="chatWindow">

            <div class="message-ai">
                Witaj. Jestem Iskra AI.
            </div>

        </div>

        <div class="chat-input">

            <input
                type="text"
                id="userInput"
                placeholder="Napisz wiadomość..."
            >

            <button onclick="sendMessage()">
                ➤
            </button>

        </div>

    </div>

    <div class="panel">

        <div class="status-box">
            <div class="status-value" id="evo">
                7.4
            </div>

            <div class="status-label">
                EWOLUCJA
            </div>
        </div>

        <div class="status-box">
            <div class="status-value">
                ONLINE
            </div>

            <div class="status-label">
                STATUS
            </div>
        </div>

    </div>

</div>

<script>

async function sendMessage(){

    const input = document.getElementById("userInput");

    const text = input.value.trim();

    if(!text) return;

    const chat = document.getElementById("chatWindow");

    chat.innerHTML += `
        <div class="message-user">
            ${text}
        </div>
    `;

    input.value = "";

    try{

        const response = await fetch('/api/chat',{

            method:'POST',

            headers:{
                'Content-Type':'application/json'
            },

            body:JSON.stringify({
                pytanie:text
            })
        });

        const data = await response.json();

        chat.innerHTML += `
            <div class="message-ai">
                ${data.odpowiedz}
            </div>
        `;

        chat.scrollTop = chat.scrollHeight;

    }catch(e){

        chat.innerHTML += `
            <div class="message-ai">
                Błąd połączenia.
            </div>
        `;
    }
}

document.addEventListener("keypress",function(e){

    if(e.key === "Enter"){
        sendMessage();
    }

});

function randomize(){

    document.getElementById("ram").innerText =
        Math.floor(Math.random()*40+40)+"%";

    document.getElementById("cpu").innerText =
        Math.floor(Math.random()*50+20)+"%";

    document.getElementById("evo").innerText =
        (Math.random()*10).toFixed(2);
}

setInterval(randomize,2000);

</script>

</body>
</html>
"""

# =========================
# ROUTES
# =========================

@app.route('/')
def index():

    return render_template_string(
        DASHBOARD_HTML,
        wiedza=iskra.pamiec.rozmiar()
    )

@app.route('/api/chat', methods=['POST'])
@limiter.limit("10/minute")
def api_chat():

    data = request.get_json()

    if not data:

        return jsonify({
            "odpowiedz": "Brak danych"
        })

    pytanie = data.get("pytanie", "").strip()

    if not pytanie:

        return jsonify({
            "odpowiedz": "Puste pytanie"
        })

    if len(pytanie) > MAX_INPUT:

        return jsonify({
            "odpowiedz": "Za długie pytanie"
        })

    session_id = request.headers.get(
        "X-Session-ID",
        str(uuid.uuid4())
    )

    odpowiedz = iskra.chat(
        pytanie,
        session_id
    )

    return jsonify({
        "odpowiedz": odpowiedz
    })

@app.route('/status')
def status():

    return jsonify({
        "pamiec": iskra.pamiec.rozmiar(),
        "users": len(iskra.historia)
    })

# =========================
# START
# =========================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=PORT
    )