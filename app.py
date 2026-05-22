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
# KONFIG
# =========================

PORT = int(os.environ.get("PORT", 8080))

DATA_DIR = "/tmp/iskra_data"

os.makedirs(DATA_DIR, exist_ok=True)

PLIK_WIEDZY = os.path.join(
    DATA_DIR,
    "wiedza.json"
)

MAX_HISTORIA = 10
MAX_INPUT = 3000
MAX_SESSIONS = 1000

REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 3

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
# JSON SAVE
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

        except Exception:

            self.dane = {}

    def zapisz(self):

        with self.lock:

            atomic_save(
                PLIK_WIEDZY,
                self.dane
            )

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
# BASE PROVIDER
# =========================

class BaseProvider:

    def generate(self, prompt):

        raise NotImplementedError()

# =========================
# GEMINI
# =========================

class GeminiProvider(BaseProvider):

    def __init__(self):

        self.api_key = os.environ.get(
            "GEMINI_API_KEY",
            ""
        )

        self.url = (
            "https://generativelanguage.googleapis.com/"
            "v1beta/models/gemini-1.5-flash:generateContent"
        )

    def generate(self, prompt):

        if not self.api_key:

            raise Exception(
                "Brak GEMINI_API_KEY"
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

        last_error = None

        for attempt in range(REQUEST_RETRIES):

            try:

                r = requests.post(
                    f"{self.url}?key={self.api_key}",
                    headers=headers,
                    json=data,
                    timeout=REQUEST_TIMEOUT
                )

                if r.status_code != 200:

                    last_error = r.text

                    time.sleep(1)

                    continue

                response = r.json()

                return (
                    response["candidates"][0]
                    ["content"]["parts"][0]["text"]
                )

            except Exception as e:

                last_error = str(e)

                time.sleep(1)

        raise Exception(
            f"Gemini fail: {last_error}"
        )

# =========================
# OPENAI
# =========================

class OpenAIProvider(BaseProvider):

    def __init__(self):

        self.api_key = os.environ.get(
            "OPENAI_API_KEY",
            ""
        )

        self.url = (
            "https://api.openai.com/"
            "v1/chat/completions"
        )

        self.model = os.environ.get(
            "OPENAI_MODEL",
            "gpt-4.1-mini"
        )

    def generate(self, prompt):

        if not self.api_key:

            raise Exception(
                "Brak OPENAI_API_KEY"
            )

        headers = {
            "Authorization": (
                f"Bearer {self.api_key}"
            ),
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7
        }

        last_error = None

        for attempt in range(REQUEST_RETRIES):

            try:

                r = requests.post(
                    self.url,
                    headers=headers,
                    json=data,
                    timeout=REQUEST_TIMEOUT
                )

                if r.status_code != 200:

                    last_error = r.text

                    time.sleep(1)

                    continue

                response = r.json()

                return (
                    response["choices"][0]
                    ["message"]["content"]
                )

            except Exception as e:

                last_error = str(e)

                time.sleep(1)

        raise Exception(
            f"OpenAI fail: {last_error}"
        )

# =========================
# OLLAMA
# =========================

class OllamaProvider(BaseProvider):

    def __init__(self):

        self.url = os.environ.get(
            "OLLAMA_URL",
            "http://localhost:11434/api/generate"
        )

        self.model = os.environ.get(
            "OLLAMA_MODEL",
            "llama3"
        )

    def generate(self, prompt):

        data = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }

        last_error = None

        for attempt in range(REQUEST_RETRIES):

            try:

                r = requests.post(
                    self.url,
                    json=data,
                    timeout=60
                )

                if r.status_code != 200:

                    last_error = r.text

                    time.sleep(1)

                    continue

                response = r.json()

                return response.get(
                    "response",
                    "Brak odpowiedzi"
                )

            except Exception as e:

                last_error = str(e)

                time.sleep(1)

        raise Exception(
            f"Ollama fail: {last_error}"
        )

# =========================
# ROUTER
# =========================

class RouterProvider(BaseProvider):

    def __init__(self):

        self.providers = {
            "gemini": GeminiProvider(),
            "openai": OpenAIProvider(),
            "ollama": OllamaProvider()
        }

        self.primary = os.environ.get(
            "LLM_PROVIDER",
            os.environ.get(
                "PRIMARY_PROVIDER",
                "openai"
            )
        ).lower()

        fallback_env = os.environ.get(
            "LLM_FALLBACK_PROVIDERS",
            os.environ.get(
                "FALLBACK_PROVIDERS",
                "gemini,ollama"
            )
        )

        self.fallbacks = [
            p.strip().lower()
            for p in fallback_env.split(",")
            if p.strip()
        ]

        print("=== ROUTER CONFIG ===")

        print("Primary:", self.primary)

        print("Fallbacks:", self.fallbacks)

    def build_chain(self):

        chain = []

        if self.primary in self.providers:

            chain.append(self.primary)

        for fb in self.fallbacks:

            if (
                fb in self.providers and
                fb not in chain
            ):

                chain.append(fb)

        return chain

    def generate(self, prompt):

        chain = self.build_chain()

        if not chain:

            raise Exception(
                "Brak providerów"
            )

        last_error = None

        for provider_name in chain:

            provider = self.providers[
                provider_name
            ]

            print(
                f"Próba provider: {provider_name}"
            )

            try:

                response = provider.generate(
                    prompt
                )

                if response:

                    print(
                        f"Provider OK: {provider_name}"
                    )

                    return response

            except Exception as e:

                print(
                    f"Provider FAIL: {provider_name}",
                    e
                )

                last_error = str(e)

        raise Exception(
            f"Wszystkie providery padły: "
            f"{last_error}"
        )

