#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ISKRA AI v6.4 NEON EDITION
Render.com READY
"""

import os
import json
import time
import uuid
import hashlib
import threading
import tempfile
import shutil
from collections import defaultdict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from flask import Flask, request, jsonify, render_template_string
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from markupsafe import escape

# =========================
# KONFIG
# =========================

PORT = int(os.environ.get("PORT", 8080))
ENV = os.environ.get("ENV", "production")

DATA_DIR = os.environ.get("DATA_DIR", "/tmp/iskra_data")
os.makedirs(DATA_DIR, exist_ok=True)

PLIK_WIEDZY = os.path.join(DATA_DIR, "wiedza.json")
PLIK_FEEDBACK = os.path.join(DATA_DIR, "feedback.json")

API_TOKEN = os.environ.get("API_TOKEN", "")

MAX_HISTORIA = 15
MAX_ODPOWIEDZ = 2500
MAX_INPUT = 4000

# =========================
# APP
# =========================

app = Flask(__name__)

app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["60 per minute"]
)

# =========================
# HELPERY
# =========================

def atomic_save(path, data):

    directory = os.path.dirname(path)

    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=directory,
        encoding="utf-8"
    ) as tmp:

        json.dump(
            data,
            tmp,
            indent=4,
            ensure_ascii=False
        )

        temp_name = tmp.name

    shutil.move(temp_name, path)

def create_session():

    session = requests.Session()

    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )

    adapter = HTTPAdapter(max_retries=retries)

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session

# =========================
# LLM
# =========================

class GeminiConnector:

    def __init__(self):

        self.api_key = os.environ.get("GEMINI_API_KEY", "")

        self.url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            "models/gemini-1.5-flash:generateContent"
        )

        self.session = create_session()

    def available(self):
        return bool(self.api_key)

    def ask(self, prompt):

        if not self.api_key:
            return None

        headers = {
            "Content-Type": "application/json"
        }

        payload = {
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

            r = self.session.post(
                f"{self.url}?key={self.api_key}",
                json=payload,
                headers=headers,
                timeout=30
            )

            if r.status_code == 200:

                data = r.json()

                return (
                    data["candidates"][0]
                    ["content"]["parts"][0]["text"]
                )

            print("Gemini error:", r.status_code)
            return None

        except Exception as e:

            print("Gemini exception:", e)
            return None

# =========================
# PAMIĘĆ
# =========================

class Memory:

    def __init__(self, file_path):

        self.file_path = file_path
        self.data = {}
        self.lock = threading.RLock()

        self.load()

    def load(self):

        if not os.path.exists(self.file_path):
            return

        try:

            with open(
                self.file_path,
                "r",
                encoding="utf-8"
            ) as f:

                self.data = json.load(f)

        except Exception as e:

            print("Memory load error:", e)

    def save(self):

        with self.lock:
            atomic_save(self.file_path, self.data)

    def add(self, question, answer):

        key = hashlib.md5(
            question.lower().encode()
        ).hexdigest()

        with self.lock:

            self.data[key] = {
                "question": question[:300],
                "answer": answer[:MAX_ODPOWIEDZ],
                "time": time.time()
            }

            if len(self.data) > 2000:

                oldest = min(
                    self.data.keys(),
                    key=lambda k: self.data[k]["time"]
                )

                del self.data[oldest]

            self.save()

    def size(self):
        return len(self.data)

# =========================
# FEEDBACK
# =========================

class Feedback:

    def __init__(self, file_path):

        self.file_path = file_path
        self.data = []
        self.lock = threading.RLock()

        self.load()

    def load(self):

        if not os.path.exists(self.file_path):
            return

        try:

            with open(
                self.file_path,
                "r",
                encoding="utf-8"
            ) as f:

                self.data = json.load(f)

        except Exception as e:

            print("Feedback load error:", e)

    def save(self):

        with self.lock:
            atomic_save(
                self.file_path,
                self.data[-1000:]
            )

    def add(self, question, answer, rating):

        with self.lock:

            self.data.append({
                "question": question[:300],
                "answer": answer[:300],
                "rating": rating,
                "time": time.time()
            })

            self.save()

    def average(self):

        ratings = [
            x["rating"]
            for x in self.data
            if isinstance(x.get("rating"), (int, float))
        ]

        if not ratings:
            return 0

        return round(sum(ratings) / len(ratings), 2)

# =========================
# ISKRA AI
# =========================

class IskraAI:

    def __init__(self):

        self.gemini = GeminiConnector()

        self.memory = Memory(PLIK_WIEDZY)
        self.feedback = Feedback(PLIK_FEEDBACK)

        self.history = defaultdict(list)

    def generate_prompt(self, question, session_id):

        history = self.history.get(session_id, [])

        history_text = ""

        if history:

            last = history[-MAX_HISTORIA:]

            history_text = "\n".join([
                f"Użytkownik: {q}\nIskra: {a}"
                for q, a in last
            ])

        return f"""