# =========================
# FACTORY
# =========================

def create_provider():

    return RouterProvider()

# =========================
# ISKRA
# =========================

class IskraAI:

    def __init__(self):

        self.pamiec = Pamiec()

        self.historia = defaultdict(list)

        self.provider = create_provider()

        print("=== ISKRA START ===")

    def cleanup_sessions(self):

        while len(self.historia) > MAX_SESSIONS:

            oldest = next(iter(self.historia))

            del self.historia[oldest]

    def build_prompt(
        self,
        pytanie,
        context
    ):

        return f"""
SYSTEM:
Jesteś futurystyczną AI
o nazwie Iskra.

Odpowiadaj po polsku.

====================
HISTORIA
====================

{context}

====================
PYTANIE USERA
====================

{pytanie}

====================
ODPOWIEDŹ
====================
"""

    def chat(
        self,
        pytanie,
        session_id
    ):

        self.cleanup_sessions()

        historia = self.historia[
            session_id
        ]

        context = ""

        for p, o in historia[-MAX_HISTORIA:]:

            context += (
                f"Użytkownik: {p}\n"
                f"Iskra: {o}\n\n"
            )

        prompt = self.build_prompt(
            pytanie,
            context
        )

        try:

            odpowiedz = (
                self.provider.generate(prompt)
            )

        except Exception as e:

            odpowiedz = (
                "System AI chwilowo "
                "niedostępny.\n\n"
                f"{e}"
            )

        historia.append(
            (
                pytanie,
                odpowiedz
            )
        )

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

<meta
name="viewport"
content="width=device-width, initial-scale=1.0"
>

<title>ISKRA AI</title>

<style>

body{
    margin:0;
    background:#050816;
    color:white;
    font-family:Arial,sans-serif;
}

.dashboard{
    display:flex;
    flex-direction:column;
    height:100vh;
    padding:20px;
    box-sizing:border-box;
}

.chat-window{
    flex:1;
    overflow:auto;
    padding:20px;
    background:#111827;
    border-radius:20px;
    margin-bottom:20px;
}

.message-user{
    background:#7c3aed;
    padding:15px;
    border-radius:15px;
    margin-bottom:15px;
    margin-left:80px;
}

.message-ai{
    background:#0891b2;
    padding:15px;
    border-radius:15px;
    margin-bottom:15px;
    margin-right:80px;
}

.chat-input{
    display:flex;
    gap:10px;
}

.chat-input input{
    flex:1;
    padding:15px;
    border:none;
    border-radius:15px;
    font-size:16px;
    background:#1f2937;
    color:white;
}

.chat-input button{
    width:80px;
    border:none;
    border-radius:15px;
    background:#06b6d4;
    color:white;
    cursor:pointer;
}

</style>

</head>

<body>

<div class="dashboard">

<div
class="chat-window"
id="chatWindow"
>

<div class="message-ai">
Witaj. Jestem Iskra AI.
</div>

</div>

<div class="chat-input">

<input
type="text"
id="userInput"
placeholder="Napisz wiadomość..."
autofocus
>

<button onclick="sendMessage()">
➤
</button>

</div>

</div>

<script>

function getSessionId(){

    let sid = localStorage.getItem(
        'iskra_session_id'
    );

    if(!sid){

        sid =
            Date.now().toString(36)
            +
            Math.random().toString(36);

        localStorage.setItem(
            'iskra_session_id',
            sid
        );
    }

    return sid;
}

async function sendMessage(){

    const input =
        document.getElementById(
            "userInput"
        );

    const text = input.value.trim();

    if(!text) return;

    const chat =
        document.getElementById(
            "chatWindow"
        );

    const userDiv =
        document.createElement("div");

    userDiv.className =
        "message-user";

    userDiv.textContent = text;

    chat.appendChild(userDiv);

    input.value = "";

    const aiDiv =
        document.createElement("div");

    aiDiv.className =
        "message-ai";

    aiDiv.textContent =
        "Myślę...";

    chat.appendChild(aiDiv);

    chat.scrollTop =
        chat.scrollHeight;

    try{

        const response =
            await fetch(
                '/api/chat',
                {
                    method:'POST',

                    headers:{
                        'Content-Type':
                            'application/json',

                        'X-Session-ID':
                            getSessionId()
                    },

                    body:JSON.stringify({
                        pytanie:text
                    })
                }
            );

        const data =
            await response.json();

        aiDiv.textContent =
            data.odpowiedz;

    }catch(e){

        aiDiv.textContent =
            "Błąd połączenia.";
    }

    chat.scrollTop =
        chat.scrollHeight;
}

document.addEventListener(
    "keypress",
    function(e){

        if(e.key === "Enter"){

            sendMessage();
        }
    }
);

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
        DASHBOARD_HTML
    )

@app.route(
    '/api/chat',
    methods=['POST']
)

@limiter.limit("10/minute")

def api_chat():

    data = request.get_json()

    if not data:

        return jsonify({
            "odpowiedz":
                "Brak danych"
        })

    pytanie = data.get(
        "pytanie",
        ""
    ).strip()

    if not pytanie:

        return jsonify({
            "odpowiedz":
                "Puste pytanie"
        })

    if len(pytanie) > MAX_INPUT:

        return jsonify({
            "odpowiedz":
                "Za długie pytanie"
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
        "pamiec":
            iskra.pamiec.rozmiar(),

        "users":
            len(iskra.historia),

        "provider":
            iskra.provider.primary
    })

@app.route('/health')

def health():

    return jsonify({
        "status": "ok",
        "provider":
            iskra.provider.primary
    })

# =========================
# START
# =========================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=PORT,
        threaded=True
    )