Jesteś Iskra AI.

Odpowiadaj po polsku.
Bądź inteligentna, rzeczowa i pomocna.

Historia:
{history_text}

Pytanie:
{question}

Odpowiedź:
"""

    def ask(self, question, session_id):

        prompt = self.generate_prompt(
            question,
            session_id
        )

        answer = self.gemini.ask(prompt)

        if not answer:
            answer = (
                "❌ Brak odpowiedzi z modelu AI. "
                "Sprawdź GEMINI_API_KEY."
            )

        answer = answer[:MAX_ODPOWIEDZ]

        self.memory.add(question, answer)

        self.history[session_id].append(
            (question, answer)
        )

        if len(self.history[session_id]) > MAX_HISTORIA:
            self.history[session_id].pop(0)

        return answer

iskra = IskraAI()

# =========================
# SECURITY HEADERS
# =========================

@app.after_request
def secure_headers(response):

    response.headers["X-Content-Type-Options"] = "nosniff"

    response.headers["X-Frame-Options"] = "DENY"

    response.headers["Referrer-Policy"] = "no-referrer"

    response.headers["Content-Security-Policy"] = (
        "default-src 'self' 'unsafe-inline' "
        "https://cdn.plot.ly "
        "https://fonts.googleapis.com "
        "https://fonts.gstatic.com;"
        "style-src 'self' 'unsafe-inline' "
        "https://fonts.googleapis.com;"
        "font-src 'self' "
        "https://fonts.gstatic.com data:;"
    )

    return response

# =========================
# TOKEN
# =========================

def auth_required():

    if not API_TOKEN:
        return None

    auth = request.headers.get(
        "Authorization",
        ""
    )

    if auth != f"Bearer {API_TOKEN}":

        return jsonify({
            "error": "Nieautoryzowany dostęp"
        }), 401

    return None

# =========================
# DASHBOARD
# =========================

DASHBOARD_HTML = """

<!DOCTYPE html>
<html lang="pl">

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width, initial-scale=1.0">

<title>ISKRA AI</title>

<style>

@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&display=swap');

body{
    margin:0;
    background:#050816;
    color:white;
    font-family:'Orbitron',sans-serif;
    overflow:auto;
}

.dashboard{
    display:grid;
    grid-template-columns:280px 1fr 320px;
    min-height:100vh;
    gap:20px;
    padding:20px;
    box-sizing:border-box;
}

.panel{
    background:rgba(10,15,35,0.85);
    border:1px solid rgba(0,255,255,0.2);
    border-radius:20px;
    padding:20px;

    box-shadow:
        0 0 20px rgba(0,255,255,0.15),
        inset 0 0 20px rgba(0,255,255,0.05);
}

.logo{
    font-size:42px;
    text-align:center;
    color:#ff00ff;

    text-shadow:
        0 0 10px #ff00ff,
        0 0 30px #ff00ff;
}

.subtitle{
    text-align:center;
    color:#00ffff;
    margin-bottom:30px;
}

.gauge{
    margin-bottom:30px;
}

.gauge-title{
    color:#00ffff;
    margin-bottom:10px;
}

.gauge-circle{
    width:180px;
    height:180px;
    border-radius:50%;
    margin:auto;

    background:
        radial-gradient(circle at center,#09111f 50%,transparent 51%),
        conic-gradient(
            #00ffff 0deg,
            #00ffff 240deg,
            #1a1f3d 240deg
        );

    position:relative;

    box-shadow:
        0 0 20px rgba(0,255,255,0.3),
        inset 0 0 20px rgba(0,255,255,0.2);
}

.gauge-inner{
    position:absolute;
    top:50%;
    left:50%;
    transform:translate(-50%,-50%);
    text-align:center;
}

.gauge-value{
    font-size:34px;
    color:#00ffff;
    text-shadow:0 0 15px #00ffff;
}

.chat{
    display:flex;
    flex-direction:column;
}

.chat-window{
    flex:1;
    overflow:auto;
    min-height:600px;
    max-height:70vh;
    margin-bottom:20px;
}

.message-user{
    background:rgba(255,0,255,0.15);
    border:1px solid rgba(255,0,255,0.3);

    padding:15px;
    border-radius:15px;

    margin-bottom:15px;
    margin-left:60px;
}

.message-ai{
    background:rgba(0,255,255,0.08);
    border:1px solid rgba(0,255,255,0.2);

    padding:15px;
    border-radius:15px;

    margin-bottom:15px;
    margin-right:60px;
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
    width:90px;
    border:none;
    border-radius:15px;

    background:linear-gradient(
        45deg,
        #00ffff,
        #ff00ff
    );

    color:white;
    font-size:22px;
    cursor:pointer;
}

.status-box{
    background:rgba(255,255,255,0.03);

    border:1px solid rgba(0,255,255,0.15);

    border-radius:15px;
    padding:20px;

    margin-bottom:20px;
}

.status-value{
    font-size:28px;
    color:#00ffff;

    text-shadow:0 0 15px #00ffff;
}

.status-label{
    color:#aaa;
    font-size:13px;
}

::-webkit-scrollbar{
    width:8px;
}

::-webkit-scrollbar-thumb{
    background:#00ffff;
    border-radius:20px;
}

@media(max-width:1200px){

    .dashboard{
        grid-template-columns:1fr;
    }
}

</style>

</head>

<body>

<div class="dashboard">

    <!-- LEWY PANEL -->

    <div class="panel">

        <div class="logo">
            ISKRA
        </div>

        <div class="subtitle">
            NEURAL SYSTEM
        </div>

        <div class="gauge">

            <div class="gauge-title">
                PAMIĘĆ SYSTEMU
            </div>

            <div class="gauge-circle">

                <div class="gauge-inner">

                    <div class="gauge-value"
                    id="ramValue">
                        61%
                    </div>

                    <div>
                        RAM
                    </div>

                </div>

            </div>

        </div>

        <div class="gauge">

            <div class="gauge-title">
                CPU AI
            </div>

            <div class="gauge-circle">

                <div class="gauge-inner">

                    <div class="gauge-value"
                    id="cpuValue">
                        37%
                    </div>

                    <div>
                        CPU
                    </div>

                </div>

            </div>

        </div>

    </div>

    <!-- ŚRODEK -->

    <div class="panel chat">

        <div class="chat-window"
        id="chatWindow">

            <div class="message-ai">
                🔥 ISKRA AI aktywna.
            </div>

        </div>

        <div class="chat-input">

            <<input id="userInput" type="text" placeholder="Napisz wiadomość...">
<button onclick="sendMessage()">➤</button>

        </div>

    </div>

    <!-- PRAWY PANEL -->

    <div class="panel">

        <div class="status-box">

            <div class="status-value"
            id="knowledgeValue">
                0
            </div>

            <div class="status-label">
                BAZA WIEDZY
            </div>

        </div>

        <div class="status-box">

            <div class="status-value"
            id="feedbackValue">
                0
            </div>

            <div class="status-label">
                ŚREDNIA OCENA
            </div>

        </div>

        <div class="status-box">

            <div class="status-value"
            id="usersValue">
                0
            </div>

            <div class="status-label">
                SESJE
            </div>

        </div>

    </div>

</div>

<script>

let sessionId =
    localStorage.getItem("iskra_session") || "";

function escapeHtml(text){

    return text
        .replace(/</g,"&lt;")
        .replace(/>/g,"&gt;");
}

async function sendMessage(){

    const input =
        document.getElementById("chatInput");

    const text = input.value.trim();

    if(!text) return;

    const chat =
        document.getElementById("chatWindow");

    chat.innerHTML += `
        <div class="message-user">
            ${escapeHtml(text)}
        </div>
    `;

    input.value = "";

    chat.scrollTop = chat.scrollHeight;

    try{

        const response = await fetch(
            '/api/chat',
            {
                method:'POST',

                headers:{
                    'Content-Type':'application/json',
                    'X-Session-ID':sessionId
                },

                body:JSON.stringify({
                    pytanie:text
                })
            }
        );

        const data = await response.json();

        if(data.session_id){

            sessionId = data.session_id;

            localStorage.setItem(
                "iskra_session",
                sessionId
            );
        }

        const answer =
            escapeHtml(
                data.odpowiedz ||
                "Brak odpowiedzi"
            );

        chat.innerHTML += `
            <div class="message-ai">
                ${answer}
            </div>
        `;

        chat.scrollTop = chat.scrollHeight;

    }catch(e){

        chat.innerHTML += `
            <div class="message-ai">
                ❌ Błąd połączenia
            </div>
        `;
    }
}

document.getElementById("sendBtn")
.addEventListener("click", sendMessage);

document.getElementById("chatInput")
.addEventListener("keypress", function(e){

    if(e.key === "Enter"){
        sendMessage();
    }
});

async function loadStatus(){

    try{

        const r = await fetch('/status');

        const data = await r.json();

        document.getElementById(
            "knowledgeValue"
        ).innerText = data.wiedza;

        document.getElementById(
            "feedbackValue"
        ).innerText = data.srednia_ocena;

        document.getElementById(
            "usersValue"
        ).innerText = data.users;

    }catch(e){}
}

function animate(){

    document.getElementById("ramValue")
    .innerText =
        Math.floor(Math.random()*40+40)+"%";

    document.getElementById("cpuValue")
    .innerText =
        Math.floor(Math.random()*50+20)+"%";
}

setInterval(randomize,2000);

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
                ${data.odpowiedz || "Brak odpowiedzi"}
            </div>
        `;

        chat.scrollTop = chat.scrollHeight;

    }catch(e){

        chat.innerHTML += `
            <div class="message-ai">
                Błąd połączenia z AI.
            </div>
        `;
    }
}

document.addEventListener("keypress",function(e){

    if(e.key === "Enter"){
        sendMessage();
    }

});

</script>

</body>
</html>

"""

# =========================
# ROUTES
# =========================

@app.route("/")
def index():

    return render_template_string(
        DASHBOARD_HTML
    )

@app.route("/health")
def health():

    return jsonify({
        "status": "ok"
    })

@app.route("/status")
def status():

    return jsonify({
        "wiedza": iskra.memory.size(),
        "srednia_ocena": iskra.feedback.average(),
        "users": len(iskra.history)
    })

@app.route("/api/chat", methods=["POST"])
@limiter.limit("10/minute")
def api_chat():

    auth = auth_required()

    if auth:
        return auth

    data = request.get_json(silent=True)

    if not data:

        return jsonify({
            "error": "Brak JSON"
        }), 400

    question = data.get("pytanie", "")

    if not isinstance(question, str):

        return jsonify({
            "error": "Nieprawidłowe dane"
        }), 400

    question = question.strip()

    if not question:

        return jsonify({
            "error": "Puste pytanie"
        }), 400

    if len(question) > MAX_INPUT:

        return jsonify({
            "error": "Pytanie za długie"
        }), 400

    session_id = request.headers.get(
        "X-Session-ID"
    )

    if not session_id:
        session_id = str(uuid.uuid4())

    answer = iskra.ask(
        question,
        session_id
    )

    return jsonify({
        "odpowiedz": answer,
        "session_id": session_id
    })

@app.route("/api/feedback", methods=["POST"])
def api_feedback():

    data = request.get_json(silent=True)

    if not data:

        return jsonify({
            "error": "Brak JSON"
        }), 400

    rating = data.get("ocena")

    if rating not in [1, -1]:

        return jsonify({
            "error": "Ocena musi być 1 lub -1"
        }), 400

    iskra.feedback.add(
        data.get("pytanie", ""),
        data.get("odpowiedz", ""),
        rating
    )

    return jsonify({
        "message": "OK"
    })

# =========================
# START
# =========================

if __name__ == "__main__":

    print(f"🚀 ISKRA AI START PORT {PORT}")

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False
    )